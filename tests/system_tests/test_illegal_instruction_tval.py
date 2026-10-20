"""mtval/stval on illegal-instruction traps (privileged spec 3.1.16).

The spec allows 0 or the faulting instruction; this core reports the instruction, like Spike. Every
instruction labelled bad_* is illegal in its case's mode and must trap with cause 2, epc at the label
and tval the instruction word there; the others must not trap.
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
LOG = 0x1000_0300
LOG_SLOTS = 12
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900

MSTATUS_TVM_TW_TSR = (1 << 20) | (1 << 21) | (1 << 22)

BODIES = {
    "m": """
bad_m_0:
        .word   0xFFFFFFFF
        csrr    t1, mscratch
bad_m_1:
        csrw    mvendorid, t1
bad_m_2:
        csrr    t1, 0x7c0
""",
    "s": """
bad_s_0:
        mret
bad_s_1:
        csrr    t1, mstatus
bad_s_2:
        wfi
bad_s_3:
        sfence.vma
bad_s_4:
        sret
        csrr    t1, sscratch
""",
    "sd": """
bad_sd_0:
        csrr    t1, mscratch
        csrr    t1, sscratch
bad_sd_1:
        .word   0xFFFFFFFF
bad_sd_2:
        mret
""",
    "u": """
bad_u_0:
        sret
bad_u_1:
        csrr    t1, sstatus
bad_u_2:
        csrr    t1, cycle
bad_u_3:
        mret
""",
}
BODY_ORDER = list(BODIES)


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
        li      t0, {CONFIG:#x}
        lw      t1, 4(t0)
        csrw    medeleg, t1
        lw      t1, 8(t0)
        csrs    mstatus, t1
        lw      t1, 12(t0)
        slli    t1, t1, 2
        la      t2, body_table
        add     t2, t2, t1
        lw      t2, 0(t2)
        lw      t3, 0(t0)
        li      t4, 3
        beq     t3, t4, run_m
        li      t4, 0x1800
        csrc    mstatus, t4
        slli    t4, t3, 11
        csrs    mstatus, t4
        csrw    mepc, t2
        mret
run_m:
        jr      t2

        .align  2
body_table:
        .word   {", ".join(f"body_{name}" for name in BODY_ORDER)}

{"".join(f"body_{name}:{text}        j       finish{chr(10)}" for name, text in BODIES.items())}
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

M, S, U = 3, 1, 0

# name, privilege, medeleg, mstatus bits set before entering the body, body, handler that takes the traps
CASES = [
    ("m_mode", M, 0x0, 0, "m", "m"),
    ("s_mode_to_m", S, 0x0, MSTATUS_TVM_TW_TSR, "s", "m"),
    ("s_mode_delegated", S, 0x4, 0, "sd", "s"),
    ("u_mode_to_m", U, 0x0, 0, "u", "m"),
    ("u_mode_delegated", U, 0x4, 0, "u", "s"),
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("ILLEGAL_TVAL_BUILD", Path.cwd() / "build" / "illegal_instruction_tval"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "illegal.S"
    lds = build_dir / "illegal.ld"
    elf = build_dir / "illegal.elf"
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


async def run_case(dut, privilege, medeleg, mstatus_bits, body_index, limit=3000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset, value in enumerate((privilege, medeleg, mstatus_bits, body_index)):
        _poke(dut, CONFIG + 4 * offset, value)
    for offset in range(0, 16 * LOG_SLOTS, 4):
        _poke(dut, LOG + offset, 0)
    _poke(dut, LOG_COUNT, 0)
    _poke(dut, DONE_ADDR, 0)
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
async def test_illegal_instruction_tval(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    def word_at(addr):
        offset = addr - INSTR_MEM_BASE
        return int.from_bytes(image[offset:offset + 4], "little")

    failures = []
    checked = 0
    for name, privilege, medeleg, mstatus_bits, body, handler in CASES:
        labels = sorted(
            (value for key, value in symbols.items() if key.startswith(f"bad_{body}_")),
        )
        expected = [(handler, 2, word_at(addr), addr) for addr in labels]
        done, count, log = await run_case(dut, privilege, medeleg, mstatus_bits, BODY_ORDER.index(body))
        problems = []
        if not done:
            problems.append("did not finish")
        if count != len(expected) or log != expected:
            shown = [(h, c, f"{t:#010x}", f"{e:#010x}") for h, c, t, e in log]
            want = [(h, c, f"{t:#010x}", f"{e:#010x}") for h, c, t, e in expected]
            problems.append(f"log (mode, cause, tval, epc) {shown} (count {count}), expected {want}")
        checked += len(expected)
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert checked >= 18, f"only {checked} illegal instructions checked"
    assert not failures, f"{len(failures)} of {len(CASES)} cases failed: " + " | ".join(failures)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_illegal_instruction_tval"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_illegal_instruction_tval",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_illegal_instruction_tval",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_illegal_instruction_tval",
            "ILLEGAL_TVAL_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
