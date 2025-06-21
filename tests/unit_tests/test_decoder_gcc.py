import cocotb
from cocotb.triggers import Timer
import subprocess
import os

def assemble_riscv_instruction(assembly_code, bin_file="temp.bin"):
    with open("temp.s", "w") as f:
        f.write(assembly_code)

    subprocess.run([
        "riscv64-unknown-elf-as", "-march=rv32i_zifencei", "-mabi=ilp32", "-o", "temp.o", "temp.s"
    ], check=True)

    subprocess.run([
        "riscv64-unknown-elf-ld", "-melf32lriscv", "-Ttext=0x0", "-o", "temp.elf", "temp.o", "--entry=_start", "--nostdlib"
    ], check=True)

    subprocess.run([
        "riscv64-unknown-elf-objcopy", "-O", "binary", "--only-section=.text", "temp.elf", bin_file
    ], check=True)

    # cleanup
    os.remove("temp.s")
    os.remove("temp.o")
    os.remove("temp.elf")

def encode_instruction(instruction):
    if isinstance(instruction, str):
        # single-line case
        assembly_code = f"""
        .section .text
        .globl _start
        _start:
            {instruction}
        """
    else:
        # multiline block
        assembly_code = instruction[0]

    bin_file = "temp.bin"
    assemble_riscv_instruction(assembly_code, bin_file)
    with open(bin_file, "rb") as f:
        encoded_instr = int.from_bytes(f.read(4), byteorder="little")
    os.remove(bin_file)
    return encoded_instr


"""
Test the RISC-V instruction decoder using an exhaustive set of instructions.

This test verifies that the decoder correctly extracts the opcode, source 
registers (rs1, rs2), destination register (rd), immediate value (imm), and 
instruction ID (instr_id) from a variety of RISC-V instructions. The test 
covers different instruction types, including R-type, I-type, S-type, B-type, 
U-type, and J-type.

Instructions tested:
- R-type: add, sub
- I-type: addi, lw
- S-type: sw
- B-type: beq
- J-type: jal
- U-type: lui

Each instruction is encoded using the `encode_instruction` function, and the 
resulting binary is applied to the `dut.instr` signal. The test then waits for 
10 ns and checks that the decoded fields in the DUT match the expected values.

Assertions:
- `dut.opcode.value` matches the expected opcode.
- `dut.rs1.value` matches the expected source register 1.
- `dut.rs2.value` matches the expected source register 2.
- `dut.rd.value` matches the expected destination register.
- `dut.imm.value` matches the expected immediate value (if applicable).
- `dut.instr_id.value.integer` matches the expected instruction ID.

Raises:
- AssertionError: If any of the decoded fields do not match the expected values.
"""
@cocotb.test()
async def test_decoder_exhaustive(dut):
    instructions = [
        ("add x1, x2, x3", {"opcode": 0b0110011, "rs1": 2, "rs2": 3, "rd": 1, "instr_id": 0x01}),
        ("sub x4, x5, x6", {"opcode": 0b0110011, "rs1": 5, "rs2": 6, "rd": 4, "instr_id": 0x02}),
        ("addi x7, x8, 10", {"opcode": 0b0010011, "rs1": 8, "rs2": 0, "rd": 7, "instr_id": 0x0B, "imm": 10}),
        ("lw x9, 0(x10)", {"opcode": 0b0000011, "rs1": 10, "rs2": 0, "rd": 9, "instr_id": 0x16, "imm": 0}),
        ("sw x11, 4(x12)", {"opcode": 0b0100011, "rs1": 12, "rs2": 11, "rd": 0, "instr_id": 0x1B, "imm": 4}),
        ("""
        .section .text
        .globl _start
        _start:
            beq x13, x14, target
            nop
        target:
        """, {"opcode": 0b1100011, "rs1": 13, "rs2": 14, "rd": 0, "instr_id": 0x1C, "imm": 8}),
        ("jal x15, 16", {"opcode": 0b1101111, "rs1": 0, "rs2": 0, "rd": 15, "instr_id": 0x22, "imm": 16}),
        ("lui x16, 0x12345", {"opcode": 0b0110111, "rs1": 0, "rs2": 0, "rd": 16, "instr_id": 0x24, "imm": 0x12345000}),
        # Add fence.i test
        ("fence.i", {"opcode": 0b0001111, "rs1": 0, "rs2": 0, "rd": 0, "instr_id": 0x26, "imm": 0}),
    ]

    for instr, expected in instructions:
        encoded = encode_instruction(instr)
        dut.instr.value = encoded
        await Timer(10, units="ns")

        assert dut.opcode.value == expected["opcode"], f"{instr}: opcode mismatch"
        assert dut.rs1.value == expected.get("rs1", 0), f"{instr}: rs1 mismatch"
        assert dut.rs2.value == expected.get("rs2", 0), f"{instr}: rs2 mismatch"
        assert dut.rd.value == expected.get("rd", 0), f"{instr}: rd mismatch"
        if "imm" in expected:
            assert dut.imm.value == expected["imm"], f"{instr}: imm mismatch"
        assert dut.instr_id.value.integer == expected["instr_id"], f"{instr}: instr_id mismatch"

import pytest
from cocotb_test.simulator import run

def runCocotbTests():
    """Run all tests"""

    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    incl_dir = os.path.join(rtl_dir, "include")
    instr_defines_file = os.path.join(rtl_dir, "instr_defines.vh")
    decoder_file = os.path.join(rtl_dir, "core_modules", "decoder.v")

    run(
        verilog_sources=[
            decoder_file        
        ],
        toplevel="decoder",
        module="test_decoder_gcc",
        simulator="verilator",
        includes=[str(incl_dir)],
    )