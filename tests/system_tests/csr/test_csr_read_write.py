"""Reads, writes, set and clear of CSRs, and CSR instructions back to back on one register."""

import cocotb

from support import run_program, run_tests


@cocotb.test()
async def test_csr_basic_operations(dut):
    """Test basic CSR read/write operations"""
    print("Starting CSR basic operations test...")
    
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
    await run_program(dut, instr_mem)
    
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
        actual = int(dut.cpu_inst.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    # Check final CSR value
    final_mscratch = int(dut.cpu_inst.csr_file_inst.mscratch.value)
    expected_mscratch = 6  # Final value after all operations
    print(f"mscratch: expected={expected_mscratch:#x}, actual={final_mscratch:#x}")
    assert final_mscratch == expected_mscratch, f"mscratch value mismatch: expected {expected_mscratch:#x}, got {final_mscratch:#x}"
    
    print("All CSR basic operations test passed!")


@cocotb.test()
async def test_csr_mstatus_operations(dut):
    """Test operations on MSTATUS CSR"""
    print("Starting MSTATUS CSR test...")
    
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

    await run_program(dut, instr_mem)
    
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
        actual = int(dut.cpu_inst.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    print("MSTATUS CSR test passed!")


@cocotb.test()
async def test_csr_machine_mode_same_reg_hazard(dut):
    """Exercise back-to-back machine CSR ops that use the same register as rs1 and rd."""
    print("Starting machine-mode CSR same-reg hazard test...")

    instr_mem = [
        0x00700093,  # addi x1,  x0, 7
        0x34009073,  # csrrw x0, mscratch, x1      ; mscratch = 7
        0x00100513,  # addi x10, x0, 1
        0x34053573,  # csrrc x10, mscratch, x10    ; x10 = 7, mscratch = 6
        0x00800513,  # addi x10, x0, 8
        0x34052573,  # csrrs x10, mscratch, x10    ; x10 = 6, mscratch = 14
        0x340025f3,  # csrrs x11, mscratch, x0     ; x11 = 14
    ]

    await run_program(dut, instr_mem)

    x10 = int(dut.cpu_inst.rf_inst0.register_file[10].value)
    x11 = int(dut.cpu_inst.rf_inst0.register_file[11].value)
    mscratch = int(dut.cpu_inst.csr_file_inst.mscratch.value)

    print(f"x10={x10:#x}, x11={x11:#x}, mscratch={mscratch:#x}")

    assert x10 == 0x6, f"Expected x10 to hold prior CSR value 0x6, got {x10:#x}"
    assert x11 == 0xe, f"Expected x11 to read final CSR value 0xe, got {x11:#x}"
    assert mscratch == 0xe, f"Expected mscratch=0xe, got {mscratch:#x}"

    print("Machine-mode CSR same-reg hazard test passed!")


@cocotb.test()
async def test_csr_machine_mode_riscv_tests_sequence(dut):
    """Mirror the rv32mi/rv64si csr.S machine-mode mscratch sequence."""
    print("Starting machine-mode riscv-tests CSR sequence...")

    instr_mem = [
        0x3401D073,  # csrwi  x0,  mscratch, 3
        0x34002573,  # csrr   a0,  mscratch
        0x3400F5F3,  # csrrci a1,  mscratch, 1
        0x34026673,  # csrrsi a2,  mscratch, 4
        0x340156F3,  # csrrwi a3,  mscratch, 2
        0x0BAD2537,  # lui    a0,  0xbad2
        0xDEA50513,  # addi   a0,  a0, -534      -> 0xbad1dea
        0x340515F3,  # csrrw  a1,  mscratch, a0
        0x00002537,  # lui    a0,  0x2
        0xDEA50513,  # addi   a0,  a0, -534      -> 0x0001dea
        0x340535F3,  # csrrc  a1,  mscratch, a0
        0x0000C537,  # lui    a0,  0xc
        0xEEF50513,  # addi   a0,  a0, -273      -> 0x0000beef
        0x340525F3,  # csrrs  a1,  mscratch, a0
        0x0BAD2537,  # lui    a0,  0xbad2
        0xDEA50513,  # addi   a0,  a0, -534      -> 0xbad1dea
        0x34051573,  # csrrw  a0,  mscratch, a0
        0x00002537,  # lui    a0,  0x2
        0xDEA50513,  # addi   a0,  a0, -534      -> 0x0001dea
        0x34053573,  # csrrc  a0,  mscratch, a0
        0x0000C537,  # lui    a0,  0xc
        0xEEF50513,  # addi   a0,  a0, -273      -> 0x0000beef
        0x34052573,  # csrrs  a0,  mscratch, a0
        0x34002573,  # csrr   a0,  mscratch
    ]

    await run_program(dut, instr_mem)

    a0 = int(dut.cpu_inst.rf_inst0.register_file[10].value)
    a1 = int(dut.cpu_inst.rf_inst0.register_file[11].value)
    a2 = int(dut.cpu_inst.rf_inst0.register_file[12].value)
    a3 = int(dut.cpu_inst.rf_inst0.register_file[13].value)
    mscratch = int(dut.cpu_inst.csr_file_inst.mscratch.value)

    print(f"a0={a0:#x}, a1={a1:#x}, a2={a2:#x}, a3={a3:#x}, mscratch={mscratch:#x}")

    assert a0 == 0xBADBEEF, f"Expected final a0=0xbadbeef, got {a0:#x}"
    assert a1 == 0xBAD0000, f"Expected a1=0xbad0000, got {a1:#x}"
    assert a2 == 0x2, f"Expected a2=0x2, got {a2:#x}"
    assert a3 == 0x6, f"Expected a3=0x6, got {a3:#x}"
    assert mscratch == 0xBADBEEF, f"Expected mscratch=0xbadbeef, got {mscratch:#x}"

    print("Machine-mode riscv-tests CSR sequence passed!")


def runCocotbTests():
    run_tests("test_csr_read_write", [
        "test_csr_basic_operations",
        "test_csr_mstatus_operations",
        "test_csr_machine_mode_same_reg_hazard",
        "test_csr_machine_mode_riscv_tests_sequence",
    ])


if __name__ == "__main__":
    runCocotbTests()
