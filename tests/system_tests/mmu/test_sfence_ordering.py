"""SFENCE.VMA orders what comes after it.

The core fetches ahead, so an instruction on the next page may already be fetched under the old
mapping when the fence executes; it must be discarded and fetched again.

Both programs put the store and the fence in the last words of page A. The store repoints page B at
different code; the marker page B writes says which mapping the core actually used. In the first, page B
is still being walked when the fence executes. In the second, page B's translation is already in the TLB,
so the words after the fence are fetched from the old page before the fence executes.
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
TRAP_LOG = 0x1000_0500      # cause, tval, epc of the first traps, for diagnosis
TRAP_COUNT = 0x1000_05FC
ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)

# Code pages: the program starts on page A and falls through into page B.
PAGE_A_VA = 0x2000_0000
PAGE_B_VA = 0x2000_1000
PAGE_A_PA = 0x8001_0000
PAGE_B_OLD_PA = 0x8001_1000
PAGE_B_NEW_PA = 0x8001_2000
L0_ENTRY_B = L0_TABLE + 4 * ((PAGE_B_VA >> 12) & 0x3FF)

OLD_MARKER = 0x0BAD_0BAD
NEW_MARKER = 0x600D_600D

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80
RW = V | R | W | A | D
RX = V | R | X | A | D
RWX = V | R | W | X | A | D
# Entry at JUMP_OFFSET starts a speculative walk for page B; the jump back into page A rewrites
# the PTE and fences while that walk is in flight.
STORE_OFFSET = 0xFF0
# The cached program's store and fence are page A's last two words; page B follows the fence.
CACHED_STORE_OFFSET = 0xFF8
FENCE_OFFSET = 0xFF4
GOTO_B_OFFSET = 0xFF8
JUMP_OFFSET = 0xFFC


def _page_b(marker: int, returns: bool = False) -> str:
    """Page B's code: record which physical page the translation ended up pointing at. With `returns`, a first
    call (s0 = 0) only returns, so that page B's translation is in the TLB."""
    call = "\n        beqz    s0, 2f" if returns else ""
    ret = "\n2:\n        jr      ra" if returns else ""
    return f"""
        li      t2, {marker:#x}{call}
        li      t3, {RESULT:#x}
        sw      t2, 0(t3)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b{ret}
"""


_PRELUDE = f"""
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
        li      t0, {PAGE_A_VA:#x}
        csrw    mepc, t0
        mret

        .align  2
m_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        li      t2, {TRAP_COUNT:#x}
        lw      t0, 0(t2)
        addi    t1, t0, 1
        sw      t1, 0(t2)
        slli    t0, t0, 4
        li      t1, {TRAP_LOG:#x}
        add     t0, t0, t1
        csrr    t1, mcause
        sw      t1, 0(t0)
        csrr    t1, mtval
        sw      t1, 4(t0)
        csrr    t1, mepc
        sw      t1, 8(t0)
        addi    t1, t1, 4
        csrw    mepc, t1
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret
"""

PROGRAM = _PRELUDE + f"""
# ---- Page A, linked at {PAGE_A_PA:#x} and run at {PAGE_A_VA:#x}.
        .section .pagea, "ax"
page_a:
        li      t0, {L0_ENTRY_B:#x}
        li      t1, {pte(PAGE_B_NEW_PA, RX):#x}
        li      t5, {PAGE_B_VA:#x}
        li      t4, {PAGE_A_VA + JUMP_OFFSET:#x}
        jr      t4                     # to the last word: page B is fetched speculatively after it

# ---- The last four words of page A.
        .section .pagea_end, "ax"
page_a_end:
        sw      t1, 0(t0)              # page B now maps to different code
        sfence.vma                     # the speculative walk for page B is still in flight here
        jr      t5                     # now go to page B for real
        j       page_a_end             # the jump whose fall-through starts that walk

# ---- Page B, two versions at different physical pages; the PTE decides which one runs.
        .section .pageb_old, "ax"
page_b_old:{_page_b(OLD_MARKER)}

        .section .pageb_new, "ax"
page_b_new:{_page_b(NEW_MARKER)}
"""

PROGRAM_CACHED = _PRELUDE + f"""
# ---- Page A, linked at {PAGE_A_PA:#x} and run at {PAGE_A_VA:#x}.
        .section .pagea, "ax"
page_a:
        li      s0, 0
        li      t5, {PAGE_B_VA:#x}
        jalr    ra, t5                 # run page B once: its old translation is now in the TLB
        li      s0, 1
        li      t0, {L0_ENTRY_B:#x}
        li      t1, {pte(PAGE_B_NEW_PA, RX):#x}
        li      t4, {PAGE_A_VA + CACHED_STORE_OFFSET:#x}
        jr      t4

# ---- The last two words of page A.
        .section .pagea_end, "ax"
page_a_end:
        sw      t1, 0(t0)              # page B now maps to different code
        sfence.vma                     # page B's first words are already fetched under the old mapping

# ---- Page B, two versions at different physical pages; the PTE decides which one runs.
        .section .pageb_old, "ax"
page_b_old:{_page_b(OLD_MARKER, returns=True)}

        .section .pageb_new, "ax"
page_b_new:{_page_b(NEW_MARKER, returns=True)}
"""


def _linker_script(store_offset: int) -> str:
    return f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text) }}
    . = {PAGE_A_PA:#x};
    .pagea : {{ *(.pagea) }}
    . = {PAGE_A_PA + store_offset:#x};
    .pagea_end : {{ *(.pagea_end) }}
    . = {PAGE_B_OLD_PA:#x};
    .pageb_old : {{ *(.pageb_old) }}
    . = {PAGE_B_NEW_PA:#x};
    .pageb_new : {{ *(.pageb_new) }}
}}
"""


def _build_dir() -> Path:
    return Path(os.environ.get("SFENCE_ORDER_BUILD", Path.cwd() / "build" / "sfence_ordering"))


async def _run(dut, directory: Path):
    """Run one program; return page B's marker, the PTE reads seen, and the problems found so far."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    # Memory is written only while the core is held in reset: the second test follows the first in one simulation.
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 1)
    image = (directory / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))
    for offset in range(0, 0x1000, 4):
        poke(dut, ROOT_TABLE + offset, 0)
        poke(dut, L0_TABLE + offset, 0)
    poke(dut, ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), pte(INSTR_MEM_BASE, RWX))
    poke(dut, ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, RW))
    poke(dut, ROOT_TABLE + 4 * (PAGE_A_VA >> 22), pte(L0_TABLE, V))
    poke(dut, L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF), pte(PAGE_A_PA, RX))
    poke(dut, L0_ENTRY_B, pte(PAGE_B_OLD_PA, RX))
    poke(dut, RESULT, 0)
    poke(dut, DONE_ADDR, 0)
    poke(dut, TRAP_COUNT, 0)
    for offset in range(0, 0x80, 4):
        poke(dut, TRAP_LOG + offset, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    walks_seen = 0
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.cpu_inst.mmu_walk_gnt.value):
            walks_seen += 1
        if (int(dut.cpu_inst.module_data_gnt_in.value) and int(dut.cpu_inst.module_mem_wr_en.value) and int(dut.cpu_inst.module_write_addr.value) == DONE_ADDR
                and int(dut.cpu_inst.module_wr_data_out.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)

    marker = peek(dut, RESULT)
    traps = peek(dut, TRAP_COUNT)
    log = [tuple(peek(dut, TRAP_LOG + 16 * i + 4 * k) for k in range(3)) for i in range(min(traps, 6))]
    dut._log.info(f"marker 0x{marker:08x} after {walks_seen} PTE reads, {traps} traps: "
                  + str([(c, hex(t), hex(e)) for c, t, e in log]))
    problems = []
    if not done:
        problems.append("the program did not finish")
    if traps:
        problems.append(f"{traps} unexpected traps: " + str([(c, hex(t), hex(e)) for c, t, e in log]))
    return marker, walks_seen, problems


@cocotb.test()
async def test_instructions_after_a_fence_use_the_new_mapping(dut):
    marker, walks_seen, problems = await _run(dut, _build_dir() / "walk")
    if marker == OLD_MARKER:
        problems.append("page B ran from the old mapping: a walk that a fence interrupted was "
                        "filled into the TLB")
    elif marker != NEW_MARKER:
        problems.append(f"page B stored 0x{marker:08x}, expected the new marker 0x{NEW_MARKER:08x}")
    if walks_seen == 0:
        problems.append("no page-table entry was ever read: the program did not exercise the walker")
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


@cocotb.test()
async def test_instructions_fetched_before_a_fence_are_fetched_again(dut):
    marker, _, problems = await _run(dut, _build_dir() / "cached")
    if marker != NEW_MARKER:
        problems.append(f"page B stored 0x{marker:08x}, expected the new marker 0x{NEW_MARKER:08x}: instructions "
                        "fetched under the old mapping before the fence were executed instead of fetched again")
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir / "walk", "sfence_walk", PROGRAM, _linker_script(STORE_OFFSET))
    assemble(build_dir / "cached", "sfence_cached", PROGRAM_CACHED, _linker_script(CACHED_STORE_OFFSET))

    run_top(
        "test_sfence_ordering",
        boot_image=nop_image(),
        extra_env={"SFENCE_ORDER_BUILD": str(build_dir.resolve())},
    )


if __name__ == "__main__":
    runCocotbTests()
