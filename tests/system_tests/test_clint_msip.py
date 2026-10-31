"""CLINT msip raises and clears mip.MSIP and traps to M-mode under OpenSBI's delegation."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from cocotb_test.simulator import run
from memory_view import read_word

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000
MSIP = 0x0200_0000

RESULT = 0x1000_0200
RESULT_WORDS = 16
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_030C
IRQ_COUNT = 0x1000_0310

LATENCIES = [0, 2]  # MEM_LATENCY and FETCH_LATENCY; at 2 the msip write waits in the store buffer
POLL = 64
MIP_MSIP = 0x8
MSIP_CAUSE = 0x8000_0003
OPENSBI_MIDELEG = 0x222


def _poll_mip(slot: int, until_set: bool) -> str:
    """Read mip.MSIP until it is set (or clear), at most POLL times, and store the last value at slot(a7)."""
    branch = "bnez" if until_set else "beqz"
    return f"""
        li      t2, {POLL}
1:
        csrr    t0, mip
        andi    t0, t0, {MIP_MSIP}
        {branch}    t0, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
        sw      t0, {slot}(a7)
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a7, {RESULT:#x}
        li      s0, {MSIP:#x}
        li      s1, {IRQ_COUNT:#x}

        csrr    t0, mip
        andi    t0, t0, {MIP_MSIP}
        sw      t0, 0(a7)

        li      t1, 1
        sw      t1, 0(s0)
{_poll_mip(4, True)}
        lw      t0, 0(s0)
        sw      t0, 8(a7)

        sw      zero, 0(s0)
{_poll_mip(12, False)}
        lw      t0, 0(s0)
        sw      t0, 16(a7)

        li      t1, 1
        sw      t1, 4(s0)
        lw      t0, 4(s0)
        sw      t0, 20(a7)
{_poll_mip(24, True)}

        la      t0, msip_trap
        csrw    mtvec, t0
        li      t0, {OPENSBI_MIDELEG:#x}
        csrw    mideleg, t0
        li      t0, {MIP_MSIP}
        csrw    mie, t0
        csrsi   mstatus, 8
        li      t1, 1
        sw      t1, 0(s0)
        li      t2, {POLL}
1:
        lw      t0, 0(s1)
        bnez    t0, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
        csrci   mstatus, 8
        csrr    t0, mip
        andi    t0, t0, {MIP_MSIP}
        sw      t0, 32(a7)

        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b

        .align  2
msip_trap:
        csrr    t3, mcause
        sw      t3, 28(a7)
        sw      zero, 0(s0)
        lw      t3, 0(s0)               # msip is clear before mret
        lw      t3, 0(s1)
        addi    t3, t3, 1
        sw      t3, 0(s1)
        mret

        .align  2
m_trap:
        li      t1, {TRAP_CAUSE:#x}
        csrr    t0, mcause
        sw      t0, 0(t1)
        csrr    t0, mepc
        sw      t0, 8(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
"""

# Slot -> (what it is, expected value)
EXPECTED = {
    0: ("mip.MSIP after reset", 0),
    4: ("mip.MSIP after writing msip 1", MIP_MSIP),
    8: ("msip read back after writing 1", 1),
    12: ("mip.MSIP after writing msip 0", 0),
    16: ("msip read back after writing 0", 0),
    20: ("hart 1's msip read back after writing 1", 0),
    24: ("mip.MSIP after writing hart 1's msip", 0),
    28: ("mcause in the msip handler", MSIP_CAUSE),
    32: ("mip.MSIP after the handler cleared msip", 0),
}

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) }}
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
    return Path(os.environ.get("CLINT_BUILD", Path.cwd() / "build" / "clint_msip"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "msip.S"
    lds = build_dir / "msip.ld"
    elf = build_dir / "msip.elf"
    src.write_text(PROGRAM)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr_zifencei", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "msip.bin")],
                   check=True)
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
    """What the program sees at addr."""
    return read_word(dut, _phys_word_index(addr))


def _name() -> str:
    return f"latency {os.environ['CLINT_LATENCY']}"


@cocotb.test()
async def test_msip_raises_and_clears_the_machine_software_interrupt(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    data = (_build_dir() / "msip.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for offset in range(0, 4 * RESULT_WORDS, 4):
        _poke(dut, RESULT + offset, 0xDEAD_BEEF)
    for addr in (DONE_ADDR, TRAP_CAUSE, TRAP_EPC, IRQ_COUNT):
        _poke(dut, addr, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            done = True
            break

    assert done, f"{_name()}: the program did not finish"
    cause = _peek(dut, TRAP_CAUSE)
    assert cause == 0, f"{_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"
    wrong = [f"{what}: 0x{_peek(dut, RESULT + slot):08x}, expected 0x{value:08x}"
             for slot, (what, value) in EXPECTED.items() if _peek(dut, RESULT + slot) != value]
    assert not wrong, f"{_name()}: " + "; ".join(wrong)
    count = _peek(dut, IRQ_COUNT)
    assert count == 1, f"{_name()}: the msip handler ran {count} times, expected once"


@cocotb.test()
async def test_device_tree_clint_window_matches_the_rtl(dut):
    """OpenSBI takes the CLINT window from the device tree; it must be the standard 64 KB the RTL decodes."""
    repo_root = _find_repo_root()
    dts = (repo_root / "sim" / "synapse32.dts").read_text()
    node = re.search(r"clint@2000000\s*\{(.*?)\};", dts, re.S)
    assert node, "no clint node in sim/synapse32.dts"
    dts_base, dts_size = (int(v, 16) for v in re.search(r"reg = <(0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)>", node.group(1)).groups())
    mmap = (repo_root / "rtl" / "include" / "memory_map.vh").read_text()
    rtl = {name: int(value, 16) for name, value in re.findall(r"`define (TIMER_BASE|TIMER_SIZE|TIMER_END)\s+32'h([0-9a-fA-F]+)", mmap)}
    assert (dts_base, dts_size) == (rtl["TIMER_BASE"], rtl["TIMER_SIZE"]), (
        f"device tree clint reg 0x{dts_base:08x}+0x{dts_size:x}, RTL decodes 0x{rtl['TIMER_BASE']:08x}+0x{rtl['TIMER_SIZE']:x}")
    assert rtl["TIMER_END"] == rtl["TIMER_BASE"] + rtl["TIMER_SIZE"] - 1, "TIMER_END does not match TIMER_SIZE"
    assert rtl["TIMER_SIZE"] == 0x10000, f"CLINT window 0x{rtl['TIMER_SIZE']:x}, the standard is 0x10000"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_clint_msip_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_clint_msip",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_clint_msip",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_clint_msip",
                "CLINT_BUILD": str(build_dir.resolve()),
                "CLINT_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
