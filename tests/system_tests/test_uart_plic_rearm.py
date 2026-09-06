"""Ensure Linux can receive more than one UART interrupt through the PLIC."""

import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_test.simulator import run


UART_BASE = 0x2000_0000
UART_RBR = UART_BASE
UART_IER = UART_BASE + 0x04
UART_FCR = UART_BASE + 0x08
UART_IIR = UART_BASE + 0x08
PLIC_BASE = 0x0C00_0000
PLIC_PRIORITY_1 = PLIC_BASE + 0x04
PLIC_ENABLE_S = PLIC_BASE + 0x2080
PLIC_THRESHOLD_S = PLIC_BASE + 0x201000
PLIC_CLAIM_S = PLIC_BASE + 0x201004


def _repo_root() -> Path:
    root = Path.cwd()
    while not (root / "rtl").is_dir():
        if root.parent == root:
            raise FileNotFoundError("rtl directory not found")
        root = root.parent
    return root


async def _write(dut, addr, value):
    dut.addr.value = addr
    dut.write_data.value = value
    dut.write_enable.value = 1
    dut.read_enable.value = 0
    await RisingEdge(dut.clk)
    dut.write_enable.value = 0


async def _read(dut, addr):
    dut.addr.value = addr
    dut.read_enable.value = 1
    dut.write_enable.value = 0
    await Timer(1, units="ns")
    value = int(dut.read_data.value)
    await RisingEdge(dut.clk)
    dut.read_enable.value = 0
    return value


async def _send_byte(dut, value):
    bit_cycles = int(dut.uart_inst.baud_div.value) + 1
    dut.rx.value = 0
    await ClockCycles(dut.clk, bit_cycles)
    for bit in range(8):
        dut.rx.value = (value >> bit) & 1
        await ClockCycles(dut.clk, bit_cycles)
    dut.rx.value = 1
    await ClockCycles(dut.clk, bit_cycles)


async def _receive_one_interrupt(dut, expected):
    for _ in range(20):
        if int(dut.external_interrupt.value):
            break
        await RisingEdge(dut.clk)
    assert int(dut.external_interrupt.value) == 1
    assert await _read(dut, PLIC_CLAIM_S) == 1
    assert (await _read(dut, UART_IIR)) & 0x0F == 0x04
    assert await _read(dut, UART_RBR) == expected
    await _write(dut, PLIC_CLAIM_S, 1)
    await ClockCycles(dut.clk, 2)
    assert int(dut.external_interrupt.value) == 0
    assert int(dut.plic_inst.gateway_busy_1.value) == 0


@cocotb.test()
async def test_uart_rx_interrupt_rearms_after_each_completion(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.addr.value = 0
    dut.write_data.value = 0
    dut.write_enable.value = 0
    dut.read_enable.value = 0
    dut.rx.value = 1
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0

    await _write(dut, UART_FCR, 0x07)
    await _write(dut, UART_IER, 0x01)
    await _write(dut, PLIC_PRIORITY_1, 1)
    await _write(dut, PLIC_ENABLE_S, 0x02)
    await _write(dut, PLIC_THRESHOLD_S, 0)

    await _send_byte(dut, ord("A"))
    await _receive_one_interrupt(dut, ord("A"))
    await _send_byte(dut, ord("B"))
    await _receive_one_interrupt(dut, ord("B"))


def runCocotbTests():
    root = _repo_root()
    build = Path.cwd() / "sim_build_uart_plic_rearm"
    if build.exists():
        shutil.rmtree(build)
    run(
        verilog_sources=[
            str(root / "rtl/core_modules/uart.v"),
            str(root / "rtl/core_modules/plic.v"),
            str(root / "tests/testbenches/uart_plic_tb.v"),
        ],
        toplevel="uart_plic_tb",
        module="test_uart_plic_rearm",
        testcase="test_uart_rx_interrupt_rearms_after_each_completion",
        includes=[str(root / "rtl/include")],
        simulator="verilator",
        compile_args=["-Wno-SYMRSVDWORD"],
        timescale="1ns/1ps",
        sim_build=str(build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()

