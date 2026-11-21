"""Sequential Sv32 walker and TLB.

The walk is an FSM that reads one PTE level at a time over the data memory interface, with the
result kept in a TLB. The test counts PTE reads per phase: a first touch of a page walks two levels,
a second touch walks none, a megapage walks one, and SFENCE.VMA or a write to satp forces a re-walk.
It also covers the walker's faults: an invalid entry at either level, and a misaligned megapage.
"""

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from support import DATA_MEM_BASE, INSTR_MEM_BASE, assemble, load_symbols, nop_image, peek, poke, pte, run_top


MARK_ADDR = 0x1000_0000
RESULT = 0x1000_0200
LOG = 0x1000_0300
LOG_SLOTS = 8
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800

ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
ALT_ROOT_TABLE = 0x1001_2000
ALT_L0_TABLE = 0x1001_3000
PT_REGION_END = ALT_L0_TABLE + 0x1000

SATP_MAIN = 0x8000_0000 | (ROOT_TABLE >> 12)
SATP_ALT = 0x8000_0000 | (ALT_ROOT_TABLE >> 12)

PAGE_A_VA = 0x2000_0000
PAGE_B_VA = 0x2000_1000
PAGE_BAD_L0_VA = 0x2000_2000
MEGA_VA = 0x4000_0000
MEGA_PA = 0x8040_0000          # 4 MiB aligned, inside the instruction region
BAD_MEGA_VA = 0x3000_0000      # megapage PTE with a non-zero PPN[0]
BAD_L1_VA = 0x5000_0000        # no entry at the root

PAGE_A_PA = 0x1000_1000
PAGE_B_PA = 0x1000_2000
PAGE_A_ALT_PA = 0x1000_3000
PAGE_A_VALUE = 0xAAAA_0001
PAGE_B_VALUE = 0xBBBB_0002
PAGE_A_ALT_VALUE = 0xCCCC_0003
MEGA_VALUE = 0xDDDD_0004

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80
RW = V | R | W | A | D
RWX = V | R | W | X | A | D
CAUSE_LOAD_PAGE_FAULT = 13

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
        li      t0, {SATP_MAIN:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        la      t0, body
        csrw    mepc, t0
        mret

        .macro  mark n
        li      t0, {MARK_ADDR:#x}
        li      t1, \\n
        sw      t1, 0(t0)
        .endm

body:
        li      t6, {RESULT:#x}
        li      a1, {PAGE_A_VA:#x}
        li      a2, {PAGE_B_VA:#x}
        li      a3, {MEGA_VA:#x}
        mark    1
        lw      s0, 0(a1)              # first touch of page A: two levels
        mark    2
        lw      s1, 4(a1)              # same page again: no walk
        mark    3
        lw      s2, 0(a2)              # another 4 KiB page: two levels
        mark    4
        lw      s3, 0(a3)              # megapage: one level
        mark    5
        sfence.vma                     # every translation is dropped
        lw      s4, 0(a1)              # page A again: two levels
        mark    6
        li      t0, {SATP_ALT:#x}
        csrw    satp, t0               # a write to satp drops them too
        lw      s5, 0(a1)              # page A through the other table
        mark    7
        li      t0, {SATP_MAIN:#x}
        csrw    satp, t0
        li      t0, {BAD_L1_VA:#x}
bad_l1:
        lw      t1, 0(t0)              # no entry at the root: one level, then a fault
        mark    8
        li      t0, {PAGE_BAD_L0_VA:#x}
bad_l0:
        lw      t1, 0(t0)              # invalid leaf: two levels, then a fault
        mark    9
        li      t0, {BAD_MEGA_VA:#x}
bad_mega:
        lw      t1, 0(t0)              # misaligned megapage: one level, then a fault
        mark    10
        sw      s0, 0(t6)
        sw      s1, 4(t6)
        sw      s2, 8(t6)
        sw      s3, 12(t6)
        sw      s4, 16(t6)
        sw      s5, 20(t6)
        fence   w, w                   # the results are visible before the done word
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

        .align  2
m_trap:
        csrrw   sp, mscratch, sp
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
        csrr    t1, mcause
        sw      t1, 0(t0)
        csrr    t1, mtval
        sw      t1, 4(t0)
        csrr    t1, mepc
        addi    t1, t1, 4
        csrw    mepc, t1
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
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

# phase -> PTE reads it must take. After a flush, the next fetch and the next mark store walk their
# megapages again, counted in the phase they happen in.
EXPECTED_WALK_READS = {
    1: 2,   # first touch of a 4 KiB page: root then leaf
    2: 0,   # same page: the TLB answers, nothing goes to memory
    3: 2,   # a different 4 KiB page
    4: 1,   # megapage: the root entry is the leaf
    5: 4,   # SFENCE.VMA: code megapage + page A (two levels) + data megapage for the next mark
    6: 4,   # write to satp: the same three walks, page A now through the other root table
    7: 3,   # write to satp again, then one read for the missing root entry before the fault
    8: 2,   # valid root, invalid leaf: two reads, then the fault
    9: 1,   # misaligned megapage: one read, then the fault
}
EXPECTED_RESULTS = {
    0: PAGE_A_VALUE,
    4: PAGE_A_VALUE,
    8: PAGE_B_VALUE,
    12: MEGA_VALUE,
    16: PAGE_A_VALUE,
    20: PAGE_A_ALT_VALUE,
}
EXPECTED_FAULTS = [
    (CAUSE_LOAD_PAGE_FAULT, BAD_L1_VA, "bad_l1"),
    (CAUSE_LOAD_PAGE_FAULT, PAGE_BAD_L0_VA, "bad_l0"),
    (CAUSE_LOAD_PAGE_FAULT, BAD_MEGA_VA, "bad_mega"),
]


def _build_dir() -> Path:
    return Path(os.environ.get("TLB_BUILD", Path.cwd() / "build" / "tlb"))


def _install_tables(dut) -> None:
    for offset in range(0, 0x1000, 4):
        poke(dut, ROOT_TABLE + offset, 0)
        poke(dut, L0_TABLE + offset, 0)
        poke(dut, ALT_ROOT_TABLE + offset, 0)
        poke(dut, ALT_L0_TABLE + offset, 0)
    # Identity megapages for code and for the data the program and handler use.
    poke(dut, ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), pte(INSTR_MEM_BASE, RWX))
    poke(dut, ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, RW))
    # 4 KiB pages under VA 0x20000000, and a megapage at VA 0x40000000.
    poke(dut, ROOT_TABLE + 4 * (PAGE_A_VA >> 22), pte(L0_TABLE, V))
    poke(dut, L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF), pte(PAGE_A_PA, RW))
    poke(dut, L0_TABLE + 4 * ((PAGE_B_VA >> 12) & 0x3FF), pte(PAGE_B_PA, RW))
    poke(dut, L0_TABLE + 4 * ((PAGE_BAD_L0_VA >> 12) & 0x3FF), 0)
    poke(dut, ROOT_TABLE + 4 * (MEGA_VA >> 22), pte(MEGA_PA, RW))
    # A megapage whose PPN[0] is not zero is misaligned and must fault.
    poke(dut, ROOT_TABLE + 4 * (BAD_MEGA_VA >> 22), pte(MEGA_PA, RW) | (1 << 10))
    # The alternative table maps the same VA to different memory.
    poke(dut, ALT_ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), pte(INSTR_MEM_BASE, RWX))
    poke(dut, ALT_ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, RW))
    poke(dut, ALT_ROOT_TABLE + 4 * (PAGE_A_VA >> 22), pte(ALT_L0_TABLE, V))
    poke(dut, ALT_L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF), pte(PAGE_A_ALT_PA, RW))

    poke(dut, PAGE_A_PA, PAGE_A_VALUE)
    poke(dut, PAGE_A_PA + 4, PAGE_A_VALUE)
    poke(dut, PAGE_B_PA, PAGE_B_VALUE)
    poke(dut, PAGE_A_ALT_PA, PAGE_A_ALT_VALUE)
    poke(dut, MEGA_PA, MEGA_VALUE)


@cocotb.test()
async def test_walker_and_tlb(dut):
    build_dir = _build_dir()
    symbols = load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _install_tables(dut)
    for offset in range(0, 0x40, 4):
        poke(dut, RESULT + offset, 0)
    for offset in range(0, 8 * LOG_SLOTS, 4):
        poke(dut, LOG + offset, 0)
    poke(dut, LOG_COUNT, 0)
    poke(dut, DONE_ADDR, 0)
    poke(dut, MARK_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    phase = 0
    walk_reads = {}
    done = False
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        # A PTE read is a walker read of the page-table region; it may hit in the data cache.
        if int(dut.cpu_inst.mmu_walk_gnt.value):
            addr = int(dut.cpu_inst.mmu_walk_addr.value)
            if ROOT_TABLE <= addr < PT_REGION_END:
                walk_reads[phase] = walk_reads.get(phase, 0) + 1
        # A store is committed when it leaves MEM; it may stay in the data cache.
        if int(dut.cpu_inst.module_data_gnt_in.value) and int(dut.cpu_inst.module_mem_wr_en.value):
            addr = int(dut.cpu_inst.module_write_addr.value)
            data = int(dut.cpu_inst.module_wr_data_out.value)
            if addr == MARK_ADDR:
                phase = data
            elif addr == DONE_ADDR and data == DONE_VALUE:
                done = True
                break
    await RisingEdge(dut.clk)

    problems = []
    if not done:
        problems.append(f"the program did not finish (reached phase {phase})")
    for step, expected in sorted(EXPECTED_WALK_READS.items()):
        got = walk_reads.get(step, 0)
        if got != expected:
            problems.append(f"phase {step}: {got} PTE reads, expected {expected}")
    for offset, expected in sorted(EXPECTED_RESULTS.items()):
        got = peek(dut, RESULT + offset)
        if got != expected:
            problems.append(f"result +{offset} = 0x{got:08x}, expected 0x{expected:08x}")
    count = peek(dut, LOG_COUNT)
    log = [(peek(dut, LOG + 8 * i), peek(dut, LOG + 8 * i + 4)) for i in range(min(count, LOG_SLOTS))]
    expected_log = [(cause, tval) for cause, tval, _ in EXPECTED_FAULTS]
    if count != len(expected_log) or log != expected_log:
        problems.append(f"fault log {[(c, hex(t)) for c, t in log]} (count {count}), "
                        f"expected {[(c, hex(t)) for c, t in expected_log]}")
    for line in problems:
        dut._log.error(line)
    dut._log.info(f"PTE reads per phase: {dict(sorted(walk_reads.items()))}")
    assert not problems, "; ".join(problems)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir, "tlb", PROGRAM, LINKER_SCRIPT)

    run_top(
        "test_tlb",
        boot_image=nop_image(),
        extra_env={"TLB_BUILD": str(build_dir.resolve())},
    )


if __name__ == "__main__":
    runCocotbTests()
