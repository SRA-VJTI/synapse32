"""ECALL and EBREAK trap before the next instruction; MRET jumps to mepc."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from support import monitor_execution, program_hex, run_hex_programs


def run_ecall_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x00500093,  # addi x1, x0, 5        # Load immediate: Set x1 to 5 (test value before ECALL)
        0x030001b7,  # lui x3, 0x3000        # Load immediate: Set x3 to memory base address 0x03000000
        0x0011a023,  # sw x1, 0(x3)          # Store word: Store x1 (5) to memory at x3+0
        0x00000073,  # ecall                 # Environment call - should trigger trap
        0x01000213,  # addi x4, x0, 16       # Load immediate: Set x4 to 16 (should not execute after ECALL)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (16) to memory at x3+4 (should not execute)
        0x00000013,  # addi x0, x0, 0        # NOP
        0x00000013,  # addi x0, x0, 0        # NOP
    ]
    test_name = "ecall_test"
    hex_file = program_hex("trap_instructions", test_name, instr_mem, 512)
    return test_name, hex_file

def run_ebreak_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x00700093,  # addi x1, x0, 7        # Load immediate: Set x1 to 7 (test value before EBREAK)
        0x030001b7,  # lui x3, 0x3000        # Load immediate: Set x3 to memory base address 0x03000000
        0x0011a023,  # sw x1, 0(x3)          # Store word: Store x1 (7) to memory at x3+0
        0x00100073,  # ebreak                # Breakpoint instruction - should trigger trap
        0x02800213,  # addi x4, x0, 40       # Load immediate: Set x4 to 40 (should not execute after EBREAK)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (40) to memory at x3+4 (should not execute)
        0x00000013,  # addi x0, x0, 0        # NOP
        0x00000013,  # addi x0, x0, 0        # NOP
    ]
    test_name = "ebreak_test"
    hex_file = program_hex("trap_instructions", test_name, instr_mem, 512)
    return test_name, hex_file

def run_mret_test():
    instr_mem = [
        0x00800093,  # addi x1, x0, 8        # Load immediate: Set x1 to 8 (MPP bits for Machine mode)
        0x30009073,  # csrw mstatus, x1      # Write CSR: Set mstatus to value in x1 (set MPP)
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 to 0x10000000 (return address)
        0x34111073,  # csrw mepc, x2         # Write CSR: Set mepc (machine exception program counter) to value in x2
        0x030001b7,  # lui x3, 0x3000        # Load immediate: Set x3 to memory base address 0x03000000
        0x0AA00213,  # addi x4, x0, 0xAA     # Load immediate: Set x4 to 0xAA (marker value before MRET)
        0x0041a023,  # sw x4, 0(x3)          # Store word: Store x4 (0xAA) to memory at x3+0
        0x30200073,  # mret                  # Machine return - should return to address in mepc
        0xDEAD0213,  # addi x4, x0, 0xDEAD   # Load immediate: Set x4 to 0xDEAD (should not execute after MRET)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (0xDEAD) to memory at x3+4 (should not execute)
    ]
    test_name = "mret_test"
    hex_file = program_hex("trap_instructions", test_name, instr_mem, 512)
    return test_name, hex_file


@cocotb.test()
async def test_ecall_test(dut):
    """Test ECALL instruction (environment call)"""
    print("Starting ECALL instruction test...")
    
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
    mem_writes = await monitor_execution(dut, "ecall_test", max_cycles=80)
    
    print("\nVerifying ECALL behavior:")
    print("Memory accesses:", mem_writes)
    
    # x1=5 should be written to memory (before ECALL)
    if 0x03000000 in mem_writes:
        assert mem_writes[0x03000000] == 5, f"Expected x1=5 at 0x03000000, got {mem_writes[0x03000000]}"
        print("Memory write before ECALL occurred correctly")
    else:
        raise AssertionError("the store before the trap or return never happened")
    
    # x4=16 should NOT be written (after ECALL trap)
    if 0x03000004 in mem_writes:
        raise AssertionError(f"the store after ECALL ran (wrote {mem_writes[0x03000004]}): ECALL did not trap")
    else:
        print("No memory write after ECALL (correct - should have trapped)")
    
    print("ECALL instruction test completed!")


@cocotb.test()
async def test_ebreak_test(dut):
    """Test EBREAK instruction (breakpoint)"""
    print("Starting EBREAK instruction test...")
    
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
    mem_writes = await monitor_execution(dut, "ebreak_test", max_cycles=80)
    
    print("\nVerifying EBREAK behavior:")
    print("Memory accesses:", mem_writes)
    
    # x1=7 should be written to memory (before EBREAK)
    if 0x03000000 in mem_writes:
        assert mem_writes[0x03000000] == 7, f"Expected x1=7 at 0x03000000, got {mem_writes[0x03000000]}"
        print("Memory write before EBREAK occurred correctly")
    else:
        raise AssertionError("the store before the trap or return never happened")
    
    # x4=40 should NOT be written (after EBREAK trap)
    if 0x03000004 in mem_writes:
        raise AssertionError(f"the store after EBREAK ran (wrote {mem_writes[0x03000004]}): EBREAK did not trap")
    else:
        print("No memory write after EBREAK (correct - should have trapped)")
    
    print("EBREAK instruction test completed!")


@cocotb.test()
async def test_mret_test(dut):
    """Test MRET instruction (return from trap)"""
    print("Starting MRET instruction test...")
    
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
    mem_writes = await monitor_execution(dut, "mret_test", max_cycles=80)
    
    print("\nVerifying MRET behavior:")
    print("Memory accesses:", mem_writes)
    
    # Marker 0xAA should be written (before MRET)
    if 0x03000000 in mem_writes:
        assert mem_writes[0x03000000] == 0xAA, f"Expected marker 0xAA at 0x03000000, got 0x{mem_writes[0x03000000]:08x}"
        print("Memory write before MRET occurred correctly")
    else:
        raise AssertionError("the store before the trap or return never happened")
    
    # 0xDEAD should NOT be written (after MRET jump)
    if 0x03000004 in mem_writes:
        raise AssertionError(f"the store after MRET ran (wrote 0x{mem_writes[0x03000004]:08x}): MRET did not jump to mepc")
    else:
        print("No memory write after MRET (correct - should have jumped away)")
    
    print("MRET instruction test completed!")


def runCocotbTests():
    run_hex_programs("test_trap_instructions", [
        ("ecall_test", run_ecall_test),
        ("ebreak_test", run_ebreak_test),
        ("mret_test", run_mret_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
