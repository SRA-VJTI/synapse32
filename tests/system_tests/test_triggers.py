"""Sdtrig address triggers (mcontrol type 2, action 0: breakpoint exception).

A matching instruction traps with cause 3 before it executes: epc is the instruction, mtval/stval the
matched address, and the access does not happen. tdata1 is write-any-read-legal, so unsupported bits
read back 0 and a write of 0 disables the trigger. A trigger does not fire while its mode's interrupts
are disabled, so a handler cannot retrigger on itself (Sdtrig "Native Triggers").
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

CONFIG = 0x1000_0000
DATA_A = 0x1000_0100
DATA_B = 0x1000_0104
DATA_C = 0x1000_0108
DATA_A_VALUE = 0x1111_1111
DATA_B_VALUE = 0x2222_2222
DATA_C_VALUE = 0x4444_4444
RESULT = 0x1000_0200
LOG = 0x1000_0300
LOG_SLOTS = 12
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900
STORE_VALUE = 0x3333_3333

CSR_TSELECT, CSR_TDATA1, CSR_TDATA2, CSR_TDATA3 = 0x7A0, 0x7A1, 0x7A2, 0x7A3
TYPE_MCONTROL = 2 << 28
M_BIT, S_BIT, U_BIT = 1 << 6, 1 << 4, 1 << 3
EXECUTE, STORE, LOAD = 1 << 2, 1 << 1, 1 << 0
CAUSE_BREAKPOINT = 3
CAUSE_ILLEGAL = 2


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
        # trigger 0: tdata1 from config[8], tdata2 from config[12]
        csrw    {CSR_TSELECT:#x}, zero
        lw      t1, 12(t0)
        csrw    {CSR_TDATA2:#x}, t1
        lw      t1, 8(t0)
        csrw    {CSR_TDATA1:#x}, t1
        # trigger 1: tdata1 from config[16], tdata2 from config[20]
        li      t1, 1
        csrw    {CSR_TSELECT:#x}, t1
        lw      t1, 20(t0)
        csrw    {CSR_TDATA2:#x}, t1
        lw      t1, 16(t0)
        csrw    {CSR_TDATA1:#x}, t1
        csrw    {CSR_TSELECT:#x}, zero
        lw      t3, 0(t0)
        lw      t4, 24(t0)
        lw      t2, 28(t0)
        li      t5, 3
        beq     t3, t5, run_m
        li      t5, 0x1800
        csrc    mstatus, t5
        slli    t5, t3, 11
        csrs    mstatus, t5
        beqz    t4, 1f
        csrsi   mstatus, 0x2
1:
        csrw    mepc, t2
        mret
run_m:
        beqz    t4, 2f
        csrsi   mstatus, 0x8
2:
        jr      t2

body:
        li      t6, {RESULT:#x}
        li      a1, {DATA_A:#x}
        li      a2, {DATA_B:#x}
        li      a7, {DATA_C:#x}
        li      a3, {STORE_VALUE:#x}
        li      a4, 0
        li      a5, 0
        li      a6, 0
bad_exec:
        addi    a4, a4, 1
bad_load:
        lw      a5, 0(a1)
bad_store:
        sw      a3, 0(a2)
bad_amo:
        amoadd.w a6, a3, (a7)
        sw      a4, 0(t6)
        sw      a5, 4(t6)
        sw      a6, 8(t6)
        j       finish

# ---- Trigger CSR legalization
warl_body:
        li      t6, {RESULT:#x}
        csrw    {CSR_TSELECT:#x}, zero
        li      t0, -1
        csrw    {CSR_TDATA1:#x}, t0
        csrr    t1, {CSR_TDATA1:#x}
        sw      t1, 0(t6)
        csrw    {CSR_TDATA1:#x}, zero
        csrr    t1, {CSR_TDATA1:#x}
        sw      t1, 4(t6)
        li      t0, {TYPE_MCONTROL | M_BIT | EXECUTE:#x}
        csrw    {CSR_TDATA1:#x}, t0
        csrr    t1, {CSR_TDATA1:#x}
        sw      t1, 8(t6)
        li      t0, 0x12345678
        csrw    {CSR_TDATA2:#x}, t0
        csrr    t1, {CSR_TDATA2:#x}
        sw      t1, 12(t6)
        li      t0, 5
        csrw    {CSR_TSELECT:#x}, t0
        csrr    t1, {CSR_TSELECT:#x}
        sw      t1, 16(t6)
        csrr    t1, {CSR_TDATA1:#x}
        sw      t1, 20(t6)
        csrw    {CSR_TSELECT:#x}, zero
        csrr    t1, {CSR_TDATA2:#x}
        sw      t1, 24(t6)
        csrr    t1, {CSR_TDATA3:#x}
        sw      t1, 28(t6)
bad_tinfo:
        csrr    t1, 0x7a4
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
    .text : {{ *(.text.init) *(.text*) }}
}}
"""

M, S, U = 3, 1, 0
NO_TRIGGER = 0

# name, privilege, medeleg, tdata1_0, tdata2_0, tdata1_1, tdata2_1, interrupts enabled,
# expected log [(handler, cause, tval, label)], expected results {offset: value}
CASES = [
    ("m_execute", M, 0, TYPE_MCONTROL | M_BIT | EXECUTE, "bad_exec", NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, "bad_exec", "bad_exec")], {0: 0, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("m_load", M, 0, TYPE_MCONTROL | M_BIT | LOAD, DATA_A, NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, DATA_A, "bad_load")], {0: 1, 4: 0, 8: DATA_C_VALUE}),
    ("m_store", M, 0, TYPE_MCONTROL | M_BIT | STORE, DATA_B, NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, DATA_B, "bad_store")], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("m_amo_as_load", M, 0, TYPE_MCONTROL | M_BIT | LOAD, DATA_C, NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, DATA_C, "bad_amo")], {0: 1, 4: DATA_A_VALUE, 8: 0}),  # AMO reads: load trigger
    ("m_amo_as_store", M, 0, TYPE_MCONTROL | M_BIT | STORE, DATA_C, NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, DATA_C, "bad_amo")], {0: 1, 4: DATA_A_VALUE, 8: 0}),
    ("m_two_triggers", M, 0, TYPE_MCONTROL | M_BIT | EXECUTE, "bad_exec",
     TYPE_MCONTROL | M_BIT | STORE, DATA_B, 1,
     [("m", CAUSE_BREAKPOINT, "bad_exec", "bad_exec"), ("m", CAUSE_BREAKPOINT, DATA_B, "bad_store")],
     {0: 0, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("m_mie_clear_does_not_fire", M, 0, TYPE_MCONTROL | M_BIT | LOAD, DATA_A, NO_TRIGGER, 0, 0,
     [], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("m_trigger_is_s_mode_only", M, 0, TYPE_MCONTROL | S_BIT | LOAD, DATA_A, NO_TRIGGER, 0, 1,
     [], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("s_load_to_m", S, 0, TYPE_MCONTROL | S_BIT | LOAD, DATA_A, NO_TRIGGER, 0, 1,
     [("m", CAUSE_BREAKPOINT, DATA_A, "bad_load")], {0: 1, 4: 0, 8: DATA_C_VALUE}),
    ("s_store_delegated", S, 1 << 3, TYPE_MCONTROL | S_BIT | STORE, DATA_B, NO_TRIGGER, 0, 1,
     [("s", CAUSE_BREAKPOINT, DATA_B, "bad_store")], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("s_delegated_sie_clear_does_not_fire", S, 1 << 3, TYPE_MCONTROL | S_BIT | STORE, DATA_B, NO_TRIGGER, 0, 0,
     [], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("s_undelegated_sie_clear_still_fires", S, 0, TYPE_MCONTROL | S_BIT | STORE, DATA_B, NO_TRIGGER, 0, 0,
     [("m", CAUSE_BREAKPOINT, DATA_B, "bad_store")], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("u_execute_to_m", U, 0, TYPE_MCONTROL | U_BIT | EXECUTE, "bad_exec", NO_TRIGGER, 0, 0,
     [("m", CAUSE_BREAKPOINT, "bad_exec", "bad_exec")], {0: 0, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("u_trigger_is_m_mode_only", U, 0, TYPE_MCONTROL | M_BIT | EXECUTE, "bad_exec", NO_TRIGGER, 0, 0,
     [], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
    ("no_trigger", M, 0, NO_TRIGGER, 0, NO_TRIGGER, 0, 1,
     [], {0: 1, 4: DATA_A_VALUE, 8: DATA_C_VALUE}),
]

# Read-backs of the legalization body
WARL_EXPECTED = {
    0: TYPE_MCONTROL | M_BIT | S_BIT | U_BIT | EXECUTE | STORE | LOAD,  # write of all ones
    4: TYPE_MCONTROL,                                                   # write of 0 disables it
    8: TYPE_MCONTROL | M_BIT | EXECUTE,
    12: 0x12345678,
    16: 1,          # tselect is 2 bits: 5 reads back as 1
    20: TYPE_MCONTROL,
    24: 0x12345678,  # trigger 0's tdata2 is untouched by the writes to trigger 1
    28: 0,           # tdata3 reads zero
}


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("TRIGGERS_BUILD", Path.cwd() / "build" / "triggers"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "triggers.S"
    lds = build_dir / "triggers.ld"
    elf = build_dir / "triggers.elf"
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


async def run_case(dut, entry, privilege, medeleg, tdata1_0, tdata2_0, tdata1_1, tdata2_1, enable, limit=3000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset, value in enumerate((privilege, medeleg, tdata1_0, tdata2_0, tdata1_1, tdata2_1, enable)):
        _poke(dut, CONFIG + 4 * offset, value)
    _poke(dut, DATA_A, DATA_A_VALUE)
    _poke(dut, DATA_B, DATA_B_VALUE)
    _poke(dut, DATA_C, DATA_C_VALUE)
    for offset in range(0, 0x40, 4):
        _poke(dut, RESULT + offset, 0)
    for offset in range(0, 16 * LOG_SLOTS, 4):
        _poke(dut, LOG + offset, 0)
    _poke(dut, LOG_COUNT, 0)
    _poke(dut, DONE_ADDR, 0)
    # The entry point is patched into the jump at the end of _start's setup.
    _poke(dut, CONFIG + 28, entry)
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
        (chr(_peek(dut, LOG + 16 * i)), _peek(dut, LOG + 16 * i + 4),
         _peek(dut, LOG + 16 * i + 8), _peek(dut, LOG + 16 * i + 12))
        for i in range(min(count, LOG_SLOTS))
    ]
    return done, count, log


def _fmt(log):
    return [f"({h}, cause {c}, tval {t:#010x}, epc {e:#010x})" for h, c, t, e in log]


@cocotb.test()
async def test_trigger_matches(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    failures = []
    for name, privilege, medeleg, td1_0, td2_0, td1_1, td2_1, enable, expected_named, results in CASES:
        td2_0 = symbols[td2_0] if isinstance(td2_0, str) else td2_0
        expected = [
            (h, c, symbols[t] if isinstance(t, str) else t, symbols[label])
            for h, c, t, label in expected_named
        ]
        done, count, log = await run_case(dut, symbols["body"], privilege, medeleg, td1_0, td2_0, td1_1, td2_1, enable)
        problems = []
        if not done:
            problems.append("did not finish")
        if count != len(expected) or log != expected:
            problems.append(f"trap log {_fmt(log)} (count {count}), expected {_fmt(expected)}")
        for offset, want in results.items():
            got = _peek(dut, RESULT + offset)
            if got != want:
                problems.append(f"result +{offset} = 0x{got:08x}, expected 0x{want:08x}")
        # A triggered store or AMO must not reach memory; an untriggered one must.
        store_hit = any(label == "bad_store" for *_, label in expected_named)
        amo_hit = any(label == "bad_amo" for *_, label in expected_named)
        want_b = DATA_B_VALUE if store_hit else STORE_VALUE
        want_c = DATA_C_VALUE if amo_hit else (DATA_C_VALUE + STORE_VALUE) & 0xFFFF_FFFF
        if _peek(dut, DATA_B) != want_b:
            problems.append(f"data B = 0x{_peek(dut, DATA_B):08x}, expected 0x{want_b:08x}")
        if _peek(dut, DATA_C) != want_c:
            problems.append(f"data C = 0x{_peek(dut, DATA_C):08x}, expected 0x{want_c:08x}")
        if _peek(dut, DATA_A) != DATA_A_VALUE:
            problems.append(f"data A changed: 0x{_peek(dut, DATA_A):08x}")
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert not failures, f"{len(failures)} of {len(CASES)} trigger cases failed: " + " | ".join(failures)


@cocotb.test()
async def test_trigger_csrs_are_warl(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    done, count, log = await run_case(dut, symbols["warl_body"], M, 0, NO_TRIGGER, 0, NO_TRIGGER, 0, 1)
    problems = []
    if not done:
        problems.append("did not finish")
    for offset, want in WARL_EXPECTED.items():
        got = _peek(dut, RESULT + offset)
        if got != want:
            problems.append(f"read-back +{offset} = 0x{got:08x}, expected 0x{want:08x}")
    # tinfo is not implemented, so reading it raises an illegal instruction (as on Spike).
    expected_log = [("m", CAUSE_ILLEGAL, symbols["bad_tinfo"])]
    got_log = [(h, c, e) for h, c, _, e in log]
    if count != 1 or got_log != expected_log:
        problems.append(f"trap log {_fmt(log)} (count {count}), expected an illegal instruction at bad_tinfo")
    assert not problems, "; ".join(problems)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_triggers"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_triggers",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_triggers",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_triggers",
            "TRIGGERS_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
