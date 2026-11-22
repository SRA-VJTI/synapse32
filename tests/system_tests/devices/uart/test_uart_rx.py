"""A byte received on the RX line sets LSR.DR and is read through RBR."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import program_hex, run_hex_programs
from uart_programs import log, monitor_cpu_execution


async def uart_send_byte(dut, byte, baud_cycles=None):
    """Drive one 8N1 byte using the divisor currently programmed in the DUT."""
    if baud_cycles is None:
        baud_cycles = 16 * int(dut.uart_inst.baud_div.value)
    dut.uart_rx.value = 0
    await ClockCycles(dut.clk, baud_cycles)
    for bit in range(8):
        dut.uart_rx.value = (byte >> bit) & 1
        await ClockCycles(dut.clk, baud_cycles)
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, baud_cycles)

def run_uart_rx_test():
    """Create assembly that waits for one RX byte and stores it to memory."""

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

        # Poll LSR[0] (DR) until data ready
        0x01412083,  # lw x1, 20(x2)
        0x0010f093,  # andi x1, x1, 1
        0xfe008ce3,  # beq x1, x0, -8

        # Read RBR and store to memory
        0x00012083,  # lw x1, 0(x2)
        0x0011a023,  # sw x1, 0(x3)

        # Read LSR again and store to verify DR cleared
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)

        # Completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a423,  # sw x1, 8(x3)

        # Infinite loop
        0x0000006f,
    ]

    test_name = "uart_rx"
    hex_file = program_hex("uart_rx", test_name, instr_mem, 256)
    return test_name, hex_file


@cocotb.test()
async def test_uart_rx(dut):
    """Verify a byte driven on uart_rx sets DR and is readable through RBR."""
    log.info("Starting UART RX test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    async def inject_rx_byte():
        # Let the test program finish UART init and enter the DR poll loop.
        await ClockCycles(dut.clk, 200)
        await uart_send_byte(dut, ord('Z'))

    cocotb.start_soon(inject_rx_byte())

    mem_writes = await monitor_cpu_execution(dut, "uart_rx", max_cycles=3000)

    received = mem_writes.get(0x02000000)
    lsr_after = mem_writes.get(0x02000004)
    completion = mem_writes.get(0x02000008)

    assert completion == 1, "Program completion flag not found"
    assert received == ord('Z'), f"Expected received byte 0x5a, got {received!r}"
    assert lsr_after is not None and (lsr_after & 0x01) == 0, (
        f"Expected DR clear after RBR read, got LSR=0x{lsr_after:02x}"
    )

    log.info("UART RX test passed!")


def runCocotbTests():
    run_hex_programs("test_uart_rx", [
        ("uart_rx", run_uart_rx_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
