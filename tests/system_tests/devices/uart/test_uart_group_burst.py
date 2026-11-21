"""Back-to-back writes to the transmit FIFO across several 16-byte groups all reach the line."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import program_hex, run_hex_programs
from uart_programs import log, monitor_cpu_execution, UartMonitor


def run_uart_fifo_group_burst_test():
    """Send multiple 16-byte FIFO bursts, waiting on THRE between groups."""

    poll_thre = [0x01412083, 0x0200f093, 0xfe008ce3]
    message = "ABCDEFGHIJKLMNOPabcdefghijklmnop"
    assert len(message) == 32

    instr_mem = [
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)

        # DLL=1, DLH=0
        0x00100093,  # addi x1, x0, 1
        0x00112023,  # sw x1, 0(x2)
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)

        # LCR=0x03 (DLAB=0), FCR=0x07
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)
    ]

    for group_start in range(0, len(message), 16):
        instr_mem.extend(poll_thre)
        for ch in message[group_start:group_start + 16]:
            instr_mem.extend([
                0x00000093 | (ord(ch) << 20),  # addi x1, x0, imm
                0x00112023,                    # sw x1, 0(x2)
            ])

    instr_mem.extend([
        # Poll until TEMT reports the transmitter is fully empty.
        0x01412083,  # lw x1, 20(x2)
        0x0400f093,  # andi x1, x1, 64
        0xfe008ce3,  # beq x1, x0, -8

        0x00100093,  # addi x1, x0, 1
        0x0011a023,  # sw x1, 0(x3)
        0x0000006f,
    ])

    test_name = "uart_fifo_group_burst"
    hex_file = program_hex("uart_group_burst", test_name, instr_mem, 256)
    return test_name, hex_file


@cocotb.test()
async def test_uart_fifo_group_burst(dut):
    """Verify FIFO bursts preserve data across multiple 16-byte groups."""
    log.info("Starting UART FIFO group burst test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=3125000)
    cocotb.start_soon(uart_monitor.start_monitoring())

    mem_writes = await monitor_cpu_execution(dut, "uart_fifo_group_burst", max_cycles=9000)
    await ClockCycles(dut.clk, 750)

    completion_found = 0x02000000 in mem_writes and mem_writes[0x02000000] == 1
    assert completion_found, "Program completion flag not found"

    received_string = uart_monitor.get_received_string()
    expected = "ABCDEFGHIJKLMNOPabcdefghijklmnop"
    log.info(f"UART received: '{received_string}'")
    assert expected in received_string, (
        f"Expected exact FIFO group text '{expected}', got '{received_string}'"
    )

    log.info("UART FIFO group burst test passed!")


def runCocotbTests():
    run_hex_programs("test_uart_group_burst", [
        ("uart_fifo_group_burst", run_uart_fifo_group_burst_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
