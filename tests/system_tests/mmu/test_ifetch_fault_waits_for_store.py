"""An instruction page fault waits for an older store that is still waiting for its translation.

In S-mode, a store at the last word of a page misses the TLB; the next fetch hits the TLB on a page
that is readable but not executable. The store must reach memory exactly once before the instruction
page fault is taken, with mepc and mtval at the faulting instruction.
"""

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from support import INSTR_MEM_BASE, assemble, nop_image, peek, poke, pte, run_top


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


def _build_dir() -> Path:
    return Path(os.environ.get("IFETCH_FAULT_BUILD", Path.cwd() / "build" / "ifetch_fault_waits_for_store"))


@cocotb.test()
async def test_ifetch_fault_waits_for_store(dut):
    latency = int(os.environ["IFETCH_FAULT_LATENCY"])
    build_dir = _build_dir()
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset in range(0, 0x1000, 4):
        poke(dut, ROOT_TABLE + offset, 0)
        poke(dut, L0_TABLE + offset, 0)
    poke(dut, ROOT_TABLE + 4 * (CODE_VA >> 22), pte(L0_TABLE, V))
    poke(dut, L0_TABLE + 4 * ((CODE_VA >> 12) & 0x3FF), pte(CODE_PA, V | R | X | A))
    poke(dut, L0_TABLE + 4 * ((NOEXEC_VA >> 12) & 0x3FF), pte(NOEXEC_PA, V | R | A))
    poke(dut, L0_TABLE + 4 * ((STORE_VA >> 12) & 0x3FF), pte(STORE_PA, V | R | W | A | D))
    poke(dut, STORE_PA, 0)
    for offset in range(0, 12, 4):
        poke(dut, RESULT + offset, 0xFFFF_FFFF)
    poke(dut, DONE_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    writes = []
    done = False
    for _ in range(5000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        # A write is done when the data port takes it from the store buffer (into the data cache).
        if int(dut.cpu_inst.drain_done.value):
            addr = int(dut.cpu_inst.drain_addr.value) & ~0x3
            data = int(dut.cpu_inst.drain_data.value)
            if addr == STORE_PA:
                writes.append(data)
            if addr == DONE_ADDR and data == DONE_VALUE:
                done = True
                break
    await RisingEdge(dut.clk)

    problems = []
    if not done:
        problems.append("the trap handler did not finish")
    mcause, mepc, mtval = (peek(dut, RESULT + offset) for offset in (0, 4, 8))
    if mcause != 12:
        problems.append(f"mcause 0x{mcause:08x}, expected 12 (instruction page fault)")
    if mepc != NOEXEC_VA:
        problems.append(f"mepc 0x{mepc:08x}, expected 0x{NOEXEC_VA:08x}")
    if mtval != NOEXEC_VA:
        problems.append(f"mtval 0x{mtval:08x}, expected 0x{NOEXEC_VA:08x}")
    stored = peek(dut, STORE_PA)
    if stored != STORE_VALUE:
        problems.append(f"memory at 0x{STORE_PA:08x} holds 0x{stored:08x}, expected 0x{STORE_VALUE:08x}")
    if writes != [STORE_VALUE]:
        problems.append(f"writes to 0x{STORE_PA:08x}: {[hex(w) for w in writes]}, expected one of 0x{STORE_VALUE:08x}")
    for line in problems:
        dut._log.error(f"latency {latency}: {line}")
    assert not problems, f"latency {latency}: " + "; ".join(problems)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir, "ifetch_fault", PROGRAM, LINKER_SCRIPT)

    for latency in LATENCIES:
        run_top(
            "test_ifetch_fault_waits_for_store",
            parameters={"MEM_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"IFETCH_FAULT_BUILD": str(build_dir.resolve()), "IFETCH_FAULT_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
