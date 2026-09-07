"""Focused NS16550 receive-FIFO regression tests."""

import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_test.simulator import run


UART_BASE = 0x2000_0000
UART_RBR = UART_BASE
UART_THR = UART_BASE
UART_IER = UART_BASE + 0x04
UART_FCR = UART_BASE + 0x08
UART_IIR = UART_BASE + 0x08
UART_LSR = UART_BASE + 0x14


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
    bit_cycles = int(dut.baud_div.value) + 1
    dut.rx.value = 0
    await ClockCycles(dut.clk, bit_cycles)
    for bit in range(8):
        dut.rx.value = (value >> bit) & 1
        await ClockCycles(dut.clk, bit_cycles)
    dut.rx.value = 1
    await ClockCycles(dut.clk, bit_cycles)


@cocotb.test()
async def test_rx_fifo_preserves_burst_order(dut):
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

    for value in (0x41, 0x42, 0x43):
        await _send_byte(dut, value)

    assert int(dut.rx_fifo_count.value) == 3
    assert int(dut.interrupt.value) == 1
    assert (await _read(dut, UART_LSR)) & 0x01
    assert [await _read(dut, UART_RBR) for _ in range(3)] == [0x41, 0x42, 0x43]
    await Timer(1, units="ns")
    assert int(dut.rx_fifo_count.value) == 0
    assert int(dut.interrupt.value) == 0

    # Reproduce simultaneous RX and THRE interrupts. Reading IIR while RX
    # has priority must not consume the lower-priority THRE interrupt.
    await _write(dut, UART_IER, 0x03)
    await _write(dut, UART_THR, 0x55)
    for _ in range(100):
        if int(dut.thre_irq.value):
            break
        await RisingEdge(dut.clk)
    assert int(dut.thre_irq.value) == 1

    await _send_byte(dut, 0x44)
    assert int(dut.interrupt.value) == 1
    assert (await _read(dut, UART_IIR)) & 0x0F == 0x04
    assert int(dut.thre_irq.value) == 1

    assert await _read(dut, UART_RBR) == 0x44
    await Timer(1, units="ns")
    assert int(dut.interrupt.value) == 1
    assert (await _read(dut, UART_IIR)) & 0x0F == 0x02
    await Timer(1, units="ns")
    assert int(dut.thre_irq.value) == 0
    assert int(dut.interrupt.value) == 0


def runCocotbTests():
    root = _repo_root()
    build = Path.cwd() / "sim_build_uart_rx_fifo"
    if build.exists():
        shutil.rmtree(build)
    run(
        verilog_sources=[str(root / "rtl" / "core_modules" / "uart.v")],
        toplevel="uart",
        module="test_uart_rx_fifo",
        testcase="test_rx_fifo_preserves_burst_order",
        includes=[str(root / "rtl" / "include")],
        simulator="verilator",
        compile_args=["-Wno-SYMRSVDWORD"],
        timescale="1ns/1ps",
        sim_build=str(build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
