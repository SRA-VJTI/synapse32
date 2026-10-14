"""SFENCE.VMA orders what comes after it.

The core fetches ahead, so an instruction on the next page may already be fetched under the old
mapping when the fence executes; it must be discarded and fetched again.

The program puts the store and the fence in the last words of a page, so the next page is being
fetched while they execute. The store repoints that page at different code; the marker it writes
says which mapping the core actually used.
"""

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
FENCE_OFFSET = 0xFF4
GOTO_B_OFFSET = 0xFF8
JUMP_OFFSET = 0xFFC


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
        li      t0, {L0_ENTRY_B:#x}
        li      t1, {_pte(PAGE_B_NEW_PA, RX):#x}
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

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text) }}
    . = {PAGE_A_PA:#x};
    .pagea : {{ *(.pagea) }}
    . = {PAGE_A_PA + STORE_OFFSET:#x};
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
    return Path(os.environ.get("SFENCE_ORDER_BUILD", Path.cwd() / "build" / "sfence_ordering"))


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
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


@cocotb.test()
async def test_instructions_after_a_fence_use_the_new_mapping(dut):
    build_dir = _build_dir()
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE + offset, 0)
    _poke(dut, ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), _pte(INSTR_MEM_BASE, RWX))
    _poke(dut, ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), _pte(DATA_MEM_BASE, RW))
    _poke(dut, ROOT_TABLE + 4 * (PAGE_A_VA >> 22), _pte(L0_TABLE, V))
    _poke(dut, L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF), _pte(PAGE_A_PA, RX))
    _poke(dut, L0_ENTRY_B, _pte(PAGE_B_OLD_PA, RX))
    _poke(dut, RESULT, 0)
    _poke(dut, DONE_ADDR, 0)
    _poke(dut, TRAP_COUNT, 0)
    for offset in range(0, 0x80, 4):
        _poke(dut, TRAP_LOG + offset, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    walks_seen = 0
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.mmu_walk_gnt.value):
            walks_seen += 1
        if (int(dut.data_write_fire.value) and int(dut.cpu_mem_write_addr.value) == DONE_ADDR
                and int(dut.cpu_mem_write_data.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)

    marker = _peek(dut, RESULT)
    problems = []
    if not done:
        problems.append("the program did not finish")
    if marker == OLD_MARKER:
        problems.append("page B ran from the old mapping: a walk that a fence interrupted was "
                        "filled into the TLB")
    elif marker != NEW_MARKER:
        problems.append(f"page B stored 0x{marker:08x}, expected the new marker 0x{NEW_MARKER:08x}")
    if walks_seen == 0:
        problems.append("no page-table entry was ever read: the program did not exercise the walker")
    for line in problems:
        dut._log.error(line)
    traps = _peek(dut, TRAP_COUNT)
    log = [tuple(_peek(dut, TRAP_LOG + 16 * i + 4 * k) for k in range(3)) for i in range(min(traps, 6))]
    dut._log.info(f"marker 0x{marker:08x} after {walks_seen} PTE reads, {traps} traps: "
                  + str([(c, hex(t), hex(e)) for c, t, e in log]))
    if traps:
        problems.append(f"{traps} unexpected traps: " + str([(c, hex(t), hex(e)) for c, t, e in log]))
    assert not problems, "; ".join(problems)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_sfence_ordering"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_sfence_ordering",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_sfence_ordering",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_sfence_ordering",
            "SFENCE_ORDER_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
