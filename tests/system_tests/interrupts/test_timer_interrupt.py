"""The CLINT timer interrupt reaches its M-mode handler."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import monitor_execution, program_hex, run_hex_programs


def run_timer_interrupt_test():
    """Create assembly program that sets up timer and waits for interrupt"""
    
    # Main program - sets up timer and waits for interrupt
    main_program = [
        # Setup interrupt vector at instruction-memory base + 0x100.
        0x80000137,  # lui x2, 0x80000       # Set x2 = 0x80000000
        0x10010113,  # addi x2, x2, 0x100    # x2 = 0x80000100 (handler at instruction 64)
        0x30511073,  # csrw mtvec, x2        # Set mtvec to the handler address
        
        # Enable timer interrupts  
        0x08000093,  # addi x1, x0, 128      # Set x1 = 0x80 (MTIE bit)
        0x30409073,  # csrw mie, x1          # Enable timer interrupts in MIE
        
        # Enable global interrupts
        0x00800193,  # addi x3, x0, 8        # Set x3 = 0x8 (MIE bit)  
        0x30019073,  # csrw mstatus, x3      # Enable global interrupts
        
        # Write setup marker to data memory
        0x10000237,  # lui x4, 0x10000       # Set x4 = 0x10000000 (data memory base)
        0x00100293,  # addi x5, x0, 1        # Set x5 = 1 (setup marker)
        0x00522023,  # sw x5, 0(x4)          # Store setup marker at 0x10000000
        
        # Program timer: set mtimecmp to a small value (50 cycles)
        0x02004337,  # lui x6, 0x2004        # Set x6 = 0x02004000 (mtimecmp_lo address)
        0x03200393,  # addi x7, x0, 50       # Set x7 = 50 (small timeout value)
        0x00732023,  # sw x7, 0(x6)          # Store 50 to mtimecmp_lo
        0x00430313,  # addi x6, x6, 4        # x6 = 0x02004004 (mtimecmp_hi address)  
        0x00032023,  # sw x0, 0(x6)          # Store 0 to mtimecmp_hi (64-bit value = 50)
        
        # Infinite loop - wait for timer interrupt
        0x00000013,  # nop                   # Wait... (instruction 15)
        0x00000013,  # nop                   # Wait... (instruction 16)
        0x00000013,  # nop                   # Wait... (instruction 17)
        0x00000013,  # nop                   # Wait... (instruction 18)
        0xffdff06f,  # jal x0, -4            # Jump back to nop at instruction 15 (infinite loop)
    ]
    
    # Pad main program to reach instruction 64 (0x100 / 4 = 64)
    # Current main program is 19 instructions, need 45 more NOPs
    while len(main_program) < 64:
        main_program.append(0x00000013)  # nop
    
    # Timer interrupt handler (starts at instruction 64, byte address 0x100)
    handler_instructions = [
        # Save context (simplified - just use scratch register)
        0x10000437,  # lui x8, 0x10000       # Set x8 = 0x10000000 (data memory base)
        0xDEADB137,  # lui x2, 0xDEADB       # Set x2 = 0xDEADB000
        0x00242823,  # sw x2, 16(x8)         # Store handler marker at 0x10000010
        
        # Clear timer interrupt by setting mtimecmp to a very large value
        0x02004337,  # lui x6, 0x2004        # Set x6 = 0x02004000 (mtimecmp_lo)
        0xfff00393,  # addi x7, x0, -1       # Set x7 = 0xFFFFFFFF
        0x00732023,  # sw x7, 0(x6)          # Store 0xFFFFFFFF to mtimecmp_lo
        0x00430313,  # addi x6, x6, 4        # x6 = 0x02004004 (mtimecmp_hi)
        0x00732023,  # sw x7, 0(x6)          # Store 0xFFFFFFFF to mtimecmp_hi
        
        # Return from interrupt
        0x30200073,  # mret                  # Return from interrupt
        
        # Add some NOPs after handler for safety
        0x00000013,  # nop
        0x00000013,  # nop
        0x00000013,  # nop
        0x00000013,  # nop
    ]
    
    # Combine main program and handler
    instr_mem = main_program + handler_instructions
    
    test_name = "timer_interrupt"
    hex_file = program_hex("timer_interrupt", test_name, instr_mem, 512)
    return test_name, hex_file


@cocotb.test()
async def test_timer_interrupt(dut):
    """Test timer interrupt handling with internal timer"""
    print("Starting timer interrupt test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset (no external timer interrupt control needed)
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "timer_interrupt", max_cycles=200)  # Increased cycles
    
    print("\nTimer interrupt test results:")
    print("Memory accesses:", mem_writes)
    
    # Check that timer was programmed correctly
    if 0x02004000 in mem_writes:
        print(f"mtimecmp_lo programmed to: {mem_writes[0x02004000]}")
    else:
        print("mtimecmp_lo was not programmed")
    
    if 0x02004004 in mem_writes:
        print(f"mtimecmp_hi programmed to: {mem_writes[0x02004004]}")
    else:
        print("mtimecmp_hi was not programmed")
    
    # Check for interrupt setup
    if 0x10000000 in mem_writes:
        print(f"Initial setup marker found: {mem_writes[0x10000000]}")
    
    # Check if interrupt handler was called (should write to 0x10000010)
    if 0x10000010 in mem_writes:
        print(f"Timer interrupt handler executed! Marker: 0x{mem_writes[0x10000010]:08x}")
        assert mem_writes[0x10000010] == 0xDEADB000, "Timer interrupt handler marker should be 0xDEADB000"
    else:
        raise AssertionError("the timer interrupt handler never ran")
    
    print("Timer interrupt test completed!")


def runCocotbTests():
    run_hex_programs("test_timer_interrupt", [
        ("timer_interrupt", run_timer_interrupt_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
