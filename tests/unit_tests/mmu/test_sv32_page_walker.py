"""Focused Sv32 physical-address-width validation tests."""

import shutil
from pathlib import Path

import cocotb
from cocotb.triggers import Timer
from cocotb_test.simulator import run


def _repo_root() -> Path:
    root = Path.cwd()
    while not (root / "rtl").is_dir():
        if root.parent == root:
            raise FileNotFoundError("rtl directory not found")
        root = root.parent
    return root


@cocotb.test()
async def test_rejects_ppn_above_32_bit_physical_space(dut):
    dut.translate_enable.value = 1
    dut.virtual_addr.value = 0x1234_5000
    dut.satp.value = 0
    dut.l1_pte_addr.value = 0x8000_0000
    dut.l0_pte_addr.value = 0x8000_1000
    dut.l1_pte_backed.value = 1
    dut.l0_pte_backed.value = 1

    # Valid readable L1 superpage except that PPN[21:20] addresses >4 GiB.
    dut.l1_pte_value.value = 0x4000_0003
    dut.l0_pte_value.value = 0
    await Timer(1, units="ns")
    assert int(dut.addr_valid.value) == 0

    # Valid L1 pointer followed by an otherwise-valid high-PPN L0 leaf.
    dut.l1_pte_value.value = 0x2000_0001
    dut.l0_pte_value.value = 0x8000_0003
    await Timer(1, units="ns")
    assert int(dut.addr_valid.value) == 0


def runCocotbTests():
    root = _repo_root()
    build = Path.cwd() / "sim_build_sv32_page_walker"
    if build.exists():
        shutil.rmtree(build)
    run(
        verilog_sources=[str(root / "rtl" / "mmu" / "sv32_page_walker.v")],
        toplevel="sv32_page_walker",
        module="test_sv32_page_walker",
        testcase="test_rejects_ppn_above_32_bit_physical_space",
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
