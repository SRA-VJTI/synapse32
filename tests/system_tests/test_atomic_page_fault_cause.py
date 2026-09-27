"""Page-fault causes of atomic and ordinary memory accesses under Sv32 (BUGS B15).

An access that writes reports a store/AMO page fault (15), including an AMO, which also reads; LR and
loads report a load page fault (13). The faulting instruction leaves memory and rd unchanged. The
cases run in S-mode on identity megapages with a read-only alias and an unmapped VA, and in M-mode
with MPRV = 1 and MPP = S.
"""

import os
import shutil
import struct
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

CONFIG = 0x1000_0000
TARGET = 0x1000_0100
TARGET_VALUE = 0x1122_3344
RESULT = 0x1000_0200
LOG = 0x1000_0300
LOG_SLOTS = 12
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900
PAGE_TABLE = 0x1001_0000
SATP_SV32 = 0x8000_0000 | (PAGE_TABLE >> 12)
READ_ONLY_VA = 0x4000_0000
UNMAPPED_VA = 0x5000_0000
RD_MARKER = 0x5A5A

# VA megapage -> (PA, flags)
MEGAPAGES = {
    INSTR_MEM_BASE: (INSTR_MEM_BASE, 0xCF),
    DATA_MEM_BASE: (DATA_MEM_BASE, 0xC7),
    READ_ONLY_VA: (DATA_MEM_BASE, 0xC3),
}

A0 = READ_ONLY_VA + (TARGET - DATA_MEM_BASE)
A1 = UNMAPPED_VA


def _handler(mode: str) -> str:
    ret = "mret" if mode == "m" else "sret"
    return f"""
        .align  2
{mode}_trap:
        csrrw   sp, {mode}scratch, sp
        sw      t0, 0(sp)
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        li      t2, {LOG_COUNT:#x}
        lw      t0, 0(t2)
        addi    t1, t0, 1
        sw      t1, 0(t2)
        slli    t0, t0, 4
        li      t1, {LOG:#x}
        add     t0, t0, t1
        li      t1, {ord(mode)}
        sw      t1, 0(t0)
        csrr    t1, {mode}cause
        sw      t1, 4(t0)
        csrr    t1, {mode}tval
        sw      t1, 8(t0)
        csrr    t1, {mode}epc
        sw      t1, 12(t0)
        addi    t1, t1, 4
        csrw    {mode}epc, t1
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, {mode}scratch, sp
        {ret}
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        li      t0, {S_SCRATCH:#x}
        csrw    sscratch, t0
        la      t0, m_trap
        csrw    mtvec, t0
        la      t0, s_trap
        csrw    stvec, t0
        li      t0, 0xB000
        csrw    medeleg, t0
        li      t0, {SATP_SV32:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        li      t0, {CONFIG:#x}
        lw      t1, 0(t0)
        bnez    t1, 1f
        la      t0, body_s
        csrw    mepc, t0
        mret
1:
        li      t0, 0x20000
        csrs    mstatus, t0
        j       body_mprv

body_s:
        li      t6, {RESULT:#x}
        li      a0, {A0:#x}
        li      a1, {A1:#x}
        li      t1, 7
        li      t2, {RD_MARKER:#x}
bad_s_0:
        amoadd.w t2, t1, (a0)
bad_s_1:
        amoswap.w t2, t1, (a1)
        sw      t2, 0(t6)
bad_s_2:
        lr.w    t3, (a1)
        lr.w    t3, (a0)
bad_s_3:
        sc.w    t3, t1, (a0)
        lw      t4, 0(a0)
        sw      t4, 4(t6)
bad_s_4:
        sw      t1, 0(a0)
bad_s_5:
        lw      t3, 0(a1)
        j       finish

body_mprv:
        li      t6, {RESULT:#x}
        li      a0, {A0:#x}
        li      a1, {A1:#x}
        li      t1, 7
        li      t2, {RD_MARKER:#x}
bad_m_0:
        amoadd.w t2, t1, (a0)
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
        sw      t2, 0(t6)
bad_m_1:
        lr.w    t3, (a1)
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
        lw      t4, 0(a0)
        sw      t4, 4(t6)
        j       finish

finish:
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin
{_handler("m")}
{_handler("s")}
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) *(.rodata*) }}
}}
"""

# name, config, expected log [(handler, cause, tval, label)]
CASES = [
    ("s_mode", 0, [
        ("s", 15, A0, "bad_s_0"),
        ("s", 15, A1, "bad_s_1"),
        ("s", 13, A1, "bad_s_2"),
        ("s", 15, A0, "bad_s_3"),
        ("s", 15, A0, "bad_s_4"),
        ("s", 13, A1, "bad_s_5"),
    ]),
    ("m_mode_mprv", 1, [
        ("m", 15, A0, "bad_m_0"),
        ("m", 13, A1, "bad_m_1"),
    ]),
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("ATOMIC_PF_BUILD", Path.cwd() / "build" / "atomic_page_fault_cause"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "atomic_pf.S"
    lds = build_dir / "atomic_pf.ld"
    elf = build_dir / "atomic_pf.elf"
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
    symbols = _elf32_symbols(elf.read_bytes())
    (build_dir / "symbols.txt").write_text("".join(f"{value:08x} {name}\n" for name, value in sorted(symbols.items())))
    (build_dir / "nop.hex").write_text("@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128)


def _elf32_symbols(elf: bytes) -> dict:
    assert elf[:4] == b"\x7fELF" and elf[4] == 1 and elf[5] == 1, "expected a little-endian ELF32 file"
    e_shoff, = struct.unpack_from("<I", elf, 32)
    e_shentsize, e_shnum = struct.unpack_from("<HH", elf, 46)
    sections = [struct.unpack_from("<IIIIIIIIII", elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    table = {}
    for _, sh_type, _, _, offset, size, link, _, _, entsize in sections:
        if sh_type != 2:  # SHT_SYMTAB
            continue
        strtab_offset = sections[link][4]
        for pos in range(offset, offset + size, entsize):
            st_name, st_value = struct.unpack_from("<II", elf, pos)
            if st_name:
                end = elf.index(b"\x00", strtab_offset + st_name)
                table[elf[strtab_offset + st_name:end].decode()] = st_value
    return table


def _load_symbols(build_dir: Path) -> dict:
    table = {}
    for line in (build_dir / "symbols.txt").read_text().splitlines():
        value, name = line.split()
        table[name] = int(value, 16)
    return table


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


async def run_case(dut, config, limit=20000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _poke(dut, CONFIG, config)
    _poke(dut, TARGET, TARGET_VALUE)
    for offset in range(0, 16 * LOG_SLOTS, 4):
        _poke(dut, LOG + offset, 0)
    _poke(dut, RESULT, 0)
    _poke(dut, RESULT + 4, 0)
    _poke(dut, LOG_COUNT, 0)
    _poke(dut, DONE_ADDR, 0)
    for va, (pa, flags) in MEGAPAGES.items():
        _poke(dut, PAGE_TABLE + 4 * (va >> 22), ((pa >> 12) << 10) | flags)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(limit):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.cpu_mem_write_en.value) and int(dut.cpu_mem_write_addr.value) == DONE_ADDR
                and int(dut.cpu_mem_write_data.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)
    count = _peek(dut, LOG_COUNT)
    log = [
        (chr(_peek(dut, LOG + 16 * i)), _peek(dut, LOG + 16 * i + 4), _peek(dut, LOG + 16 * i + 8), _peek(dut, LOG + 16 * i + 12))
        for i in range(min(count, LOG_SLOTS))
    ]
    return done, count, log


@cocotb.test()
async def test_atomic_page_fault_cause(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    failures = []
    for name, config, expected_named in CASES:
        expected = [(h, c, t, symbols[label]) for h, c, t, label in expected_named]
        done, count, log = await run_case(dut, config)
        problems = []
        if not done:
            problems.append("did not finish")
        if count != len(expected) or log != expected:
            shown = [(h, c, f"{t:#010x}", f"{e:#010x}") for h, c, t, e in log]
            want = [(h, c, f"{t:#010x}", f"{e:#010x}") for h, c, t, e in expected]
            problems.append(f"log (mode, cause, tval, epc) {shown} (count {count}), expected {want}")
        if _peek(dut, TARGET) != TARGET_VALUE:
            problems.append(f"read-only target written: 0x{_peek(dut, TARGET):08x}")
        if _peek(dut, RESULT) != RD_MARKER:
            problems.append(f"rd of the faulting AMO changed: 0x{_peek(dut, RESULT):08x}")
        if _peek(dut, RESULT + 4) != TARGET_VALUE:
            problems.append(f"read through the read-only alias gave 0x{_peek(dut, RESULT + 4):08x}")
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert not failures, f"{len(failures)} of {len(CASES)} cases failed: " + " | ".join(failures)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    # At latency 2 a faulting store would still be in flight when the trap is taken.
    for latency in (0, 2):
        sim_build = Path.cwd() / "sim_build" / f"sim_build_atomic_page_fault_cause_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_atomic_page_fault_cause",
            parameters={"MEM_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_atomic_page_fault_cause",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_atomic_page_fault_cause",
                "ATOMIC_PF_BUILD": str(build_dir.resolve()),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
