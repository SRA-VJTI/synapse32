"""Run a prebuilt ISA test image on the core and determine pass/fail via tohost.

Environment variables:
  ISA_HEX_FILE      : absolute path to verilog-hex image
  ISA_TOHOST_ADDR   : tohost symbol address (hex, e.g. 0x80001000)
  ISA_MAX_CYCLES    : optional max cycles (default: 200000)
"""
import os
import shutil
from pathlib import Path

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


@cocotb.test()
async def test_riscv_isa_image(dut):
    tohost_addr = int(os.environ["ISA_TOHOST_ADDR"], 16)
    max_cycles = int(os.environ.get("ISA_MAX_CYCLES", "200000"))
    trace_isa = os.environ.get("TRACE_ISA", "0") == "1"

    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        if trace_isa:
            cocotb.log.info(
                "cycle=%d pc=%#x priv=%#x mepc=%#x mcause=%#x mtval=%#x satp=%#x "
                "rd=%d wr=%d raw_wr=%d mem_wr=%d raddr=%#x waddr=%#x wdata=%#x rdata=%#x "
                "wb_en=%d wb_rd=%d wb_val=%#x lp=%d sp=%d pfaddr=%#x",
                cycle,
                int(dut.cpu_pc_out.value),
                int(dut.cpu_inst.csr_file_inst.privilege_mode.value),
                int(dut.cpu_inst.csr_file_inst.mepc.value),
                int(dut.cpu_inst.csr_file_inst.mcause.value),
                int(dut.cpu_inst.csr_file_inst.mtval.value),
                int(dut.cpu_inst.csr_file_inst.satp.value),
                int(dut.cpu_mem_read_en.value),
                int(dut.cpu_mem_write_en.value),
                int(dut.unified_mem_inst.data_wr_req.value),
                int(dut.unified_mem_inst.wr_en.value),
                int(dut.cpu_mem_read_addr.value),
                int(dut.cpu_mem_write_addr.value),
                int(dut.cpu_mem_write_data.value),
                int(dut.mem_read_data.value),
                int(dut.cpu_inst.rf_inst0_wr_en.value),
                int(dut.cpu_inst.rf_inst0_rd_in.value),
                int(dut.cpu_inst.rf_inst0_rd_value_in.value),
                int(dut.cpu_load_page_fault.value),
                int(dut.cpu_store_page_fault.value),
                int(dut.cpu_page_fault_addr.value),
            )
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value) & 0xFFFFFFFF
            if addr == tohost_addr and (data & 1):
                # riscv-tests convention: 1 = pass, else fail code in upper bits.
                assert data == 1, f"ISA test reported failure via tohost: 0x{data:08x}"
                return

    assert False, f"ISA test did not finish within {max_cycles} cycles"


def runCocotbTests():
    required_env = ("ISA_HEX_FILE", "ISA_TOHOST_ADDR")
    missing = [name for name in required_env if name not in os.environ]
    if missing:
        pytest.skip(f"Skipping ISA harness in full pytest run (missing env: {', '.join(missing)})")

    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    incl_dir = rtl_dir / "include"
    hex_file = os.environ["ISA_HEX_FILE"]

    sources = []
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith((".v", ".sv")):
                sources.append(os.path.join(root, file))

    sim_build = Path.cwd() / "sim_build" / "sim_build_riscv_isa"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_riscv_isa",
        testcase="test_riscv_isa_image",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{hex_file}"'],
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
