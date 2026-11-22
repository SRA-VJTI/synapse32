"""Ensure Linux can receive more than one UART interrupt through the PLIC.

The PLIC gateway is level-triggered: after a completion it forwards the source again if the source is still
asserted, as the UART's receive interrupt is while bytes remain in its FIFO.
"""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from support import run_unit


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
    bit_cycles = 16 * int(dut.uart_inst.baud_div.value)
    dut.rx.value = 0
    await ClockCycles(dut.clk, bit_cycles)
    for bit in range(8):
        dut.rx.value = (value >> bit) & 1
        await ClockCycles(dut.clk, bit_cycles)
    dut.rx.value = 1
    await ClockCycles(dut.clk, bit_cycles)


async def _receive_one_interrupt(dut, expected, more_waiting=False):
    for _ in range(20):
        if int(dut.external_interrupt.value):
            break
        await RisingEdge(dut.clk)
    assert int(dut.external_interrupt.value) == 1, "no external interrupt for the received byte"
    assert await _read(dut, PLIC_CLAIM_S) == 1
    assert (await _read(dut, UART_IIR)) & 0x0F == 0x04
    assert await _read(dut, UART_RBR) == expected
    await _write(dut, PLIC_CLAIM_S, 1)
    await ClockCycles(dut.clk, 2)
    if more_waiting:
        # The UART still asserts its interrupt, so the completion must make it pending again.
        assert int(dut.external_interrupt.value) == 1, (
            "a byte is still waiting in the UART, but the PLIC did not forward its interrupt again after completion")
    else:
        assert int(dut.external_interrupt.value) == 0
        assert int(dut.plic_inst.gateway_busy.value) == 0


async def _setup(dut):
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


@cocotb.test()
async def test_uart_rx_interrupt_rearms_after_each_completion(dut):
    await _setup(dut)
    await _send_byte(dut, ord("A"))
    await _receive_one_interrupt(dut, ord("A"))
    await _send_byte(dut, ord("B"))
    await _receive_one_interrupt(dut, ord("B"))


@cocotb.test()
async def test_uart_rx_interrupt_stays_pending_while_bytes_remain(dut):
    await _setup(dut)
    await _send_byte(dut, ord("C"))
    await _send_byte(dut, ord("D"))
    await _receive_one_interrupt(dut, ord("C"), more_waiting=True)
    await _receive_one_interrupt(dut, ord("D"))


def runCocotbTests():
    run_unit(
        "uart_plic_tb",
        "test_uart_plic_rearm",
        ["rtl/core_modules/uart.v", "rtl/core_modules/plic.v", "tests/testbenches/uart_plic_tb.v"],
        compile_args=["-Wno-SYMRSVDWORD"],
    )


if __name__ == "__main__":
    runCocotbTests()
