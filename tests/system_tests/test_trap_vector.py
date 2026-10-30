"""Trap vector modes of mtvec and stvec (privileged spec 3.1.7 and 4.1.2).

Direct (MODE 0): every trap enters at BASE. Vectored (MODE 1): exceptions enter at BASE, interrupts at
BASE + 4 * cause code. MODE is WARL: bit 1 is cleared on write, so 2 reads back 0 and 3 reads back 1.
Each case configures mtvec/stvec, privilege, delegation and one trap source, and checks which handler
entry ran with which cause.
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
from memory_view import read_word

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

CONFIG = 0x1000_0100
RESULT = 0x1000_0200
LOG = 0x1000_0300
LOG_SLOTS = 8
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
ACK_ADDR = 0x1000_0404
READY_ADDR = 0x1000_0408
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900
PAGE_TABLE = 0x1001_0000
SATP_SV32 = 0x8000_0000 | (PAGE_TABLE >> 12)
MTIMECMP_LO = 0x0200_4000
UNMAPPED_VA = 0x4000_0000
LOOP_COUNT = 200
DIRECT = 0xFF

# Sv32 identity megapages
MEGAPAGES = {
    INSTR_MEM_BASE: 0xCF,
    DATA_MEM_BASE: 0xCF,
    0x0200_0000: 0xC7,
}

ACTION_NONE = 0
ACTION_SOFTWARE = 1
ACTION_EXTERNAL = 2
ACTION_TIMER = 3
ACTION_ECALL = 4
ACTION_ILLEGAL = 5
ACTION_LOAD_PAGE_FAULT = 6
ACTION_INSTR_PAGE_FAULT = 7
ACTION_WARL = 8


def _vector_table(mode: str) -> str:
    lines = [f"        .align  2\n{mode}_vec:"]
    lines += [f"        j       {mode}_entry_{i}" for i in range(16)]
    for i in range(16):
        lines.append(
            f"{mode}_entry_{i}:\n"
            f"        csrrw   sp, {mode}scratch, sp\n"
            f"        sw      t0, 0(sp)\n"
            f"        li      t0, {i}\n"
            f"        j       {mode}_common"
        )
    lines.append(
        f"        .align  2\n{mode}_direct:\n"
        f"        csrrw   sp, {mode}scratch, sp\n"
        f"        sw      t0, 0(sp)\n"
        f"        li      t0, {DIRECT}\n"
        f"        j       {mode}_common"
    )
    return "\n".join(lines)


def _common_handler(mode: str) -> str:
    """Log (mode, entry in t0, cause), service the trap, return. Saves everything it touches."""
    ret = "mret" if mode == "m" else "sret"
    return f"""
{mode}_common:
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        sw      t3, 12(sp)
        li      t3, {LOG_COUNT:#x}
        lw      t2, 0(t3)
        addi    t1, t2, 1
        sw      t1, 0(t3)
        slli    t2, t2, 3
        li      t1, {LOG:#x}
        add     t2, t2, t1
        li      t1, {ord(mode) << 8:#x}
        or      t0, t0, t1
        sw      t0, 0(t2)
        csrr    t1, {mode}cause
        sw      t1, 4(t2)
        bltz    t1, {mode}_irq
        li      t2, 12
        beq     t1, t2, {mode}_fetch_fault
        csrr    t1, {mode}epc
        addi    t1, t1, 4
        csrw    {mode}epc, t1
        j       {mode}_ret
{mode}_fetch_fault:
        csrw    {mode}epc, ra
        j       {mode}_ret
{mode}_irq:
        andi    t1, t1, 0x3f
        li      t2, 5
        beq     t1, t2, {mode}_timer
        li      t2, 7
        beq     t1, t2, {mode}_timer
        li      t1, {ACK_ADDR:#x}
        sw      t1, 0(t1)
        j       {mode}_ret
{mode}_timer:
        li      t1, {MTIMECMP_LO + 4:#x}
        li      t2, -1
        sw      t2, 0(t1)
{mode}_ret:
        lw      t3, 12(sp)
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
        li      t0, {CONFIG:#x}
        lw      t1, 0(t0)
        csrw    mtvec, t1
        lw      t1, 4(t0)
        csrw    stvec, t1
        lw      t1, 12(t0)
        csrw    mideleg, t1
        lw      t1, 16(t0)
        csrw    medeleg, t1
        li      t1, 0xAAA
        csrw    mie, t1
        lw      t1, 24(t0)
        beqz    t1, 1f
        li      t2, {SATP_SV32:#x}
        csrw    satp, t2
1:
        lw      t3, 8(t0)
        li      t4, 3
        la      t2, body
        beq     t3, t4, run_m
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
        csrsi   mstatus, 0x2
        csrw    mepc, t2
        mret
run_m:
        csrsi   mstatus, 0x8
        jr      t2

body:
        li      t6, {RESULT:#x}
        li      t0, {CONFIG:#x}
        lw      a0, 20(t0)
        li      t1, {ACTION_TIMER}
        bne     a0, t1, 2f
        li      t2, {MTIMECMP_LO:#x}
        sw      zero, 4(t2)
        sw      zero, 0(t2)
2:
        li      t1, {ACTION_ECALL}
        bne     a0, t1, 3f
        ecall
3:
        li      t1, {ACTION_ILLEGAL}
        bne     a0, t1, 4f
        .word   0x00000000
4:
        li      t1, {ACTION_LOAD_PAGE_FAULT}
        bne     a0, t1, 5f
        li      t2, {UNMAPPED_VA:#x}
        lw      t3, 0(t2)
5:
        li      t1, {ACTION_INSTR_PAGE_FAULT}
        bne     a0, t1, 6f
        li      t2, {UNMAPPED_VA:#x}
        jalr    ra, 0(t2)
6:
        li      t1, {ACTION_WARL}
        bne     a0, t1, 7f
        csrr    s1, mtvec
        csrr    s2, stvec
        li      t2, 0x80001002
        csrw    mtvec, t2
        csrr    t3, mtvec
        sw      t3, 8(t6)
        li      t2, 0x80002003
        csrw    mtvec, t2
        csrr    t3, mtvec
        sw      t3, 12(t6)
        li      t2, 0x80003006
        csrw    stvec, t2
        csrr    t3, stvec
        sw      t3, 16(t6)
        li      t2, 0x80004001
        csrw    stvec, t2
        csrr    t3, stvec
        sw      t3, 20(t6)
        csrw    mtvec, s1
        csrw    stvec, s2
7:
        li      t1, {READY_ADDR:#x}
        sw      t1, 0(t1)
        li      s0, 0
        li      s3, {LOOP_COUNT}
loop:
        addi    s0, s0, 1
        blt     s0, s3, loop
        sw      s0, 0(t6)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

{_vector_table("m")}
{_common_handler("m")}
{_vector_table("s")}
{_common_handler("s")}
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) *(.rodata*) }}
}}
"""

M, S = 3, 1

# name, mtvec, stvec, privilege, mideleg, medeleg, action, mmu, expected log [(handler, entry, cause)].
# A tvec is "vec", "direct", "mode2" or "mode3".
CASES = [
    ("m_software_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_SOFTWARE, 0, [("m", 3, 0x8000_0003)]),
    ("m_timer_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_TIMER, 0, [("m", 7, 0x8000_0007)]),
    ("m_external_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_EXTERNAL, 0, [("m", 11, 0x8000_000B)]),
    ("s_software_delegated_vectored", "vec", "vec", S, 0x002, 0x0000, ACTION_SOFTWARE, 0, [("s", 1, 0x8000_0001)]),
    ("s_timer_delegated_vectored", "vec", "vec", S, 0x020, 0x0000, ACTION_TIMER, 0, [("s", 5, 0x8000_0005)]),
    ("s_external_delegated_vectored", "vec", "vec", S, 0x200, 0x0000, ACTION_EXTERNAL, 0, [("s", 9, 0x8000_0009)]),
    ("s_mmu_external_delegated_vectored", "vec", "vec", S, 0x200, 0x0000, ACTION_EXTERNAL, 1, [("s", 9, 0x8000_0009)]),
    ("s_software_to_m_vectored", "vec", "vec", S, 0x000, 0x0000, ACTION_SOFTWARE, 0, [("m", 3, 0x8000_0003)]),
    ("s_timer_delegated_m_direct", "direct", "vec", S, 0x020, 0x0000, ACTION_TIMER, 0, [("s", 5, 0x8000_0005)]),
    ("s_external_to_m_s_direct", "vec", "direct", S, 0x000, 0x0000, ACTION_EXTERNAL, 0, [("m", 11, 0x8000_000B)]),
    ("m_software_mode3_is_vectored", "mode3", "direct", M, 0x000, 0x0000, ACTION_SOFTWARE, 0, [("m", 3, 0x8000_0003)]),
    ("m_software_mode2_is_direct", "mode2", "direct", M, 0x000, 0x0000, ACTION_SOFTWARE, 0, [("m", 0, 0x8000_0003)]),
    ("m_ecall_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_ECALL, 0, [("m", 0, 11)]),
    ("m_illegal_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_ILLEGAL, 0, [("m", 0, 2)]),
    ("s_ecall_to_m_vectored", "vec", "vec", S, 0x000, 0x0000, ACTION_ECALL, 0, [("m", 0, 9)]),
    ("s_ecall_delegated_vectored", "vec", "vec", S, 0x000, 0x0200, ACTION_ECALL, 0, [("s", 0, 9)]),
    ("s_load_page_fault_delegated_vectored", "vec", "vec", S, 0x000, 0x2000, ACTION_LOAD_PAGE_FAULT, 1, [("s", 0, 13)]),
    ("s_load_page_fault_to_m_vectored", "vec", "vec", S, 0x000, 0x0000, ACTION_LOAD_PAGE_FAULT, 1, [("m", 0, 13)]),
    ("s_instr_page_fault_delegated_vectored", "vec", "vec", S, 0x000, 0x1000, ACTION_INSTR_PAGE_FAULT, 1, [("s", 0, 12)]),
    ("s_instr_page_fault_to_m_vectored", "vec", "vec", S, 0x000, 0x0000, ACTION_INSTR_PAGE_FAULT, 1, [("m", 0, 12)]),
    ("m_software_direct", "direct", "direct", M, 0x000, 0x0000, ACTION_SOFTWARE, 0, [("m", DIRECT, 0x8000_0003)]),
    ("s_external_delegated_direct", "direct", "direct", S, 0x200, 0x0000, ACTION_EXTERNAL, 0, [("s", DIRECT, 0x8000_0009)]),
    ("m_ecall_direct", "direct", "direct", M, 0x000, 0x0000, ACTION_ECALL, 0, [("m", DIRECT, 11)]),
    ("m_no_trap_vectored", "vec", "vec", M, 0x000, 0x0000, ACTION_NONE, 0, []),
]

# WARL read-backs (ACTION_WARL)
WARL_EXPECTED = {8: 0x8000_1000, 12: 0x8000_2001, 16: 0x8000_3004, 20: 0x8000_4001}


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("TRAP_VECTOR_BUILD", Path.cwd() / "build" / "trap_vector"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "trap_vector.S"
    lds = build_dir / "trap_vector.ld"
    elf = build_dir / "trap_vector.elf"
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
    return read_word(dut, _phys_word_index(addr)) & 0xFFFF_FFFF


def _load_image(dut, build_dir: Path) -> None:
    data = (build_dir / "image.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for va, flags in MEGAPAGES.items():
        _poke(dut, PAGE_TABLE + 4 * (va >> 22), ((va >> 12) << 10) | flags)


def _tvec(symbols: dict, kind: str, mode: str) -> int:
    table = symbols[f"{mode}_vec"]
    return {
        "vec": table | 1,
        "mode2": table | 2,
        "mode3": table | 3,
        "direct": symbols[f"{mode}_direct"],
    }[kind]


async def run_case(dut, mtvec, stvec, privilege, mideleg, medeleg, action, mmu, limit=20000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _poke(dut, CONFIG, mtvec)
    _poke(dut, CONFIG + 4, stvec)
    _poke(dut, CONFIG + 8, privilege)
    _poke(dut, CONFIG + 12, mideleg)
    _poke(dut, CONFIG + 16, medeleg)
    _poke(dut, CONFIG + 20, action)
    _poke(dut, CONFIG + 24, mmu)
    for offset in range(0, 0x100, 4):
        _poke(dut, RESULT + offset, 0)
        _poke(dut, LOG + offset, 0)
    _poke(dut, DONE_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    # Level interrupt: held until the handler acknowledges it.
    pin = {ACTION_SOFTWARE: dut.software_interrupt, ACTION_EXTERNAL: dut.external_interrupt}.get(action)
    raise_pin = lower_pin = False
    done = False
    for _ in range(limit):
        await RisingEdge(dut.clk)
        if raise_pin:
            pin.value = 1
            raise_pin = False
        if lower_pin:
            pin.value = 0
            lower_pin = False
        await ReadOnly()
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            if addr == READY_ADDR and pin is not None:
                raise_pin = True
            elif addr == ACK_ADDR and pin is not None:
                lower_pin = True
            elif addr == DONE_ADDR and int(dut.cpu_mem_write_data.value) == DONE_VALUE:
                done = True
                break
    await RisingEdge(dut.clk)
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    count = _peek(dut, LOG_COUNT)
    log = []
    for index in range(min(count, LOG_SLOTS)):
        word = _peek(dut, LOG + 8 * index)
        log.append((chr(word >> 8), word & 0xFF, _peek(dut, LOG + 8 * index + 4)))
    result = {offset: _peek(dut, RESULT + offset) for offset in (0, 8, 12, 16, 20)}
    return done, count, log, result


def _show(log):
    return [(h, "direct" if e == DIRECT else e, f"{c:#x}") for h, e, c in log]


async def _start(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _load_image(dut, build_dir)
    return symbols


@cocotb.test()
async def test_trap_entry_per_mode(dut):
    """Every case enters the expected handler entry with the expected cause and resumes the loop."""
    symbols = await _start(dut)
    failures = []
    for name, mtvec, stvec, privilege, mideleg, medeleg, action, mmu, expected in CASES:
        done, count, log, result = await run_case(
            dut, _tvec(symbols, mtvec, "m"), _tvec(symbols, stvec, "s"), privilege, mideleg, medeleg, action, mmu
        )
        problems = []
        if not done:
            problems.append("did not finish")
        if result[0] != LOOP_COUNT:
            problems.append(f"loop result {result[0]} != {LOOP_COUNT}")
        if count != len(expected) or log != expected:
            problems.append(f"trap log {_show(log)} (count {count}), expected {_show(expected)}")
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert not failures, f"{len(failures)} of {len(CASES)} trap-vector cases failed: " + " | ".join(failures)


@cocotb.test()
async def test_tvec_mode_is_warl(dut):
    """Writes of MODE 2 and 3 read back as 0 and 1; BASE bits are kept."""
    symbols = await _start(dut)
    done, count, log, result = await run_case(
        dut, _tvec(symbols, "vec", "m"), _tvec(symbols, "vec", "s"), M, 0, 0, ACTION_WARL, 0
    )
    assert done and count == 0, f"WARL program did not finish cleanly: done={done} log={_show(log)}"
    problems = [
        f"+{offset}: read 0x{result[offset]:08x}, expected 0x{value:08x}"
        for offset, value in WARL_EXPECTED.items() if result[offset] != value
    ]
    assert not problems, "mtvec/stvec read-back: " + "; ".join(problems)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_trap_vector"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_trap_vector",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_trap_vector",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_trap_vector",
            "TRAP_VECTOR_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
