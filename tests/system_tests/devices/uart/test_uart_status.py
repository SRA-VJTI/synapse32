"""The UART line status register: THRE and TEMT with the FIFO off, and while bytes wait in the FIFO."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import program_hex, run_hex_programs
from uart_programs import log, monitor_cpu_execution, UartMonitor


def run_uart_status_test():
    """Create assembly program that tests UART status register"""
    
    # UART configuration - same baud rate as hello test
    # Baud divisor 1: 50 MHz / (16 x 1) = 3,125,000 baud
    BAUD_DIVISOR = 1
    
    # NS16550 poll: lw x1,20(x2); andi x1,x1,32; beq x1,x0,-8
    POLL = [0x01412083, 0x0200f093, 0xfe008ce3]

    instr_mem = [
        # Initialize registers
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)         # LCR

        # DLL=1, DLH=0
        0x00100093,  # addi x1, x0, 1
        0x00112023,  # sw x1, 0(x2)          # DLL
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)          # DLH

        # LCR=0x03 (DLAB=0)
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)         # LCR

        # Read LSR (initial: should show THRE=1, i.e. ready)
        0x01412083,  # lw x1, 20(x2)         # x1 = LSR
        0x0011a023,  # sw x1, 0(x3)          # store to memory[base+0]

        # Write 'A'
        0x04100093,  # addi x1, x0, 65
        0x00112023,  # sw x1, 0(x2)          # THR = 'A'

        # Read LSR immediately after write (THRE may be 0 = busy)
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)          # store to memory[base+4]

        # Wait until THRE=1
        *POLL,

        # Read final LSR (should show THRE=1 again)
        0x01412083,  # lw x1, 20(x2)
        0x0011a423,  # sw x1, 8(x3)          # store to memory[base+8]

        # Store completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a623,  # sw x1, 12(x3)         # memory[base+12] = 1

        # Infinite loop
        0x0000006f,
    ]
    
    test_name = "uart_status"
    hex_file = program_hex("uart_status", test_name, instr_mem, 256)
    return test_name, hex_file

def run_uart_fifo_status_test():
    """Verify FIFO mode drives THRE/TEMT low once data is queued."""

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

        # Read initial LSR (expect THRE=1/TEMT=1)
        0x01412083,  # lw x1, 20(x2)
        0x0011a023,  # sw x1, 0(x3)

        # Queue two bytes and sample LSR again: the second byte stays queued while the first is sent,
        # whatever the baud phase at which the first leaves the FIFO.
        0x04100093,  # addi x1, x0, 'A'
        0x00112023,  # sw x1, 0(x2)
        0x04200093,  # addi x1, x0, 'B'
        0x00112023,  # sw x1, 0(x2)
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)

        # Wait until transmitter fully empties, then sample once more.
        0x01412083,  # lw x1, 20(x2)
        0x0400f093,  # andi x1, x1, 64
        0xfe008ce3,  # beq x1, x0, -8
        0x01412083,  # lw x1, 20(x2)
        0x0011a423,  # sw x1, 8(x3)

        # Completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a623,  # sw x1, 12(x3)
        0x0000006f,
    ]

    test_name = "uart_fifo_status"
    hex_file = program_hex("uart_status", test_name, instr_mem, 256)
    return test_name, hex_file


@cocotb.test()
async def test_uart_status_register(dut):
    """Test UART status register functionality"""
    log.info("Starting UART status register test...")
    
    # Start clock (50MHz)
    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Start UART monitor at 3.125 Mbaud (same as hello test)
    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=3125000)
    monitor_task = cocotb.start_soon(uart_monitor.start_monitoring())
    
    # Monitor execution (reduced cycles due to faster baud rate)
    mem_writes = await monitor_cpu_execution(dut, "uart_status", max_cycles=2200)
    
    log.info("\nVerifying UART status register behavior:")
    log.info("Memory writes:", mem_writes)
    
    # Check for completion flag
    completion_found = 0x0200000C in mem_writes and mem_writes[0x0200000C] == 1
    assert completion_found, "Program completion flag not found"
    
    # Verify LSR values (NS16550: bit5=THRE=1 means TX ready)
    if 0x02000000 in mem_writes:
        initial_lsr = mem_writes[0x02000000]
        log.info(f"Initial LSR: 0x{initial_lsr:08x}")
        assert (initial_lsr & 0x20) != 0, "Initial LSR should show THRE=1 (TX ready)"

    if 0x02000004 in mem_writes:
        busy_lsr = mem_writes[0x02000004]
        log.info(f"LSR after write: 0x{busy_lsr:08x}")
        # May or may not be ready depending on timing

    if 0x02000008 in mem_writes:
        final_lsr = mem_writes[0x02000008]
        log.info(f"Final LSR: 0x{final_lsr:08x}")
        assert (final_lsr & 0x20) != 0, "Final LSR should show THRE=1 (TX ready)"
    
    # Verify we received the 'A' character
    received_string = uart_monitor.get_received_string()
    log.info(f"UART received: '{received_string}'")
    assert 'A' in received_string, f"Expected 'A' in UART output, got '{received_string}'"
    
    log.info("UART status register test passed!")


@cocotb.test()
async def test_uart_fifo_status(dut):
    """Verify FIFO mode clears THRE/TEMT while bytes remain queued."""
    log.info("Starting UART FIFO status test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = await monitor_cpu_execution(dut, "uart_fifo_status", max_cycles=3000)

    initial_lsr = mem_writes.get(0x02000000)
    queued_lsr = mem_writes.get(0x02000004)
    final_lsr = mem_writes.get(0x02000008)
    completion = mem_writes.get(0x0200000C)

    assert completion == 1, "Program completion flag not found"
    assert initial_lsr is not None and (initial_lsr & 0x60) == 0x60, (
        f"Expected THRE/TEMT high before FIFO write, got 0x{initial_lsr:02x}"
    )
    assert queued_lsr is not None and (queued_lsr & 0x60) == 0x00, (
        f"Expected THRE/TEMT low with queued FIFO data, got 0x{queued_lsr:02x}"
    )
    assert final_lsr is not None and (final_lsr & 0x60) == 0x60, (
        f"Expected THRE/TEMT high after drain, got 0x{final_lsr:02x}"
    )

    log.info("UART FIFO status test passed!")


def runCocotbTests():
    run_hex_programs("test_uart_status", [
        ("uart_status_register", run_uart_status_test),
        ("uart_fifo_status", run_uart_fifo_status_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
