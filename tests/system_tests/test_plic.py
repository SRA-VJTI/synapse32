import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_test.simulator import run


PLIC_BASE = 0x0C000000
PRIORITY_1_ADDR = PLIC_BASE + 0x000004
PENDING_ADDR = PLIC_BASE + 0x001000
ENABLE_M_ADDR = PLIC_BASE + 0x002000
ENABLE_S_ADDR = PLIC_BASE + 0x002080
THRESHOLD_M_ADDR = PLIC_BASE + 0x200000
CLAIM_M_ADDR = PLIC_BASE + 0x200004
THRESHOLD_S_ADDR = PLIC_BASE + 0x201000
CLAIM_S_ADDR = PLIC_BASE + 0x201004


async def _write_reg(dut, addr, value):
    dut.addr.value = addr
    dut.write_data.value = value
    dut.write_enable.value = 1
    dut.read_enable.value = 0
    await RisingEdge(dut.clk)
    dut.write_enable.value = 0


async def _read_reg(dut, addr):
    dut.addr.value = addr
    dut.read_enable.value = 1
    dut.write_enable.value = 0
    await RisingEdge(dut.clk)
    value = int(dut.read_data.value)
    dut.read_enable.value = 0
    return value


async def _reset_and_configure(dut):
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.addr.value = 0
    dut.write_data.value = 0
    dut.write_enable.value = 0
    dut.read_enable.value = 0
    dut.source_irq.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 1)

    await _write_reg(dut, PRIORITY_1_ADDR, 1)
    await _write_reg(dut, ENABLE_S_ADDR, 0x2)
    await _write_reg(dut, THRESHOLD_S_ADDR, 0)
    await _write_reg(dut, ENABLE_M_ADDR, 0)
    await _write_reg(dut, THRESHOLD_M_ADDR, 0)


@cocotb.test()
async def test_level_irq_rearms_after_completion(dut):
    await _reset_and_configure(dut)

    assert int(dut.external_interrupt.value) == 0
    assert await _read_reg(dut, PENDING_ADDR) == 0

    dut.source_irq.value = 1
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")

    assert int(dut.external_interrupt.value) == 1
    assert await _read_reg(dut, PENDING_ADDR) == 0x2

    claim = await _read_reg(dut, CLAIM_S_ADDR)
    assert claim == 1
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")
    assert int(dut.external_interrupt.value) == 0
    assert await _read_reg(dut, PENDING_ADDR) == 0

    await _write_reg(dut, CLAIM_S_ADDR, 1)
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")
    assert int(dut.external_interrupt.value) == 1
    assert await _read_reg(dut, PENDING_ADDR) == 0x2

    claim = await _read_reg(dut, CLAIM_S_ADDR)
    assert claim == 1
    dut.source_irq.value = 0
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")
    await _write_reg(dut, CLAIM_S_ADDR, 1)
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")

    assert int(dut.external_interrupt.value) == 0
    assert await _read_reg(dut, PENDING_ADDR) == 0
    assert await _read_reg(dut, CLAIM_S_ADDR) == 0


@cocotb.test()
async def test_stale_completion_preserves_unclaimed_pending_irq(dut):
    await _reset_and_configure(dut)

    dut.source_irq.value = 1
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")
    assert int(dut.external_interrupt.value) == 1
    assert await _read_reg(dut, PENDING_ADDR) == 0x2

    # A duplicate/stale completion may arrive after the source level falls,
    # but it must not discard a request that software has not claimed yet.
    dut.source_irq.value = 0
    await ClockCycles(dut.clk, 1)
    await _write_reg(dut, CLAIM_M_ADDR, 1)
    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")

    assert int(dut.external_interrupt.value) == 1
    assert await _read_reg(dut, PENDING_ADDR) == 0x2
    assert await _read_reg(dut, CLAIM_S_ADDR) == 1

    await ClockCycles(dut.clk, 1)
    await Timer(1, units="ns")
    assert int(dut.external_interrupt.value) == 0
    assert await _read_reg(dut, PENDING_ADDR) == 0


def runCocotbTests():
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found")
        root_dir = os.path.dirname(root_dir)

    rtl_dir = Path(root_dir) / "rtl"
    incl_dir = rtl_dir / "include"
    sim_build_dir = Path.cwd() / "sim_build_plic"
    if sim_build_dir.exists():
        import shutil
        shutil.rmtree(sim_build_dir)

    run(
        verilog_sources=[str(rtl_dir / "core_modules" / "plic.v")],
        toplevel="plic",
        module="test_plic",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build_dir),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "plic",
            "MODULE": "test_plic",
            "COCOTB_TOPLEVEL": "plic",
            "COCOTB_TEST_MODULES": "test_plic",
        },
    )


if __name__ == "__main__":
    runCocotbTests()
