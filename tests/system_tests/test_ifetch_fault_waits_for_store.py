"""An instruction page fault waits for an older store that is still waiting for its translation.

In S-mode, a store at the last word of a page misses the TLB; the next fetch hits the TLB on a page
that is readable but not executable. The store must reach memory exactly once before the instruction
page fault is taken, with mepc and mtval at the faulting instruction.
"""

import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

RESULT = 0x1000_0200
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)

CODE_VA, CODE_PA = 0x2000_0000, 0x8001_0000
NOEXEC_VA, NOEXEC_PA = 0x2000_1000, 0x8001_1000
STORE_VA, STORE_PA = 0x2000_2000, 0x1000_1000
STORE_VALUE = 0x1234_5678
ENTRY_OFFSET = 0xFE8

LATENCIES = [0, 2]

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80

PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        csrw    medeleg, zero
        li      t0, {SATP:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        li      t0, {CODE_VA + ENTRY_OFFSET:#x}
        csrw    mepc, t0
        mret

        .align  2
m_trap:
        li      t4, {RESULT:#x}
        csrr    t5, mcause
        sw      t5, 0(t4)
        csrr    t5, mepc
        sw      t5, 4(t4)
        csrr    t5, mtval
        sw      t5, 8(t4)
        li      t4, {DONE_ADDR:#x}
        li      t5, {DONE_VALUE:#x}
        sw      t5, 0(t4)
spin:
        j       spin

        .section .text.smode, "ax"
        .org    {ENTRY_OFFSET:#x}
        lui     t3, {NOEXEC_VA >> 12:#x}
        lw      t2, 0(t3)              # puts the non-executable page in the TLB
        lui     t0, {STORE_VA >> 12:#x}
        li      t1, {STORE_VALUE:#x}
        sw      t1, 0(t0)              # last word of the page; its translation misses the TLB
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) }}
    . = {CODE_PA:#x};
    .smode : {{ *(.text.smode) }}
}}
"""


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("IFETCH_FAULT_BUILD", Path.cwd() / "build" / "ifetch_fault_waits_for_store"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "ifetch_fault.S"
    lds = build_dir / "ifetch_fault.ld"
    elf = build_dir / "ifetch_fault.elf"
    src.write_text(PROGRAM)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "image.bin")], check=True)
    (build_dir / "nop.hex").write_text("@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128)


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < INSTR_MEM_BASE + INSTR_MEM_SIZE:
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address 0x{addr:08x}")


def _poke(dut, addr: int, value: int) -> None:
    dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value & 0xFFFF_FFFF


def _peek(dut, addr: int) -> int:
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


@cocotb.test()
async def test_ifetch_fault_waits_for_store(dut):
    latency = int(os.environ["IFETCH_FAULT_LATENCY"])
    build_dir = _build_dir()
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE + offset, 0)
    _poke(dut, ROOT_TABLE + 4 * (CODE_VA >> 22), _pte(L0_TABLE, V))
    _poke(dut, L0_TABLE + 4 * ((CODE_VA >> 12) & 0x3FF), _pte(CODE_PA, V | R | X | A))
    _poke(dut, L0_TABLE + 4 * ((NOEXEC_VA >> 12) & 0x3FF), _pte(NOEXEC_PA, V | R | A))
    _poke(dut, L0_TABLE + 4 * ((STORE_VA >> 12) & 0x3FF), _pte(STORE_PA, V | R | W | A | D))
    _poke(dut, STORE_PA, 0)
    for offset in range(0, 12, 4):
        _poke(dut, RESULT + offset, 0xFFFF_FFFF)
    _poke(dut, DONE_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    writes = []
    done = False
    for _ in range(5000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.data_write_fire.value) and int(dut.data_store_we.value):
            addr = int(dut.data_store_addr.value) & ~0x3
            data = int(dut.data_store_wdata.value)
            if addr == STORE_PA:
                writes.append(data)
            if addr == DONE_ADDR and data == DONE_VALUE:
                done = True
                break
    await RisingEdge(dut.clk)

    problems = []
    if not done:
        problems.append("the trap handler did not finish")
    mcause, mepc, mtval = (_peek(dut, RESULT + offset) for offset in (0, 4, 8))
    if mcause != 12:
        problems.append(f"mcause 0x{mcause:08x}, expected 12 (instruction page fault)")
    if mepc != NOEXEC_VA:
        problems.append(f"mepc 0x{mepc:08x}, expected 0x{NOEXEC_VA:08x}")
    if mtval != NOEXEC_VA:
        problems.append(f"mtval 0x{mtval:08x}, expected 0x{NOEXEC_VA:08x}")
    stored = _peek(dut, STORE_PA)
    if stored != STORE_VALUE:
        problems.append(f"memory at 0x{STORE_PA:08x} holds 0x{stored:08x}, expected 0x{STORE_VALUE:08x}")
    if writes != [STORE_VALUE]:
        problems.append(f"writes to 0x{STORE_PA:08x}: {[hex(w) for w in writes]}, expected one of 0x{STORE_VALUE:08x}")
    for line in problems:
        dut._log.error(f"latency {latency}: {line}")
    assert not problems, f"latency {latency}: " + "; ".join(problems)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_ifetch_fault_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_ifetch_fault_waits_for_store",
            parameters={"MEM_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_ifetch_fault_waits_for_store",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_ifetch_fault_waits_for_store",
                "IFETCH_FAULT_BUILD": str(build_dir.resolve()),
                "IFETCH_FAULT_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
