"""A store and a load of the same address across a page-table walk.

A store whose translation misses the TLB waits for the walk; the load that follows must still see
the stored value, the shape of a function prologue and epilogue (sw ra,12(sp) ... lw ra,12(sp)).

The program runs in S-mode and touches pages deliberately kept out of the TLB: each round stores
through a fresh mapping, fences so the next round walks again, and reads the value back.
"""

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

from support import DATA_MEM_BASE, INSTR_MEM_BASE, assemble, nop_image, peek, poke, pte, run_top


RESULT = 0x1000_0200
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)

# Four pages the program stores to and loads back, each a fresh walk after a fence.
PAGE_VAS = [0x2000_0000, 0x2000_1000, 0x2000_2000, 0x2000_3000]
PAGE_PAS = [0x1000_1000, 0x1000_2000, 0x1000_3000, 0x1000_4000]
STORE_BASE = 0x5100_0000

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80
RW = V | R | W | A | D
RWX = V | R | W | X | A | D


def _round(index: int, va: int) -> str:
    """One round in the shape of a function prologue: the first store waits for a walk while the
    second, using the same base register, is held in EX."""
    return f"""
        sfence.vma
        li      a4, {va + 0x40:#x}
        li      a2, {STORE_BASE + index:#x}
        li      a5, {STORE_BASE + 0x100 + index:#x}
        addi    a1, a4, -16            # producer of the base register
        sw      a2, 8(a1)              # waits for the walk
        sw      a5, 12(a1)             # held in EX during that wait
        lw      a3, 8(a1)
        sw      a3, {4 * index}(t6)
        lw      a3, 12(a1)
        sw      a3, {4 * (index + len(PAGE_VAS))}(t6)
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        la      t0, m_trap
        csrw    mtvec, t0
        csrw    medeleg, zero
        li      t0, {SATP:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        la      t0, body
        csrw    mepc, t0
        mret

body:
        li      t6, {RESULT:#x}
{"".join(_round(i, va) for i, va in enumerate(PAGE_VAS))}
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

        .align  2
m_trap:
        csrr    t0, mcause
        csrr    t1, mepc
        addi    t1, t1, 4
        csrw    mepc, t1
        mret
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) }}
}}
"""


def _build_dir() -> Path:
    return Path(os.environ.get("STORE_LOAD_WALK_BUILD", Path.cwd() / "build" / "store_load_across_walk"))


@cocotb.test()
async def test_store_is_visible_to_a_load_after_a_walk(dut):
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
    poke(dut, ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), pte(INSTR_MEM_BASE, RWX))
    poke(dut, ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, RW))
    poke(dut, ROOT_TABLE + 4 * (PAGE_VAS[0] >> 22), pte(L0_TABLE, V))
    for va, pa in zip(PAGE_VAS, PAGE_PAS):
        poke(dut, L0_TABLE + 4 * ((va >> 12) & 0x3FF), pte(pa, RW))
        for offset in range(0, 0x60, 4):
            poke(dut, pa + offset, 0)
    for offset in range(0, 0x40, 4):
        poke(dut, RESULT + offset, 0)
    poke(dut, DONE_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.cpu_inst.module_data_gnt_in.value) and int(dut.cpu_inst.module_mem_wr_en.value) and int(dut.cpu_inst.module_write_addr.value) == DONE_ADDR
                and int(dut.cpu_inst.module_wr_data_out.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)

    problems = []
    if not done:
        problems.append("the program did not finish")
    for index, pa in enumerate(PAGE_PAS):
        first = peek(dut, RESULT + 4 * index)
        second = peek(dut, RESULT + 4 * (index + len(PAGE_PAS)))
        want_first = STORE_BASE + index
        want_second = STORE_BASE + 0x100 + index
        if first != want_first:
            problems.append(f"page {index}: the store that waited for the walk read back 0x{first:08x}, "
                            f"expected 0x{want_first:08x}")
        if second != want_second:
            problems.append(f"page {index}: the store held in EX during the wait read back 0x{second:08x}, "
                            f"expected 0x{want_second:08x}")
        # Both stores use the same base register, so they must land 4 bytes apart in the same page.
        for offset, want in ((0x30 + 8, want_first), (0x30 + 12, want_second)):
            in_memory = peek(dut, pa + offset)
            if in_memory != want:
                problems.append(f"page {index}: memory at +0x{offset:x} holds 0x{in_memory:08x}, "
                                f"expected 0x{want:08x}")
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir, "store_load_walk", PROGRAM, LINKER_SCRIPT)

    run_top(
        "test_store_load_across_walk",
        boot_image=nop_image(),
        extra_env={"STORE_LOAD_WALK_BUILD": str(build_dir.resolve())},
    )


if __name__ == "__main__":
    runCocotbTests()
