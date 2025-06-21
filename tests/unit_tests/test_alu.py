import cocotb
from cocotb.triggers import Timer
import random
import os
from pathlib import Path

# Helper function to verify ALU operation
async def verify_alu_operation(dut, rs1, rs2, imm, instruction, pc_input, expected_output, operation_name):
    dut.rs1.value = rs1
    dut.rs2.value = rs2
    dut.imm.value = imm
    dut.instr_id.value = instruction
    dut.pc_input.value = pc_input
    
    await Timer(5, units="ns")  # Wait for combinational logic to settle
    
    actual_output = dut.ALUoutput.value.integer
    
    assert actual_output == expected_output, (
        f"ALU operation {operation_name} failed: "
        f"rs1=0x{rs1:08x}, rs2=0x{rs2:08x}, imm=0x{imm:08x}, "
        f"expected=0x{expected_output:08x}, got=0x{actual_output:08x}"
    )
    
    dut._log.info(
        f"ALU operation {operation_name} passed: "
        f"rs1=0x{rs1:08x}, rs2=0x{rs2:08x}, imm=0x{imm:08x}, "
        f"result=0x{actual_output:08x}"
    )

# Basic operations with R-type instructions
@cocotb.test()
async def test_add(dut):
    """Test ADD operation (rs1 + rs2)"""
    # Normal cases
    await verify_alu_operation(dut, 10, 20, 0, 0x1, 0, 30, "ADD")
    await verify_alu_operation(dut, 0xFFFFFFFF, 1, 0, 0x1, 0, 0, "ADD overflow")
    
    # Corner cases
    await verify_alu_operation(dut, 0x7FFFFFFF, 1, 0, 0x1, 0, 0x80000000, "ADD int_max+1")
    await verify_alu_operation(dut, 0x80000000, 0x80000000, 0, 0x1, 0, 0, "ADD int_min+int_min")
    await verify_alu_operation(dut, 0, 0, 0, 0x1, 0, 0, "ADD zero+zero")

@cocotb.test()
async def test_sub(dut):
    """Test SUB operation (rs1 - rs2)"""
    # Normal cases
    await verify_alu_operation(dut, 30, 20, 0, 0x2, 0, 10, "SUB")
    await verify_alu_operation(dut, 0, 1, 0, 0x2, 0, 0xFFFFFFFF, "SUB underflow")
    
    # Corner cases
    await verify_alu_operation(dut, 0x80000000, 1, 0, 0x2, 0, 0x7FFFFFFF, "SUB int_min-1")
    await verify_alu_operation(dut, 0, 0, 0, 0x2, 0, 0, "SUB zero-zero")
    await verify_alu_operation(dut, 5, 5, 0, 0x2, 0, 0, "SUB same values")

@cocotb.test()
async def test_bitwise_operations(dut):
    """Test bitwise operations (XOR, OR, AND)"""
    # XOR
    await verify_alu_operation(dut, 0xAAAA5555, 0x5555AAAA, 0, 0x3, 0, 0xFFFFFFFF, "XOR")
    await verify_alu_operation(dut, 0xFFFF0000, 0x0000FFFF, 0, 0x3, 0, 0xFFFFFFFF, "XOR")
    await verify_alu_operation(dut, 0xABCD1234, 0xABCD1234, 0, 0x3, 0, 0, "XOR same values")
    
    # OR
    await verify_alu_operation(dut, 0xAAAA5555, 0x5555AAAA, 0, 0x4, 0, 0xFFFFFFFF, "OR")
    await verify_alu_operation(dut, 0x12345678, 0, 0, 0x4, 0, 0x12345678, "OR with zero")
    
    # AND
    await verify_alu_operation(dut, 0xFFFF0000, 0x0000FFFF, 0, 0x5, 0, 0, "AND")
    await verify_alu_operation(dut, 0xFFFFFFFF, 0x12345678, 0, 0x5, 0, 0x12345678, "AND with all ones")
    await verify_alu_operation(dut, 0x12345678, 0, 0, 0x5, 0, 0, "AND with zero")

@cocotb.test()
async def test_shifts(dut):
    """Test shift operations"""
    # Logical left shift
    await verify_alu_operation(dut, 1, 4, 0, 0x6, 0, 16, "SLL")
    await verify_alu_operation(dut, 0x12345678, 0, 0, 0x6, 0, 0x12345678, "SLL by zero")
    await verify_alu_operation(dut, 0x12345678, 32, 0, 0x6, 0, 0x12345678, "SLL by 32 (should use only 5 bits)")
    await verify_alu_operation(dut, 0x12345678, 31, 0, 0x6, 0, 0x0000000, "SLL by 31")
    
    # Logical right shift
    await verify_alu_operation(dut, 16, 2, 0, 0x7, 0, 4, "SRL")
    await verify_alu_operation(dut, 0x80000000, 31, 0, 0x7, 0, 1, "SRL by 31")
    await verify_alu_operation(dut, 0xFFFFFFFF, 32, 0, 0x7, 0, 0xFFFFFFFF, "SRL by 32 (should use only 5 bits)")
    
    # Arithmetic right shift
    await verify_alu_operation(dut, 16, 2, 0, 0x8, 0, 4, "SRA positive")
    await verify_alu_operation(dut, 0x80000000, 4, 0, 0x8, 0, 0xF8000000, "SRA negative")
    await verify_alu_operation(dut, 0x80000000, 31, 0, 0x8, 0, 0xFFFFFFFF, "SRA by 31 (sign extension)")

@cocotb.test()
async def test_comparisons(dut):
    """Test comparisons operations"""
    # Set less than (signed)
    await verify_alu_operation(dut, 10, 20, 0, 0x9, 0, 0xFFFFFFFF, "SLT true")
    await verify_alu_operation(dut, 20, 10, 0, 0x9, 0, 0, "SLT false")
    await verify_alu_operation(dut, 0x80000000, 1, 0, 0x9, 0, 0xFFFFFFFF, "SLT negative < positive")
    await verify_alu_operation(dut, 0, 0x80000000, 0, 0x9, 0, 0, "SLT positive > negative")
    
    # Set less than (unsigned)
    await verify_alu_operation(dut, 10, 20, 0, 0xA, 0, 0xFFFFFFFF, "SLTU true")
    await verify_alu_operation(dut, 20, 10, 0, 0xA, 0, 0, "SLTU false")
    await verify_alu_operation(dut, 0, 1, 0, 0xA, 0, 0xFFFFFFFF, "SLTU zero < one")
    await verify_alu_operation(dut, 0x80000000, 1, 0, 0xA, 0, 0, "SLTU MSB high > low (unsigned)")

@cocotb.test()
async def test_immediate_operations(dut):
    """Test operations with immediates"""
    # Add immediate
    await verify_alu_operation(dut, 10, 0, 20, 0xB, 0, 30, "ADDI")
    await verify_alu_operation(dut, 0x7FFFFFFF, 0, 1, 0xB, 0, 0x80000000, "ADDI overflow")
    
    # XOR immediate
    await verify_alu_operation(dut, 0xFFFF0000, 0, 0x0000FFFF, 0xC, 0, 0xFFFFFFFF, "XORI")
    
    # OR immediate
    await verify_alu_operation(dut, 0xAAAA0000, 0, 0x0000AAAA, 0xD, 0, 0xAAAAAAAA, "ORI")
    
    # AND immediate
    await verify_alu_operation(dut, 0xFFFFFFFF, 0, 0x0000FFFF, 0xE, 0, 0x0000FFFF, "ANDI")
    
    # Shift left immediate
    await verify_alu_operation(dut, 1, 0, 4, 0xF, 0, 16, "SLLI")
    await verify_alu_operation(dut, 1, 0, 31, 0xF, 0, 0x80000000, "SLLI max shift")
    
    # Shift right logical immediate
    await verify_alu_operation(dut, 16, 0, 2, 0x10, 0, 4, "SRLI")
    await verify_alu_operation(dut, 0x80000000, 0, 31, 0x10, 0, 1, "SRLI max shift")
    
    # Shift right arithmetic immediate
    await verify_alu_operation(dut, 16, 0, 2, 0x11, 0, 4, "SRAI positive")
    await verify_alu_operation(dut, 0x80000000, 0, 4, 0x11, 0, 0xF8000000, "SRAI negative")
    await verify_alu_operation(dut, 0x80000000, 0, 31, 0x11, 0, 0xFFFFFFFF, "SRAI max shift")

    # Set less than immediate (signed)
    await verify_alu_operation(dut, 10, 0, 20, 0x12, 0, 0xFFFFFFFF, "SLTI true")
    await verify_alu_operation(dut, 20, 0, 10, 0x12, 0, 0, "SLTI false")
    await verify_alu_operation(dut, 0x80000000, 0, 0, 0x12, 0, 0xFFFFFFFF, "SLTI negative < zero")
    
    # Set less than immediate (unsigned)
    await verify_alu_operation(dut, 10, 0, 20, 0x13, 0, 0xFFFFFFFF, "SLTIU true")
    await verify_alu_operation(dut, 20, 0, 10, 0x13, 0, 0, "SLTIU false")
    await verify_alu_operation(dut, 0x80000000, 0, 1, 0x13, 0, 0, "SLTIU MSB high > low (unsigned)")

@cocotb.test()
async def test_default(dut):
    """Test default operation (should output zero)"""
    await verify_alu_operation(dut, 0x1234, 0x8765, 0xABCDE, 0, 0x100, 0, "DEFAULT")
    await verify_alu_operation(dut, 0x1234, 0x8765, 0xABCDE, 0x26, 0x100, 0, "DEFAULT with invalid op")
    
@cocotb.test()
async def test_random_inputs(dut):
    """Test random inputs for all operations"""
    for _ in range(10):  # Run 10 random tests
        #generate rs1, rs2, imm, betweeen 0 to 2^32-1
        rs1 = random.randint(0, 0xFFFFFFFF)
        rs2 = random.randint(0, 0xFFFFFFFF)
        imm = random.randint(0, 0xFFFFFFFF)
        pc_input = random.randint(0, 0xFFFFFFFF)
        instr = random.randint(1, 0x13)
        
        # Calculate expected result based on instruction
        if instr == 0x1:  # ADD
            expected = (rs1 + rs2) & 0xFFFFFFFF
        elif instr == 0x2:  # SUB
            expected = (rs1 - rs2) & 0xFFFFFFFF
        elif instr == 0x3:  # XOR
            expected = rs1 ^ rs2
        elif instr == 0x4:  # OR
            expected = rs1 | rs2
        elif instr == 0x5:  # AND
            expected = rs1 & rs2
        elif instr == 0x6:  # SLL
            expected = (rs1 << (rs2 & 0x1F)) & 0xFFFFFFFF
        elif instr == 0x7:  # SRL
            expected = (rs1 >> (rs2 & 0x1F)) & 0xFFFFFFFF
        elif instr == 0x8:  # SRA
            # Python's >> is arithmetic for signed integers
            rs1_signed = rs1 if rs1 < 0x80000000 else rs1 - 0x100000000
            expected = ((rs1_signed >> (rs2 & 0x1F)) & 0xFFFFFFFF)
        elif instr == 0x9:  # SLT
            rs1_signed = rs1 if rs1 < 0x80000000 else rs1 - 0x100000000
            rs2_signed = rs2 if rs2 < 0x80000000 else rs2 - 0x100000000
            expected = 0xFFFFFFFF if rs1_signed < rs2_signed else 0
        elif instr == 0xA:  # SLTU
            expected = 0xFFFFFFFF if rs1 < rs2 else 0
        elif instr == 0xB:  # ADDI
            expected = (rs1 + imm) & 0xFFFFFFFF
        elif instr == 0xC:  # XORI
            expected = rs1 ^ imm
        elif instr == 0xD:  # ORI
            expected = rs1 | imm
        elif instr == 0xE:  # ANDI
            expected = rs1 & imm
        elif instr == 0xF:  # SLLI
            expected = (rs1 << (imm & 0x1F)) & 0xFFFFFFFF
        elif instr == 0x10:  # SRLI
            expected = (rs1 >> (imm & 0x1F)) & 0xFFFFFFFF
        elif instr == 0x11:  # SRAI
            rs1_signed = rs1 if rs1 < 0x80000000 else rs1 - 0x100000000
            expected = ((rs1_signed >> (imm & 0x1F)) & 0xFFFFFFFF)
        elif instr == 0x12:  # SLTI
            rs1_signed = rs1 if rs1 < 0x80000000 else rs1 - 0x100000000
            imm_signed = imm if imm < 0x80000000 else imm - 0x100000000
            expected = 0xFFFFFFFF if rs1_signed < imm_signed else 0
        elif instr == 0x13:  # SLTIU
            expected = 0xFFFFFFFF if rs1 < imm else 0
            
        await verify_alu_operation(dut, rs1, rs2, imm, instr, pc_input, expected, f"Random test instr=0x{instr:x}")

import pytest
from cocotb_test.simulator import run
import os

def runCocotbTests():
    """Run all tests"""
    # Define the test directory and files
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    incl_dir = os.path.join(rtl_dir, "include")
    verilog_file = os.path.join(rtl_dir, "core_modules", "alu.v")
    
    run(
        verilog_sources=[verilog_file],
        toplevel="alu",
        module="test_alu",
        simulator="verilator",
        includes=[incl_dir]
    )
