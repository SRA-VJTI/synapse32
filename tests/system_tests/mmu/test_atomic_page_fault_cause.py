"""Page-fault causes of atomic and ordinary memory accesses under Sv32.

An access that writes reports a store/AMO page fault (15), including an AMO, which also reads; LR and
loads report a load page fault (13). The faulting instruction leaves memory and rd unchanged. The
cases run in S-mode on identity megapages with a read-only alias and an unmapped VA, and in M-mode
with MPRV = 1 and MPP = S.
"""

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from support import DATA_MEM_BASE, INSTR_MEM_BASE, assemble, load_symbols, nop_image, peek, poke, run_top


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


def _build_dir() -> Path:
    return Path(os.environ.get("ATOMIC_PF_BUILD", Path.cwd() / "build" / "atomic_page_fault_cause"))


async def run_case(dut, config, limit=20000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    poke(dut, CONFIG, config)
    poke(dut, TARGET, TARGET_VALUE)
    for offset in range(0, 16 * LOG_SLOTS, 4):
        poke(dut, LOG + offset, 0)
    poke(dut, RESULT, 0)
    poke(dut, RESULT + 4, 0)
    poke(dut, LOG_COUNT, 0)
    poke(dut, DONE_ADDR, 0)
    for va, (pa, flags) in MEGAPAGES.items():
        poke(dut, PAGE_TABLE + 4 * (va >> 22), ((pa >> 12) << 10) | flags)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(limit):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.cpu_inst.module_mem_wr_en.value) and int(dut.cpu_inst.module_write_addr.value) == DONE_ADDR
                and int(dut.cpu_inst.module_wr_data_out.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)
    count = peek(dut, LOG_COUNT)
    log = [
        (chr(peek(dut, LOG + 16 * i)), peek(dut, LOG + 16 * i + 4), peek(dut, LOG + 16 * i + 8), peek(dut, LOG + 16 * i + 12))
        for i in range(min(count, LOG_SLOTS))
    ]
    return done, count, log


@cocotb.test()
async def test_atomic_page_fault_cause(dut):
    build_dir = _build_dir()
    symbols = load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

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
        if peek(dut, TARGET) != TARGET_VALUE:
            problems.append(f"read-only target written: 0x{peek(dut, TARGET):08x}")
        if peek(dut, RESULT) != RD_MARKER:
            problems.append(f"rd of the faulting AMO changed: 0x{peek(dut, RESULT):08x}")
        if peek(dut, RESULT + 4) != TARGET_VALUE:
            problems.append(f"read through the read-only alias gave 0x{peek(dut, RESULT + 4):08x}")
        dut._log.info(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        if problems:
            failures.append(f"{name}: {'; '.join(problems)}")
    assert not failures, f"{len(failures)} of {len(CASES)} cases failed: " + " | ".join(failures)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir, "atomic_pf", PROGRAM, LINKER_SCRIPT)

    # At latency 2 a faulting store would still be in flight when the trap is taken.
    for latency in (0, 2):
        run_top(
            "test_atomic_page_fault_cause",
            parameters={"MEM_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ATOMIC_PF_BUILD": str(build_dir.resolve())},
        )


if __name__ == "__main__":
    runCocotbTests()
