"""Routing of supervisor-level interrupts by mideleg (privileged spec 3.1.9, BUGS B14).

An undelegated SSIP, STIP or SEIP traps to M-mode keeping cause 1, 5 or 9, after MEI, MSI and MTI.
A delegated one traps to S-mode and is never taken while in M-mode. Each case pends its bits, runs a
counting loop in the configured mode, and checks which handler ran with which cause.
"""

import os
import shutil
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
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900
MTIMECMP_LO = 0x0200_4000
LOOP_COUNT = 100


def _handler(mode: str) -> str:
    ret = "mret" if mode == "m" else "sret"
    timer_check = "        li      t2, 7\n        beq     t1, t2, m_timer\n" if mode == "m" else ""
    timer_body = f"""m_timer:
        li      t1, {MTIMECMP_LO + 4:#x}
        li      t2, -1
        sw      t2, 0(t1)
        j       m_ret
""" if mode == "m" else ""
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
        slli    t0, t0, 3
        li      t1, {LOG:#x}
        add     t0, t0, t1
        li      t1, {ord(mode)}
        sw      t1, 0(t0)
        csrr    t1, {mode}cause
        sw      t1, 4(t0)
        bltz    t1, {mode}_irq
        csrr    t1, {mode}epc
        addi    t1, t1, 4
        csrw    {mode}epc, t1
        j       {mode}_ret
{mode}_irq:
        andi    t1, t1, 0x3f
{timer_check}        li      t2, 1
        sll     t2, t2, t1
        csrc    {mode}ip, t2
        j       {mode}_ret
{timer_body}{mode}_ret:
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
        csrw    mideleg, t1
        lw      t1, 12(t0)
        csrw    mie, t1
        lw      t1, 16(t0)
        beqz    t1, 1f
        li      t2, {MTIMECMP_LO:#x}
        sw      zero, 4(t2)
        sw      zero, 0(t2)
1:
        lw      t1, 8(t0)
        csrw    mip, t1
        lw      t3, 0(t0)
        lw      t4, 20(t0)
        la      t2, body
        li      t5, 3
        beq     t3, t5, run_m
        li      t5, 0x1800
        csrc    mstatus, t5
        slli    t5, t3, 11
        csrs    mstatus, t5
        beqz    t4, 2f
        csrsi   mstatus, 0x2
2:
        csrw    mepc, t2
        mret
run_m:
        beqz    t4, 3f
        csrsi   mstatus, 0x8
3:
        jr      t2

body:
        li      t6, {RESULT:#x}
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
SSI, STI, SEI = 0x002, 0x020, 0x200
IRQ = 0x8000_0000

# name, privilege, mideleg, pended mip bits, mie, machine timer pending, global enable, expected log
CASES = [
    ("m_ssi_undelegated", M, 0x000, SSI, SSI, 0, 1, [("m", IRQ | 1)]),
    ("m_sti_undelegated", M, 0x000, STI, STI, 0, 1, [("m", IRQ | 5)]),
    ("m_sei_undelegated", M, 0x000, SEI, SEI, 0, 1, [("m", IRQ | 9)]),
    ("m_undelegated_mie_clear", M, 0x000, SSI | STI | SEI, SSI | STI | SEI, 0, 0, []),
    ("m_undelegated_not_enabled", M, 0x000, SSI | STI | SEI, 0x000, 0, 1, []),
    ("s_ssi_undelegated", S, 0x000, SSI, SSI, 0, 0, [("m", IRQ | 1)]),
    ("s_sei_undelegated_sie_set", S, 0x000, SEI, SEI, 0, 1, [("m", IRQ | 9)]),
    ("u_sti_undelegated", U, 0x000, STI, STI, 0, 0, [("m", IRQ | 5)]),
    ("s_ssi_delegated", S, 0x222, SSI, SSI, 0, 1, [("s", IRQ | 1)]),
    ("s_ssi_delegated_sie_clear", S, 0x222, SSI, SSI, 0, 0, []),
    ("m_delegated_not_taken", M, 0x222, SSI | STI | SEI, SSI | STI | SEI, 0, 1, []),
    ("m_priority_mti_sei_ssi_sti", M, 0x000, SSI | STI | SEI, 0xAAA, 1, 1,
     [("m", IRQ | 7), ("m", IRQ | 9), ("m", IRQ | 1), ("m", IRQ | 5)]),
    ("u_mixed_delegation", U, SSI, SSI | STI | SEI, SSI | STI | SEI, 0, 0,
     [("m", IRQ | 9), ("m", IRQ | 5), ("s", IRQ | 1)]),
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("UNDELEGATED_IRQ_BUILD", Path.cwd() / "build" / "undelegated_interrupts"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "undelegated.S"
    lds = build_dir / "undelegated.ld"
    elf = build_dir / "undelegated.elf"
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
    return read_word(dut, _phys_word_index(addr)) & 0xFFFF_FFFF


async def run_case(dut, privilege, mideleg, pend, mie, timer, enable, limit=5000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset, value in enumerate((privilege, mideleg, pend, mie, timer, enable)):
        _poke(dut, CONFIG + 4 * offset, value)
    _poke(dut, RESULT, 0)
    for offset in range(0, 4 * 2 * LOG_SLOTS, 4):
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
    log = [(chr(_peek(dut, LOG + 8 * i)), _peek(dut, LOG + 8 * i + 4)) for i in range(min(count, LOG_SLOTS))]
    return done, count, log, _peek(dut, RESULT)


@cocotb.test()
async def test_supervisor_interrupt_routing(dut):
    build_dir = _build_dir()
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    data = (build_dir / "image.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))

    failures = []
    for name, privilege, mideleg, pend, mie, timer, enable, expected in CASES:
        done, count, log, result = await run_case(dut, privilege, mideleg, pend, mie, timer, enable)
        problems = []
        if not done:
            problems.append("did not finish")
        if result != LOOP_COUNT:
            problems.append(f"loop result {result} != {LOOP_COUNT}")
        if count != len(expected) or log != expected:
            shown = [(h, f"{c:#x}") for h, c in log]
            problems.append(f"trap log {shown} (count {count}), expected {[(h, f'{c:#x}') for h, c in expected]}")
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert not failures, f"{len(failures)} of {len(CASES)} routing cases failed: " + " | ".join(failures)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_undelegated_interrupts"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_undelegated_interrupts",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_undelegated_interrupts",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_undelegated_interrupts",
            "UNDELEGATED_IRQ_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
