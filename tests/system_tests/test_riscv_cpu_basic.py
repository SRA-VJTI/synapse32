import cocotb

from cpu_program import run_program, run_tests


@cocotb.test()
async def test_riscv_cpu_raw_hazards(dut):
    """Test for RAW hazards - when an instruction needs register data from previous instructions"""
    print("Starting RAW hazards test...")
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
    await run_program(dut, instr_mem)
    
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
        actual = int(dut.cpu_inst.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    print("All register values match expected values - RAW hazard test passed!")

@cocotb.test()
async def test_riscv_cpu_control_hazards(dut):
    """Test for control hazards - when branches and jumps affect the pipeline"""
    print("Starting control hazards test...")
    # Program with branch and jump instructions:
    instr_mem = [
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00500113,  # addi x2, x0, 5      # x2 = 5
        0x00208463,  # beq x1, x2, L1      # Branch if x1 == x2 (won't take)
        0x00000013,  # nop                 # Execute if branch not taken
        0x00100193,  # addi x3, x0, 1      # x3 = 1
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x00a00113,  # addi x2, x0, 10     # x2 = 10
        0x00208663,  # beq x1, x2, 12      # Branch if x1 == x2 (will take)
        0x00118193,  # addi x3, x3, 1      # x3 = 2 (skipped due to branch)
        0x00118193,  # addi x3, x3, 1      # x3 = 3 (skipped due to branch)
        0xfff18193,  # addi x3, x3, -1     # x3 = 0
    ]

    await run_program(dut, instr_mem)

    # Verify register values after execution
    expected_values = {
        1: 10,    # x1 = 10
        2: 10,    # x2 = 10 (after branch)
        3: 0,     # x3 = 0 (after branch)
    }
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.cpu_inst.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"

    print("All register values match expected values - control hazards test passed!")

@cocotb.test()
async def test_riscv_cpu_memory_hazards(dut):
    """Test for memory hazards - particularly store-load hazards"""
    print("Starting memory hazards test...")
    # Program with store-load hazards:
    instr_mem = [
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x10000137,  # lui x2, 0x10000     # x2 = 0x10000000 (address)
        0x00112023,  # sw x1, 0(x2)        # MEM[0] = x1 (10)
        0x00012183,  # lw x3, 0(x2)        # x3 = MEM[0] (should be 10)
        0x00118213,  # addi x4, x3, 1      # x4 = x3 + 1 (should be 11)
        0x00412083,  # lw x1, 4(x2)        # x1 = MEM[4]
        0x00312103,  # lw x2, 3(x2)        # x2 = MEM[3] (misaligned load)
    ]

    # The misaligned load traps (mcause 4) and ends the program.
    await run_program(dut, instr_mem, done=lambda dut: int(dut.cpu_inst.csr_file_inst.mcause.value) == 4)

    expected_values = {
        3: 10,    # x3 = MEM[0] (the stored 10)
        4: 11,    # x4 = x3 + 1
    }
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.cpu_inst.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"


def runCocotbTests():
    run_tests("test_riscv_cpu_basic", [
        "test_riscv_cpu_raw_hazards",
        "test_riscv_cpu_control_hazards",
        "test_riscv_cpu_memory_hazards",
    ])


if __name__ == "__main__":
    runCocotbTests()
