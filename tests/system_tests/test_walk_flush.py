"""SFENCE.VMA while a page-table walk is in flight.

An Sv32 walk is two dependent reads; a fence between them must drop the entry the walk would fill,
since the pointer it holds may belong to a page table nothing uses any more. sv32_mmu.v does that
with walk_aborted. This runs a program that fences while a walk is running, at every MEM_LATENCY,
and checks which page table the core actually executed from afterward.

It is not a discriminator for walk_aborted itself: the same program passes with the guard deleted,
because the stale-pointer case it guards cannot be reached from a program on this pipeline (the
walker's second read always lands before any instruction that could hold the bus finishes fetching).
What it does cover is fence ordering against a running walk. tests/manual/test_mmu_walk_flush_unit.py
remains the only proof of the guard itself.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

RESULT = 0x1000_0200
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
TRAP_LOG = 0x1000_0500
TRAP_COUNT = 0x1000_05FC
ROOT_TABLE = 0x1001_0000
L0_TABLE_OLD = 0x1001_1000
L0_TABLE_NEW = 0x1001_2000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)

PAGE_A_VA = 0x2000_0000
PAGE_B_VA = 0x2000_1000
PAGE_A_PA = 0x8001_0000
PAGE_B_OLD_PA = 0x8001_1000
PAGE_B_NEW_PA = 0x8001_2000
ROOT_ENTRY_CODE = ROOT_TABLE + 4 * (PAGE_A_VA >> 22)
SCRATCH_STORE = 0x1000_0300
NEW_PTE_SLOT = 0x1000_0310

OLD_MARKER = 0x0BAD_0BAD
NEW_MARKER = 0x600D_600D

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80
RW = V | R | W | A | D
RX = V | R | X | A | D
RWX = V | R | W | X | A | D

# The last three words of page A: the load, the store it stalls on, and the fence. Page B follows.
TAIL_OFFSET = 0xFF4

# Higher latencies move where the fence lands inside the walk.
LATENCIES = [0, 1, 2, 4]
WALK_IDLE = 0


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


def _page_b(marker: int) -> str:
    """Page B's code: record which physical page the translation ended up pointing at."""
    return f"""
        li      t2, {marker:#x}
        li      t3, {RESULT:#x}
        sw      t2, 0(t3)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
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

# ---- Page A, linked at {PAGE_A_PA:#x} and run at {PAGE_A_VA:#x}.
        .section .pagea, "ax"
page_a:
        li      t3, {SCRATCH_STORE:#x}
        sw      zero, 0(t3)            # warm the data megapage: the tail must not walk for data
        li      t0, {ROOT_ENTRY_CODE:#x}
        li      t5, {NEW_PTE_SLOT:#x}
        li      t4, {PAGE_A_VA + TAIL_OFFSET:#x}
        jr      t4

# ---- The last three words of page A; page B follows it in the address space.
        .section .pagea_end, "ax"
page_a_end:
        lw      t1, 0(t5)              # the new root PTE; the store below stalls one cycle on it
        sw      t1, 0(t0)              # the root entry now points at the other level-0 table
        sfence.vma                     # page B's walk is in flight, holding the old pointer

# ---- Page B, two versions at different physical pages; the PTE decides which one runs.
        .section .pageb_old, "ax"
page_b_old:{_page_b(OLD_MARKER)}

        .section .pageb_new, "ax"
page_b_new:{_page_b(NEW_MARKER)}
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text) }}
    . = {PAGE_A_PA:#x};
    .pagea : {{ *(.pagea) }}
    . = {PAGE_A_PA + TAIL_OFFSET:#x};
    .pagea_end : {{ *(.pagea_end) }}
    . = {PAGE_B_OLD_PA:#x};
    .pageb_old : {{ *(.pageb_old) }}
    . = {PAGE_B_NEW_PA:#x};
    .pageb_new : {{ *(.pageb_new) }}
}}
"""


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("WALK_FLUSH_BUILD", Path.cwd() / "build" / "walk_flush"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "walk_flush.S"
    lds = build_dir / "walk_flush.ld"
    elf = build_dir / "walk_flush.elf"
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
    subprocess.run(
        ["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "image.bin")],
        check=True,
    )
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
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


def _load(dut, build_dir: Path) -> None:
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE_OLD + offset, 0)
        _poke(dut, L0_TABLE_NEW + offset, 0)
    _poke(dut, ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), _pte(INSTR_MEM_BASE, RWX))
    _poke(dut, ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), _pte(DATA_MEM_BASE, RW))
    _poke(dut, ROOT_ENTRY_CODE, _pte(L0_TABLE_OLD, V))
    # The two level-0 tables map page A identically and page B differently.
    for table, page_b_pa in ((L0_TABLE_OLD, PAGE_B_OLD_PA), (L0_TABLE_NEW, PAGE_B_NEW_PA)):
        _poke(dut, table + 4 * ((PAGE_A_VA >> 12) & 0x3FF), _pte(PAGE_A_PA, RX))
        _poke(dut, table + 4 * ((PAGE_B_VA >> 12) & 0x3FF), _pte(page_b_pa, RX))
    _poke(dut, SCRATCH_STORE, 0)
    _poke(dut, NEW_PTE_SLOT, _pte(L0_TABLE_NEW, V))
    _poke(dut, RESULT, 0)
    _poke(dut, DONE_ADDR, 0)
    _poke(dut, TRAP_COUNT, 0)
    for offset in range(0, 0x80, 4):
        _poke(dut, TRAP_LOG + offset, 0)


@cocotb.test()
async def test_a_fence_during_a_walk_does_not_leave_a_stale_translation(dut):
    latency = int(os.environ["WALK_FLUSH_LATENCY"])
    build_dir = _build_dir()
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    _load(dut, build_dir)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    pte_reads = 0
    flushes = 0
    flush_during_walk = 0
    flush_after_first_read = 0
    reads_this_walk = 0
    for _ in range(40000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        walking = int(dut.mmu_inst.walk_state.value) != WALK_IDLE
        if not walking:
            reads_this_walk = 0
        if int(dut.mmu_walk_gnt.value):
            pte_reads += 1
            reads_this_walk += 1
        if int(dut.cpu_tlb_flush.value):
            flushes += 1
            # A walk is under way when software fences.
            if walking:
                flush_during_walk += 1
            # The walk has already read a PTE, so it carries a pointer the fence retires.
            if walking and reads_this_walk:
                flush_after_first_read += 1
        if (int(dut.data_write_fire.value) and int(dut.cpu_mem_write_addr.value) == DONE_ADDR
                and int(dut.cpu_mem_write_data.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)

    marker = _peek(dut, RESULT)
    traps = _peek(dut, TRAP_COUNT)
    log = [tuple(_peek(dut, TRAP_LOG + 16 * i + 4 * k) for k in range(3)) for i in range(min(traps, 6))]
    dut._log.info(
        f"latency {latency}: marker 0x{marker:08x}, {pte_reads} PTE reads, {flushes} fences, "
        f"{flush_during_walk} of them during a walk ({flush_after_first_read} after that walk had "
        f"already read a PTE), {traps} traps"
    )

    # Record for the coverage check in the last latency's run.
    (build_dir / f"coverage_lat{latency}.json").write_text(
        json.dumps({"latency": latency, "flush_during_walk": flush_during_walk,
                    "flush_after_first_read": flush_after_first_read, "marker": marker})
    )

    problems = []
    if not done:
        problems.append("the program did not finish")
    if marker == OLD_MARKER:
        problems.append("page B ran from the old mapping: a walk the fence interrupted was filled "
                        "into the TLB and outlived the flush")
    elif marker != NEW_MARKER:
        problems.append(f"page B stored 0x{marker:08x}, expected the new marker 0x{NEW_MARKER:08x}")
    if pte_reads == 0:
        problems.append("no PTE was ever read: the program did not exercise the walker")
    if traps:
        problems.append(f"{traps} unexpected traps: " + str([(c, hex(t), hex(e)) for c, t, e in log]))
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


@cocotb.test()
async def test_the_sweep_actually_fenced_during_a_walk(dut):
    """Coverage, not behaviour: without this the test above could pass by never reaching the case."""
    latency = int(os.environ["WALK_FLUSH_LATENCY"])
    if latency != LATENCIES[-1]:
        return
    build_dir = _build_dir()
    seen = {}
    carried = {}
    for candidate in LATENCIES:
        path = build_dir / f"coverage_lat{candidate}.json"
        if path.exists():
            record = json.loads(path.read_text())
            seen[candidate] = record["flush_during_walk"]
            carried[candidate] = record["flush_after_first_read"]
    dut._log.info(f"fences landing inside a walk, by latency: {seen}")
    dut._log.info(f"of those, fences landing after that walk had read a PTE: {carried}")
    assert seen, "no latency recorded coverage"
    assert any(count > 0 for count in seen.values()), (
        "no fence in the whole sweep landed while a walk was in flight, so this test is not "
        f"exercising the ordering it is written for; counts by latency: {seen}"
    )


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)
    for stale in build_dir.glob("coverage_lat*.json"):
        stale.unlink()

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_walk_flush_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_walk_flush",
            parameters={"MEM_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_walk_flush",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_walk_flush",
                "WALK_FLUSH_BUILD": str(build_dir.resolve()),
                "WALK_FLUSH_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
