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

    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value) & 0xFFFFFFFF
            if addr == tohost_addr and (data & 1):
                # riscv-tests convention: 1 = pass, else fail code in upper bits.
                assert data == 1, f"ISA test reported failure via tohost: 0x{data:08x}"
                return

    assert False, f"ISA test did not finish within {max_cycles} cycles"


def runCocotbTests():
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
