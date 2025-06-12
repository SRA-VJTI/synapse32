import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
import pytest

async def run_csr_test_program(dut, instr_mem):
    """Helper function to run a CSR test program"""
    # Dictionary to track register values
    reg_values = {i: 0 for i in range(32)}
    
    # Simulate instruction memory fetch
    def get_instr(pc):
        idx = pc // 4
        if 0 <= idx < len(instr_mem):
            return instr_mem[idx]
        return 0
    
    # Feed instructions and track CSR operations
    for cycle in range(len(instr_mem) + 10):  # Run for enough cycles
        # Feed instruction based on PC
        pc = int(dut.module_pc_out.value)
        current_instr = get_instr(pc)
        dut.module_instr_in.value = current_instr
        
        # Track register writes
        try:
            wb_reg = int(dut.rf_inst0_rd_in.value)
            wb_val = int(dut.rf_inst0_rd_value_in.value)
            wb_en = int(dut.rf_inst0_wr_en.value)
            
            if wb_en and wb_reg != 0:
                reg_values[wb_reg] = wb_val
                print(f"Cycle {cycle}: Register x{wb_reg} = {wb_val:#x}")
        except Exception as e:
            print(f"Error tracking registers: {e}")
        
        # Track CSR operations
        try:
            csr_addr = int(dut.csr_addr.value)
            csr_read_en = int(dut.csr_read_enable.value)
            csr_write_en = int(dut.csr_write_enable.value)
            csr_read_data = int(dut.csr_read_data.value)
            csr_write_data = int(dut.csr_write_data.value)
            
            if csr_read_en or csr_write_en:
                operation = ""
                if csr_read_en and csr_write_en:
                    operation = f"CSR RW: CSR[{csr_addr:#x}] read={csr_read_data:#x}, write={csr_write_data:#x}"
                elif csr_read_en:
                    operation = f"CSR R: CSR[{csr_addr:#x}] read={csr_read_data:#x}"
                elif csr_write_en:
                    operation = f"CSR W: CSR[{csr_addr:#x}] write={csr_write_data:#x}"
                print(f"Cycle {cycle}: {operation}")
        except Exception as e:
            # CSR signals might not be ready yet
            pass
            
        # Advance simulation
        await RisingEdge(dut.clk)
        
    # Print final register values
    print("\nFinal register values:")
    for reg, value in reg_values.items():
        if value != 0:  # Only print non-zero registers
            print(f"x{reg} = {value:#x}")
    
    return reg_values

@cocotb.test()
async def test_csr_basic_operations(dut):
    """Test basic CSR read/write operations"""
    print("Starting CSR basic operations test...")
    
    # Attach a clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test CSR operations:
    instr_mem = [
        # Test CSRRW (Read/Write)
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x34009173,  # csrrw x2, mscratch, x1  # x2 = old mscratch (0), mscratch = 10
        0x34001273,  # csrrw x4, mscratch, x0  # x4 = mscratch (10), mscratch = 0
        
        # Test CSRRS (Read/Set)
        0x00500093,  # addi x1, x0, 5      # x1 = 5
        0x3400a373,  # csrrs x6, mscratch, x1  # x6 = mscratch (0), mscratch |= 5
        0x00300113,  # addi x2, x0, 3      # x2 = 3
        0x34012473,  # csrrs x8, mscratch, x2  # x8 = mscratch (5), mscratch |= 3 = 7
        
        # Test CSRRC (Read/Clear)
        0x00100193,  # addi x3, x0, 1      # x3 = 1
        0x3401b573,  # csrrc x10, mscratch, x3 # x10 = mscratch (7), mscratch &= ~1 = 6
        
        # Test immediate versions
        0x3402d673,  # csrrwi x12, mscratch, 5  # x12 = mscratch (6), mscratch = 5
        0x34016773,  # csrrsi x14, mscratch, 2  # x14 = mscratch (5), mscratch |= 2 = 7
        0x3400f873,  # csrrci x16, mscratch, 1  # x16 = mscratch (7), mscratch &= ~1 = 6
    ]

    # Run the program
    reg_values = await run_csr_test_program(dut, instr_mem)
    
    # Expected register values after execution
    expected_values = {
        1: 5,    # x1 = 10
        2: 3,     # x2 = old mscratch (initial value 0)
        4: 10,    # x4 = mscratch value (10)
        6: 0,     # x6 = mscratch before set (0)
        8: 5,     # x8 = mscratch before set (5)
        10: 7,    # x10 = mscratch before clear (7)
        12: 6,    # x12 = mscratch before write (6)
        14: 5,    # x14 = mscratch before set (5)
        16: 7,    # x16 = mscratch before clear (7)
    }
    
    # Verify register values
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    # Check final CSR value
    final_mscratch = int(dut.csr_file_inst.mscratch.value)
    expected_mscratch = 6  # Final value after all operations
    print(f"mscratch: expected={expected_mscratch:#x}, actual={final_mscratch:#x}")
    assert final_mscratch == expected_mscratch, f"mscratch value mismatch: expected {expected_mscratch:#x}, got {final_mscratch:#x}"
    
    print("All CSR basic operations test passed!")

@cocotb.test()
async def test_csr_mstatus_operations(dut):
    """Test operations on MSTATUS CSR"""
    print("Starting MSTATUS CSR test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test MSTATUS operations:
    instr_mem = [
        # Read initial MSTATUS value
        0x30002073,  # csrrs x0, mstatus, x0   # Read mstatus (no change)
        0x30002173,  # csrrs x2, mstatus, x0   # x2 = mstatus
        
        # Set some bits in MSTATUS
        0x00800093,  # addi x1, x0, 8         # x1 = 8 (MIE bit)
        0x3000a273,  # csrrs x4, mstatus, x1   # Set MIE bit, x4 = old mstatus
        
        # Clear some bits in MSTATUS
        0x00800193,  # addi x3, x0, 8         # x3 = 8 (MIE bit)
        0x3001b373,  # csrrc x6, mstatus, x3   # Clear MIE bit, x6 = old mstatus
        
        # Test immediate operations on MSTATUS
        0x30006473,  # csrrsi x8, mstatus, 0   # Read mstatus (no change)
        0x30015573,  # csrrsi x10, mstatus, 2  # Set bit 1, x10 = old mstatus
    ]

    await run_csr_test_program(dut, instr_mem)
    
    # Verify that MSTATUS operations worked correctly
    # Note: Initial MSTATUS = 0x1800 (MPP = 11)
    expected_values = {
        2: 0x1800,  # x2 = initial mstatus
        3: 0x8,  # x3 = MIE bit set (0x1808)
        4: 0x1800,  # x4 = mstatus before setting MIE
        6: 0x1808,  # x6 = mstatus with MIE set
        8: 0x1800,  # x8 = mstatus after clearing MIE
        10: 0x1800, # x10 = mstatus before setting bit 1
    }
    
    print("\nVerifying MSTATUS register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    print("MSTATUS CSR test passed!")

@cocotb.test()
async def test_csr_cycle_counter(dut):
    """Test cycle counter CSRs"""
    print("Starting cycle counter CSR test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test cycle counter:
    instr_mem = [
        # Read cycle counter at different times
        0xc0002073,  # csrrs x0, cycle, x0     # Read cycle (no change)
        0xc0002173,  # csrrs x2, cycle, x0     # x2 = cycle low
        0xc8002273,  # csrrs x4, cycleh, x0    # x4 = cycle high
        
        # Add some NOPs to advance cycle counter
        0x00000013,  # nop
        0x00000013,  # nop
        0x00000013,  # nop
        
        # Read cycle counter again
        0xc0002373,  # csrrs x6, cycle, x0     # x6 = cycle low (later)
        0xc8002473,  # csrrs x8, cycleh, x0    # x8 = cycle high (later)
    ]

    await run_csr_test_program(dut, instr_mem)
    
    # Verify that cycle counter is advancing
    cycle_low_1 = int(dut.rf_inst0.register_file[2].value)
    cycle_high_1 = int(dut.rf_inst0.register_file[4].value)
    cycle_low_2 = int(dut.rf_inst0.register_file[6].value)
    cycle_high_2 = int(dut.rf_inst0.register_file[8].value)
    
    print(f"First cycle read: low={cycle_low_1:#x}, high={cycle_high_1:#x}")
    print(f"Second cycle read: low={cycle_low_2:#x}, high={cycle_high_2:#x}")
    
    # Cycle counter should have advanced
    assert cycle_low_2 > cycle_low_1, "Cycle counter should have advanced"
    
    print("Cycle counter CSR test passed!")

@cocotb.test()
async def test_csr_invalid_access(dut):
    """Test access to invalid CSR addresses"""
    print("Starting invalid CSR access test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test invalid CSR access:
    instr_mem = [
        # Try to access an invalid CSR (address 0x123)
        0x12302173,  # csrrs x2, 0x123, x0    # Should read 0 from invalid CSR
        
        # Valid CSR for comparison
        0x34002273,  # csrrs x4, mscratch, x0  # Should read valid CSR
    ]

    await run_csr_test_program(dut, instr_mem)
    
    # Verify invalid CSR returns 0
    invalid_csr_value = int(dut.rf_inst0.register_file[2].value)
    valid_csr_value = int(dut.rf_inst0.register_file[4].value)
    
    print(f"Invalid CSR read: {invalid_csr_value:#x}")
    print(f"Valid CSR read: {valid_csr_value:#x}")
    
    assert invalid_csr_value == 0, "Invalid CSR should return 0"
    
    print("Invalid CSR access test passed!")

from cocotb_test.simulator import run
import os

def runCocotbTests():
    # All Verilog sources under rtl directory and subdirectories
    sources = []
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith(".v") or file.endswith(".sv"):
                sources.append(os.path.join(root, file))
    
    # Define the CSR tests
    tests = [
        "test_csr_basic_operations",
        "test_csr_mstatus_operations", 
        "test_csr_cycle_counter",
        "test_csr_invalid_access",
    ]
    
    # Create waveforms directory in the current working directory if it doesn't exist
    curr_dir = os.getcwd()
    waveform_dir = os.path.join(curr_dir, "waveforms")
    if not os.path.exists(waveform_dir):
        os.makedirs(waveform_dir)
    # Query full path of the directory
    waveform_dir = os.path.abspath("waveforms")
    
    # Run each test with its own waveform file
    for test_name in tests:
        print(f"\n=== Running {test_name} ===")
        waveform_path = os.path.join(waveform_dir, f"{test_name}.vcd")
        
        # Use +dumpfile argument to pass the filename to the simulator
        run(
            verilog_sources=sources,
            toplevel="riscv_cpu",
            module="test_csr",
            testcase=test_name,
            includes=[rtl_dir],
            simulator="icarus",
            timescale="1ns/1ps",
            plus_args=[f"+dumpfile={waveform_path}"]
        )

if __name__ == "__main__":
    runCocotbTests()