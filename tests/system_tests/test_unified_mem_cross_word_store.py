"""Verify unified_mem writes bytes into the correct word across word boundaries."""

import os
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb_test.simulator import run


INSTR_MEM_BASE = 0x8000_0000


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


@cocotb.test()
async def test_cross_word_store_updates_next_word(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.clk.value = 0
    dut.instr_addr.value = 0
    dut.instr_addr_p2.value = INSTR_MEM_BASE + 3
    dut.data_wr_req.value = 1
    dut.data_rd_en.value = 0
    dut.wr_en.value = 0
    dut.write_byte_enable.value = 0
    dut.wr_data.value = 0
    dut.load_type.value = 0
    dut.pte_wr_en_a.value = 0
    dut.pte_wr_addr_a.value = 0
    dut.pte_wr_value_a.value = 0
    dut.pte_wr_en_b.value = 0
    dut.pte_wr_addr_b.value = 0
    dut.pte_wr_value_b.value = 0
    dut.pte_rd_addr_a.value = 0
    dut.pte_rd_addr_b.value = 0
    dut.pte_rd_addr_c.value = 0
    dut.pte_rd_addr_d.value = 0

    dut.instr_ram[0].value = 0
    dut.instr_ram[1].value = 0

    await RisingEdge(dut.clk)

    # Simulate a 2-byte store starting at byte offset 3:
    # low byte should land in word 0 byte lane 3, high byte in word 1 byte lane 0.
    dut.wr_en.value = 1
    dut.write_byte_enable.value = 0b0011
    dut.wr_data.value = 0x0000_BBAA

    await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    dut.write_byte_enable.value = 0
    dut.wr_data.value = 0

    await RisingEdge(dut.clk)

    word0 = int(dut.instr_ram[0].value) & 0xFFFF_FFFF
    word1 = int(dut.instr_ram[1].value) & 0xFFFF_FFFF

    assert word0 == 0xAA00_0000, f"expected low byte in first word, got 0x{word0:08x}"
    assert word1 == 0x0000_00BB, f"expected high byte in second word, got 0x{word1:08x}"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl" / "mmu"
    incl_dir = repo_root / "rtl" / "include"

    sources = [str(rtl_dir / "unified_mem.v")]

    sim_build = Path.cwd() / "sim_build" / "sim_build_unified_mem_cross_word_store"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="unified_mem",
        module="test_unified_mem_cross_word_store",
        testcase="test_cross_word_store_updates_next_word",
        includes=[str(incl_dir)],
        simulator="verilator",
        compile_args=["-Wno-WIDTHTRUNC"],
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
