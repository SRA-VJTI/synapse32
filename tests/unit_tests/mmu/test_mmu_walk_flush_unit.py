"""A fence that lands while a page-table walk is in flight.

A walk interrupted by SFENCE.VMA may carry a stale entry, so it must not fill the TLB; the access
walks again and sees what software wrote. This drives sv32_mmu directly because the fence has to
land between the walk's last PTE read and its fill, which a program cannot time. Removing the guard
from sv32_mmu.v makes this test fail.
"""

import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_test.simulator import run

ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
VADDR = 0x2000_1000

V, R, W, A, D = 0x01, 0x02, 0x04, 0x40, 0x80
RW = V | R | W | A | D

OLD_PA = 0x1000_1000
NEW_PA = 0x1000_5000
PRIV_S = 1


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


def _repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _idle(dut) -> None:
    dut.flush_tlb.value = 0
    dut.satp.value = SATP
    dut.data_sum.value = 0
    dut.data_mxr.value = 0
    dut.instr_translate_enable.value = 0
    dut.instr_virtual_addr.value = 0
    dut.instr_priv_mode.value = PRIV_S
    dut.data_translate_enable.value = 0
    dut.data_virtual_addr.value = 0
    dut.data_rd_en.value = 0
    dut.data_wr_req.value = 0
    dut.data_priv_mode.value = PRIV_S
    dut.walk_gnt.value = 0
    dut.walk_rvalid.value = 0
    dut.walk_rdata.value = 0


async def _request_load(dut, vaddr: int) -> None:
    dut.data_translate_enable.value = 1
    dut.data_virtual_addr.value = vaddr
    dut.data_rd_en.value = 1
    dut.data_wr_req.value = 0


async def _settle(dut) -> None:
    """Let the cycle's combinational logic settle before sampling (no ReadOnly polling)."""
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")


async def _answer_walk(dut, value: int, flush_now: bool = False) -> int:
    """Grant the walk's request and return the PTE it asked for; optionally fence in that cycle."""
    addr = 0
    for _ in range(20):
        if int(dut.walk_req.value):
            addr = int(dut.walk_addr.value)
            break
        await _settle(dut)
    else:
        raise AssertionError("the walker never asked for a page-table entry")
    dut.walk_gnt.value = 1
    dut.walk_rvalid.value = 1
    dut.walk_rdata.value = value
    if flush_now:
        dut.flush_tlb.value = 1
    await _settle(dut)
    dut.walk_gnt.value = 0
    dut.walk_rvalid.value = 0
    dut.flush_tlb.value = 0
    await _settle(dut)
    return addr


@cocotb.test()
async def test_fence_during_a_walk_discards_its_result(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _idle(dut)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    await _settle(dut)

    problems = []

    # A walk a fence interrupts must not fill the TLB with the entry software just replaced.
    await _request_load(dut, VADDR)
    level1 = await _answer_walk(dut, _pte(L0_TABLE, V))
    level0 = await _answer_walk(dut, _pte(OLD_PA, RW), flush_now=True)
    if level1 != ROOT_TABLE + 4 * (VADDR >> 22):
        problems.append(f"level 1 read 0x{level1:08x}, expected the root entry for the address")
    if level0 != L0_TABLE + 4 * ((VADDR >> 12) & 0x3FF):
        problems.append(f"level 0 read 0x{level0:08x}, expected the leaf entry for the address")

    # Only the module's own ports are observed: a filled TLB entry would answer immediately.
    if int(dut.data_ready.value):
        problems.append("the translation was ready after a fence interrupted its walk, "
                        "so the discarded walk was filled into the TLB")
    if not int(dut.walk_req.value):
        problems.append("no new walk was started after the fence discarded the first one")

    # The access walks again and now sees what software wrote.
    await _answer_walk(dut, _pte(L0_TABLE, V))
    await _answer_walk(dut, _pte(NEW_PA, RW))
    if not int(dut.data_ready.value):
        problems.append("the retried walk did not produce a translation")
    got = int(dut.data_phys_addr.value)
    if got != NEW_PA:
        problems.append(f"translated to 0x{got:08x}, expected the new mapping 0x{NEW_PA:08x}")

    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


def runCocotbTests():
    root = _repo_root()
    build = Path.cwd() / "sim_build" / "sim_build_mmu_walk_flush_unit"
    if build.exists():
        shutil.rmtree(build)
    run(
        verilog_sources=[
            str(root / "rtl" / "mmu" / "sv32_mmu.v"),
            str(root / "rtl" / "mmu" / "sv32_tlb.v"),
            str(root / "rtl" / "mmu" / "sv32_instr_check.v"),
            str(root / "rtl" / "mmu" / "sv32_data_check.v"),
        ],
        toplevel="sv32_mmu",
        module="test_mmu_walk_flush_unit",
        includes=[str(root / "rtl" / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "sv32_mmu",
            "MODULE": "test_mmu_walk_flush_unit",
            "COCOTB_TOPLEVEL": "sv32_mmu",
            "COCOTB_TEST_MODULES": "test_mmu_walk_flush_unit",
        },
    )


if __name__ == "__main__":
    runCocotbTests()
