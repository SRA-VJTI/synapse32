"""A fence that lands while a page-table walk is in flight.

A walk interrupted by SFENCE.VMA may carry a stale entry, so it must not fill the TLB; the access
walks again and sees what software wrote. The fence may land in the cycle the PTE arrives, or while
the walker still waits for it (sv32_mmu.v remembers that in walk_aborted). This drives sv32_mmu
directly because a program cannot time either: the walker waits for an empty store buffer, so the
PTE store before a fence always lands before the walk's first read.
"""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from support import pte, run_unit

ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
VADDR = 0x2000_1000

V, R, W, A, D = 0x01, 0x02, 0x04, 0x40, 0x80
RW = V | R | W | A | D

OLD_PA = 0x1000_1000
NEW_PA = 0x1000_5000
PRIV_S = 1


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


async def _fence_while_waiting(dut, value: int) -> int:
    """Grant the walk's request, fence while its PTE is still outstanding, then answer it."""
    addr = 0
    for _ in range(20):
        if int(dut.walk_req.value):
            addr = int(dut.walk_addr.value)
            break
        await _settle(dut)
    else:
        raise AssertionError("the walker never asked for a page-table entry")
    dut.walk_gnt.value = 1
    await _settle(dut)
    dut.walk_gnt.value = 0
    dut.flush_tlb.value = 1
    await _settle(dut)
    dut.flush_tlb.value = 0
    dut.walk_rvalid.value = 1
    dut.walk_rdata.value = value
    await _settle(dut)
    dut.walk_rvalid.value = 0
    await _settle(dut)
    return addr


async def _reset(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _idle(dut)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    await _settle(dut)


def _check_retry(dut, problems: list, level1: int, level0: int) -> None:
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


async def _retry_sees_new_mapping(dut, problems: list) -> None:
    await _answer_walk(dut, pte(L0_TABLE, V))
    await _answer_walk(dut, pte(NEW_PA, RW))
    if not int(dut.data_ready.value):
        problems.append("the retried walk did not produce a translation")
    got = int(dut.data_phys_addr.value)
    if got != NEW_PA:
        problems.append(f"translated to 0x{got:08x}, expected the new mapping 0x{NEW_PA:08x}")


@cocotb.test()
async def test_fence_during_a_walk_discards_its_result(dut):
    await _reset(dut)
    problems = []

    # A walk a fence interrupts must not fill the TLB with the entry software just replaced.
    await _request_load(dut, VADDR)
    level1 = await _answer_walk(dut, pte(L0_TABLE, V))
    level0 = await _answer_walk(dut, pte(OLD_PA, RW), flush_now=True)
    _check_retry(dut, problems, level1, level0)
    # The access walks again and now sees what software wrote.
    if not problems:
        await _retry_sees_new_mapping(dut, problems)
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


@cocotb.test()
async def test_fence_while_a_walk_waits_for_its_pte_discards_its_result(dut):
    await _reset(dut)
    problems = []
    await _request_load(dut, VADDR)
    level1 = await _answer_walk(dut, pte(L0_TABLE, V))
    level0 = await _fence_while_waiting(dut, pte(OLD_PA, RW))
    _check_retry(dut, problems, level1, level0)
    if not problems:
        await _retry_sees_new_mapping(dut, problems)
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


def runCocotbTests():
    run_unit(
        "sv32_mmu",
        "test_mmu_walk_flush_unit",
        ["rtl/mmu/sv32_mmu.v", "rtl/mmu/sv32_tlb.v", "rtl/mmu/sv32_instr_check.v", "rtl/mmu/sv32_data_check.v"],
    )


if __name__ == "__main__":
    runCocotbTests()
