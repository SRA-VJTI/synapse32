import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
import pytest

@cocotb.test()
async def test_riscv_cpu_raw_hazards(dut):
    """Test for RAW hazards - when an instruction needs register data from previous instructions"""
    print("Starting RAW hazards test...")
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

    # Program with multiple back-to-back RAW hazards:
    # 1. Simple RAW case: x1 <- x2 <- x3
    # 2. Multiple sources RAW: x1, x2 -> x3, then x3 -> x4
    instr_mem = [
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00108113,  # addi x2, x1, 1      # x2 = x1 + 1 = 11 (RAW on x1)
        0x00110193,  # addi x3, x2, 1      # x3 = x2 + 1 = 12 (RAW on x2)
        0x00320233,  # add x4, x4, x3      # x4 = x4 + x3 (RAW on x3)
        0x00100293,  # addi x5, x0, 1      # x5 = 1
        0x005282b3,  # add x5, x5, x5      # x5 = x5 + x5 = 2 (RAW on x5)
        0x005282b3,  # add x5, x5, x5      # x5 = x5 + x5 = 4 (RAW on x5)
        0x005282b3,  # add x5, x5, x5      # x5 = x5 + x5 = 8 (RAW on x5)
    ]

    # Run the program
    reg_values = await run_test_program(dut, instr_mem)
    
    # Expected register values after execution
    expected_values = {
        1: 10,    # x1 = 10
        2: 11,    # x2 = 11
        3: 12,    # x3 = 12
        4: 12,    # x4 = 0 + 12 = 12 (assuming x4 starts as 0)
        5: 8      # x5 = 8 after three doubling operations
    }
    
    # Verify register values
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    print("All register values match expected values - RAW hazard test passed!")

@cocotb.test()
async def test_riscv_cpu_control_hazards(dut):
    """Test for control hazards - when branches and jumps affect the pipeline"""
    print("Starting control hazards test...")
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

    # Program with branch and jump instructions:
    instr_mem = [
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00500113,  # addi x2, x0, 5      # x2 = 5
        0x00208463,  # beq x1, x2, L1      # Branch if x1 == x2 (won't take)
        0x00000013,  # nop                 # Execute if branch not taken
        0x00100193,  # addi x3, x0, 1      # x3 = 1
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00a00113,  # addi x2, x0, 10     # x2 = 10
        0x02208a63,  # beq x1, x2, 0x34      # Branch if x1 == x2 (will take)
        0x00118193,  # addi x3, x3, 1      # x3 = 2 (skipped due to branch)
        0x00118193,  # addi x3, x3, 1      # x3 = 3 (skipped due to branch)
        0xfff18193,  # addi x3, x3, -1     # x3 = 0
    ]

    await run_test_program(dut, instr_mem)

    # Verify register values after execution
    expected_values = {
        1: 10,    # x1 = 10
        2: 10,    # x2 = 10 (after branch)
        3: 0,     # x3 = 0 (after branch)
    }
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"

    print("All register values match expected values - control hazards test passed!")

@cocotb.test()
async def test_riscv_cpu_memory_hazards(dut):
    """Test for memory hazards - particularly store-load hazards"""
    print("Starting memory hazards test...")
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

    # Memory data for loads
    mem_data = {}  # address -> data

    # Program with store-load hazards:
    instr_mem = [
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00000113,  # addi x2, x0, 0      # x2 = 0 (address)
        0x00112023,  # sw x1, 0(x2)        # MEM[0] = x1 (10)
        0x00012183,  # lw x3, 0(x2)        # x3 = MEM[0] (should be 10)
        0x00118213,  # addi x4, x3, 1      # x4 = x3 + 1 (should be 11)
        0x00412083,  # lw x1, 4(x2)        # x1 = MEM[4]
        0x00312103,  # lw x2, 3(x2)        # x2 = MEM[3] (misaligned load)
    ]

    # Simulate data memory - handle read requests
    async def handle_memory_writes(dut, mem_data):
        while True:
            # Check for memory read and respond in the same cycle
            try:
                if int(dut.module_mem_wr_en.value):
                    addr = int(dut.module_write_addr.value)
                    data = int(dut.module_wr_data_out.value)
                    print(f"Memory write: MEM[{addr:#x}] = {data:#x}")
                    mem_data[addr] = data
            except Exception as e:
                print(f"Memory handler error: {e}")
            
            # Wait for next clock cycle after handling the current one
            await RisingEdge(dut.clk)

    async def handle_memory_reads(dut, mem_data):
        while True:
            # Check for memory read requests
            try:
                if int(dut.module_mem_rd_en.value):
                    addr = int(dut.module_read_addr.value)
                    if addr in mem_data:
                        data = mem_data[addr]
                        dut.module_read_data_in.value = data
                        print(f"Memory read: MEM[{addr:#x}] = {data:#x}")
                    else:
                        dut.module_read_data_in.value = 0xDEADBEEF  # Default value if not found
            except Exception as e:
                print(f"Memory handler error: {e}")
            # Wait for next clock cycle after handling the current one
            await RisingEdge(dut.clk)
    
    # Start the memory handler
    cocotb.start_soon(handle_memory_writes(dut, mem_data))
    cocotb.start_soon(handle_memory_reads(dut, mem_data))
    
    await run_test_program(dut, instr_mem)

async def run_test_program(dut, instr_mem):
    """Helper function to run a program and track register values"""
    # Dictionary to track register values
    reg_values = {i: 0 for i in range(32)}
    
    # Simulate instruction memory fetch
    def get_instr(pc):
        idx = pc // 4
        if 0 <= idx < len(instr_mem):
            return instr_mem[idx]
        return 0
    
    # Pipeline stages tracker
    pipeline_tracker = []
    
    # Feed instructions and track pipeline stages
    for cycle in range(30):  # Run for enough cycles
        # Feed instruction based on PC
        pc = int(dut.module_pc_out.value)
        current_instr = get_instr(pc)
        dut.module_instr_in.value = current_instr
        
        # Track what's in each pipeline stage
        if current_instr != 0:
            instr_idx = pc // 4
            pipeline_tracker.append({
                'cycle': cycle,
                'pc': pc,
                'instr_idx': instr_idx,
                'instr': current_instr
            })
        
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
        
        # Print hazard detection signals
        try:
            # RAW hazard detection (forwarding unit)
            forward_a = int(dut.forward_a.value)
            forward_b = int(dut.forward_b.value)
            if forward_a > 0 or forward_b > 0:
                print(f"Cycle {cycle}: RAW hazard detected - forward_a={forward_a}, forward_b={forward_b}")
                
            # Load-use hazard detection
            try:
                stall = int(dut.stall_pipeline.value)
                if stall:
                    print(f"Cycle {cycle}: Load-use hazard detected - pipeline stalled")
            except Exception:
                pass
                
            # Branch/jump hazard detection
            try:
                flush = int(dut.branch_flush.value)
                if flush:
                    print(f"Cycle {cycle}: Branch hazard detected - pipeline flushed")
            except Exception:
                pass
                
            # Store-load hazard detection
            try:
                store_load_hazard = int(dut.store_load_hazard.value)
                if store_load_hazard:
                    print(f"Cycle {cycle}: Store-load hazard detected")
            except Exception:
                pass
                
        except Exception as e:
            print(f"Error checking hazard signals: {e}")
            
        # Advance simulation
        await RisingEdge(dut.clk)
        
    # Print final register values
    print("\nFinal register values:")
    for reg, value in reg_values.items():
        if value != 0:  # Only print non-zero registers
            print(f"x{reg} = {value:#x}")

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
    incl_dir = os.path.join(rtl_dir, "include")
    
    # Define the tests
    tests = [
        "test_riscv_cpu_raw_hazards",
        "test_riscv_cpu_control_hazards", 
        "test_riscv_cpu_memory_hazards"
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
            module="test_riscv_cpu_basic",
            testcase=test_name,
            includes=[str(incl_dir)],
            simulator="icarus",
            timescale="1ns/1ps",
            plus_args=[f"+dumpfile={waveform_path}"]
        )

if __name__ == "__main__":
    runCocotbTests()
