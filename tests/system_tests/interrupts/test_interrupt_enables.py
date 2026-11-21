"""mtvec, mie and mstatus read back what was written, and mip shows nothing pending."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import monitor_execution, program_hex, run_hex_programs


def run_interrupt_setup_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x08000093,  # addi x1, x0, 128      # Load immediate: Set x1 to 0x80 (MTIE bit - machine timer interrupt enable)
        0x30409073,  # csrw mie, x1          # Write CSR: Set mie (machine interrupt enable) to value in x1
        0x00800193,  # addi x3, x0, 8        # Load immediate: Set x3 to 0x8 (MIE bit - global machine interrupt enable)
        0x30019073,  # csrw mstatus, x3      # Write CSR: Set mstatus to value in x3 (enable interrupts)
        0x30502273,  # csrr x4, mtvec        # Read CSR: Read mtvec value into x4
        0x030002b7,  # lui x5 0x3000         # Load immediate: Set x5 to memory base address 0x03000000
        0x0042a023,  # sw x4, 0(x5)          # Store word: Store mtvec value (x4) to memory at x5+0
        0x30402373,  # csrr x6, mie          # Read CSR: Read mie value into x6
        0x0062a223,  # sw x6, 4(x5)          # Store word: Store mie value (x6) to memory at x5+4
        0x30002473,  # csrr x8, mstatus      # Read CSR: Read mstatus value into x8
        0x0082a423,  # sw x8, 8(x5)          # Store word: Store mstatus value (x8) to memory at x5+8
        0x34402573,  # csrr x10, mip         # Read CSR: Read mip (machine interrupt pending) into x10
        0x00a2a623,  # sw x10, 12(x5)        # Store word: Store mip value (x10) to memory at x5+12
        0x00100093,  # addi x1, x0, 1        # Load immediate: Set x1 to 1 (completion flag)
        0x0012a823,  # sw x1, 16(x5)         # Store word: Store completion flag (x1) to memory at x5+16
    ]
    test_name = "interrupt_setup"
    hex_file = program_hex("interrupt_enables", test_name, instr_mem, 512)
    return test_name, hex_file


@cocotb.test()
async def test_interrupt_setup(dut):
    """Test interrupt enable setup"""
    print("Starting interrupt setup test...")
    
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "interrupt_setup", max_cycles=80)
    
    # Verify results
    expected_memory = {
        0x03000000: 0x10000000,  # mtvec value
        0x03000004: 0x80,        # mie value (MTIE enabled)
        0x03000008: 0x8,         # mstatus value (MIE enabled)
        0x0300000C: 0x0,         # mip value (no interrupts pending)
        0x03000010: 0x1,         # completion flag
    }
    
    print("\nVerifying interrupt setup from memory writes:")
    for addr, expected in expected_memory.items():
        if addr in mem_writes:
            actual = mem_writes[addr]
            print(f"Memory[0x{addr:08x}]: expected=0x{expected:08x}, actual=0x{actual:08x}")
            assert actual == expected, f"Memory value mismatch at 0x{addr:08x}: expected 0x{expected:08x}, got 0x{actual:08x}"
        else:
            raise AssertionError(f"Memory[0x{addr:08x}] was never written")
    
    print("Interrupt setup test passed!")


def runCocotbTests():
    run_hex_programs("test_interrupt_enables", [
        ("interrupt_setup", run_interrupt_setup_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
