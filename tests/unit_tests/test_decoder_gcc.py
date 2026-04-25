import cocotb
from cocotb.triggers import Timer
import subprocess
import os
import sys
import re
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def prepend_to_path(*path_entries: str):
    """Temporarily prepend directories to PATH for simulator subprocesses."""
    entries = [entry for entry in path_entries if entry]
    if not entries:
        yield
        return

    original_path = os.environ.get("PATH")
    prefix = os.pathsep.join(entries)
    new_path = prefix if not original_path else f"{prefix}{os.pathsep}{original_path}"
    os.environ["PATH"] = new_path
    try:
        yield
    finally:
        if original_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = original_path

def assemble_riscv_instruction(assembly_code, bin_file="temp.bin"):
    with open("temp.s", "w") as f:
        f.write(assembly_code)

    subprocess.run([
        "riscv64-unknown-elf-as", "-march=rv32ima_zalrsc_zaamo_zifencei", "-mabi=ilp32", "-o", "temp.o", "temp.s"
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


_INSTR_ID_RE = re.compile(r"localparam\s+\[6:0\]\s+(\w+)\s*=\s*7'h([0-9A-Fa-f]+)")
_INSTR_IDS = None


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        cur = cur.parent
    return cur


def _instr_id(name: str) -> int:
    global _INSTR_IDS
    if _INSTR_IDS is None:
        defines = _find_repo_root() / "rtl" / "include" / "instr_defines.vh"
        text = defines.read_text(encoding="ascii")
        _INSTR_IDS = {k: int(v, 16) for k, v in _INSTR_ID_RE.findall(text)}
    return _INSTR_IDS[name]


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
        ("add x1, x2, x3", {"opcode": 0b0110011, "rs1": 2, "rs2": 3, "rd": 1, "instr_id": _instr_id("INSTR_ADD"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("sub x4, x5, x6", {"opcode": 0b0110011, "rs1": 5, "rs2": 6, "rd": 4, "instr_id": _instr_id("INSTR_SUB"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("addi x7, x8, 10", {"opcode": 0b0010011, "rs1": 8, "rs2": 0, "rd": 7, "instr_id": _instr_id("INSTR_ADDI"), "imm": 10, "rs1_valid": 1, "rs2_valid": 0, "rd_valid": 1}),
        ("lw x9, 0(x10)", {"opcode": 0b0000011, "rs1": 10, "rs2": 0, "rd": 9, "instr_id": _instr_id("INSTR_LW"), "imm": 0, "rs1_valid": 1, "rs2_valid": 0, "rd_valid": 1}),
        ("sw x11, 4(x12)", {"opcode": 0b0100011, "rs1": 12, "rs2": 11, "rd": 0, "instr_id": _instr_id("INSTR_SW"), "imm": 4, "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 0}),
        ("""
        .section .text
        .globl _start
        _start:
            beq x13, x14, target
            nop
        target:
        """, {"opcode": 0b1100011, "rs1": 13, "rs2": 14, "rd": 0, "instr_id": _instr_id("INSTR_BEQ"), "imm": 8, "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 0}),
        ("jal x15, 16", {"opcode": 0b1101111, "rs1": 0, "rs2": 0, "rd": 15, "instr_id": _instr_id("INSTR_JAL"), "imm": 16, "rs1_valid": 0, "rs2_valid": 0, "rd_valid": 1}),
        ("lui x16, 0x12345", {"opcode": 0b0110111, "rs1": 0, "rs2": 0, "rd": 16, "instr_id": _instr_id("INSTR_LUI"), "imm": 0x12345000, "rs1_valid": 0, "rs2_valid": 0, "rd_valid": 1}),
        ("fence.i", {"opcode": 0b0001111, "rs1": 0, "rs2": 0, "rd": 0, "instr_id": _instr_id("INSTR_FENCE_I"), "imm": 0, "rs1_valid": 0, "rs2_valid": 0, "rd_valid": 0}),
        ("mul x1, x2, x3", {"opcode": 0b0110011, "rs1": 2, "rs2": 3, "rd": 1, "instr_id": _instr_id("INSTR_MUL"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("mulh x4, x5, x6", {"opcode": 0b0110011, "rs1": 5, "rs2": 6, "rd": 4, "instr_id": _instr_id("INSTR_MULH"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("mulhsu x7, x8, x9", {"opcode": 0b0110011, "rs1": 8, "rs2": 9, "rd": 7, "instr_id": _instr_id("INSTR_MULHSU"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("mulhu x10, x11, x12", {"opcode": 0b0110011, "rs1": 11, "rs2": 12, "rd": 10, "instr_id": _instr_id("INSTR_MULHU"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("div x13, x14, x15", {"opcode": 0b0110011, "rs1": 14, "rs2": 15, "rd": 13, "instr_id": _instr_id("INSTR_DIV"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("divu x16, x17, x18", {"opcode": 0b0110011, "rs1": 17, "rs2": 18, "rd": 16, "instr_id": _instr_id("INSTR_DIVU"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("rem x19, x20, x21", {"opcode": 0b0110011, "rs1": 20, "rs2": 21, "rd": 19, "instr_id": _instr_id("INSTR_REM"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("remu x22, x23, x24", {"opcode": 0b0110011, "rs1": 23, "rs2": 24, "rd": 22, "instr_id": _instr_id("INSTR_REMU"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("lr.w x5, (x6)", {"opcode": 0b0101111, "rs1": 6, "rs2": 0, "rd": 5, "instr_id": _instr_id("INSTR_LR_W"), "rs1_valid": 1, "rs2_valid": 0, "rd_valid": 1}),
        ("sc.w x7, x8, (x9)", {"opcode": 0b0101111, "rs1": 9, "rs2": 8, "rd": 7, "instr_id": _instr_id("INSTR_SC_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amoswap.w x10, x11, (x12)", {"opcode": 0b0101111, "rs1": 12, "rs2": 11, "rd": 10, "instr_id": _instr_id("INSTR_AMOSWAP_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amoadd.w x13, x14, (x15)", {"opcode": 0b0101111, "rs1": 15, "rs2": 14, "rd": 13, "instr_id": _instr_id("INSTR_AMOADD_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amoand.w x16, x17, (x18)", {"opcode": 0b0101111, "rs1": 18, "rs2": 17, "rd": 16, "instr_id": _instr_id("INSTR_AMOAND_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amoor.w x19, x20, (x21)", {"opcode": 0b0101111, "rs1": 21, "rs2": 20, "rd": 19, "instr_id": _instr_id("INSTR_AMOOR_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amoxor.w x22, x23, (x24)", {"opcode": 0b0101111, "rs1": 24, "rs2": 23, "rd": 22, "instr_id": _instr_id("INSTR_AMOXOR_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amomax.w x25, x26, (x27)", {"opcode": 0b0101111, "rs1": 27, "rs2": 26, "rd": 25, "instr_id": _instr_id("INSTR_AMOMAX_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amomin.w x28, x29, (x30)", {"opcode": 0b0101111, "rs1": 30, "rs2": 29, "rd": 28, "instr_id": _instr_id("INSTR_AMOMIN_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amomaxu.w x1, x2, (x3)", {"opcode": 0b0101111, "rs1": 3, "rs2": 2, "rd": 1, "instr_id": _instr_id("INSTR_AMOMAXU_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
        ("amominu.w x4, x5, (x6)", {"opcode": 0b0101111, "rs1": 6, "rs2": 5, "rd": 4, "instr_id": _instr_id("INSTR_AMOMINU_W"), "rs1_valid": 1, "rs2_valid": 1, "rd_valid": 1}),
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
        if "rs1_valid" in expected:
            assert int(dut.rs1_valid.value) == expected["rs1_valid"], f"{instr}: rs1_valid mismatch"
        if "rs2_valid" in expected:
            assert int(dut.rs2_valid.value) == expected["rs2_valid"], f"{instr}: rs2_valid mismatch"
        if "rd_valid" in expected:
            assert int(dut.rd_valid.value) == expected["rd_valid"], f"{instr}: rd_valid mismatch"
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

    tools_dir = os.path.join(root_dir, "tests", "tools")
    python_dir = os.path.dirname(sys.executable)
    with prepend_to_path(tools_dir, python_dir):
        run(
            verilog_sources=[
                decoder_file        
            ],
            toplevel="decoder",
            module="test_decoder_gcc",
            simulator="verilator",
            includes=[str(incl_dir)],
            extra_env={"PYTHON3": sys.executable},
        )
