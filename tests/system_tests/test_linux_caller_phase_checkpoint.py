"""Checkpoint the real Linux caller/helper path at an exact repeated PC.

This lets us stop on a specific occurrence of a caller-side phase boundary,
such as:
- the helper return point at 0x80005668
- the post-xor/post-store round boundary at 0x8000568c

The software model and RTL are both halted on arrival at the same PC before
executing that instruction, then the helper state is compared in memory.
"""

import importlib.util
import os
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


HELPER_PATH = Path(__file__).with_name("test_linux_caller_stitch.py")
HELPER_SPEC = importlib.util.spec_from_file_location("linux_caller_stitch_helpers", HELPER_PATH)
HELPERS = importlib.util.module_from_spec(HELPER_SPEC)
HELPER_SPEC.loader.exec_module(HELPERS)

TARGET_PC = int(os.environ.get("LINUX_CALLER_CHECK_PC", "0x8000568c"), 16)
TARGET_OCCURRENCE = int(os.environ.get("LINUX_CALLER_CHECK_OCCURRENCE", "1"))
MODEL_OCCURRENCE = int(
    os.environ.get("LINUX_CALLER_MODEL_OCCURRENCE", str(TARGET_OCCURRENCE))
)
RTL_OCCURRENCE = int(
    os.environ.get("LINUX_CALLER_RTL_OCCURRENCE", str(TARGET_OCCURRENCE))
)
STATE_COMPARE_START = 8
STATE_COMPARE_SIZE = 0xC8


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _model_state_at_pc(
    initial_regs: list[int],
    initial_mem: dict[int, int],
    target_pc: int,
    target_occurrence: int,
):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    pc = HELPERS.RESET_PC
    seen = 0
    steps = 0
    max_steps = 30000

    while True:
        instr = HELPERS.PROGRAM_WORDS.get(pc, HELPERS.NOP)
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        next_pc = (pc + 4) & 0xFFFF_FFFF

        if pc == target_pc:
            seen += 1
            if seen == target_occurrence:
                break

        if opcode == 0x03:
            imm = HELPERS._sign_extend(instr >> 20, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x2:
                regs[rd] = HELPERS._read_word(mem, addr)
            elif funct3 == 0x4:
                regs[rd] = HELPERS._read_byte(mem, addr)
            else:
                raise AssertionError(f"Unexpected load: {instr:08x}")
        elif opcode == 0x23:
            imm = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
            imm = HELPERS._sign_extend(imm, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x0:
                HELPERS._write_byte(mem, addr, regs[rs2])
            elif funct3 == 0x2:
                HELPERS._write_word(mem, addr, regs[rs2])
            else:
                raise AssertionError(f"Unexpected store: {instr:08x}")
        elif opcode == 0x13:
            imm = HELPERS._sign_extend(instr >> 20, 12)
            shamt = (instr >> 20) & 0x1F
            if funct3 == 0x0:
                regs[rd] = (regs[rs1] + imm) & 0xFFFF_FFFF
            elif funct3 == 0x1:
                regs[rd] = (regs[rs1] << shamt) & 0xFFFF_FFFF
            elif funct3 == 0x5:
                assert funct7 == 0x00, f"Unexpected shift-right variant: {instr:08x}"
                regs[rd] = (regs[rs1] >> shamt) & 0xFFFF_FFFF
            elif funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ (imm & 0xFFFF_FFFF)) & 0xFFFF_FFFF
            elif funct3 == 0x6:
                regs[rd] = (regs[rs1] | (imm & 0xFFFF_FFFF)) & 0xFFFF_FFFF
            elif funct3 == 0x7:
                regs[rd] = regs[rs1] & (imm & 0xFFFF_FFFF)
            else:
                raise AssertionError(f"Unexpected I-type op: {instr:08x}")
        elif opcode == 0x17:
            regs[rd] = (pc + (instr & 0xFFFFF000)) & 0xFFFF_FFFF
        elif opcode == 0x37:
            regs[rd] = instr & 0xFFFFF000
        elif opcode == 0x33:
            if funct7 == 0x20 and funct3 == 0x0:
                regs[rd] = (regs[rs1] - regs[rs2]) & 0xFFFF_FFFF
            elif funct7 == 0x00 and funct3 == 0x0:
                regs[rd] = (regs[rs1] + regs[rs2]) & 0xFFFF_FFFF
            elif funct7 == 0x00 and funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ regs[rs2]) & 0xFFFF_FFFF
            elif funct7 == 0x00 and funct3 == 0x6:
                regs[rd] = (regs[rs1] | regs[rs2]) & 0xFFFF_FFFF
            elif funct7 == 0x00 and funct3 == 0x7:
                regs[rd] = regs[rs1] & regs[rs2]
            else:
                raise AssertionError(f"Unexpected R-type op: {instr:08x}")
        elif opcode == 0x63:
            imm = HELPERS._branch_imm(instr)
            take = False
            if funct3 == 0x0:
                take = regs[rs1] == regs[rs2]
            elif funct3 == 0x1:
                take = regs[rs1] != regs[rs2]
            elif funct3 == 0x7:
                take = (regs[rs1] & 0xFFFF_FFFF) >= (regs[rs2] & 0xFFFF_FFFF)
            else:
                raise AssertionError(f"Unexpected branch: {instr:08x}")
            if take:
                next_pc = (pc + imm) & 0xFFFF_FFFF
        elif opcode == 0x6F:
            regs[rd] = next_pc
            next_pc = (pc + HELPERS._jal_imm(instr)) & 0xFFFF_FFFF
        elif opcode == 0x67:
            imm = HELPERS._sign_extend(instr >> 20, 12)
            target = (regs[rs1] + imm) & 0xFFFF_FFFE
            regs[rd] = next_pc
            next_pc = target
        else:
            raise AssertionError(f"Unexpected opcode: {instr:08x} at pc=0x{pc:08x}")

        regs[0] = 0
        pc = next_pc
        steps += 1
        if steps > max_steps:
            raise AssertionError(
                f"Model did not reach pc=0x{target_pc:08x} occurrence {target_occurrence}"
            )

    return regs, mem


@cocotb.test()
async def test_linux_caller_phase_checkpoint_matches_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    init_regs, init_mem, _ = HELPERS._seed_state(0)
    expected_regs, expected_mem = _model_state_at_pc(
        init_regs,
        init_mem,
        TARGET_PC,
        MODEL_OCCURRENCE,
    )

    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    await HELPERS._load_trial_state(dut, init_regs, init_mem)
    dut.rst.value = 0

    seen = 0
    reached = False
    for _ in range(90000):
        await RisingEdge(dut.clk)
        if (int(dut.pc_debug.value) & 0xFFFF_FFFF) == TARGET_PC:
            seen += 1
            if seen == RTL_OCCURRENCE:
                reached = True
                break

    assert reached, (
        f"RTL never reached pc=0x{TARGET_PC:08x} occurrence {RTL_OCCURRENCE}"
    )

    ctx = init_regs[18]
    mismatches = []
    for addr in range(ctx + STATE_COMPARE_START, ctx + STATE_COMPARE_START + STATE_COMPARE_SIZE, 4):
        actual = int(dut.unified_mem_inst.instr_ram[HELPERS._phys_word_index(addr)].value) & 0xFFFF_FFFF
        expected = expected_mem.get(addr, 0) & 0xFFFF_FFFF
        if actual != expected:
            mismatches.append((addr, expected, actual))

    if mismatches:
        actual_regs = [
            int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
            for idx in range(32)
        ]
        expected_preview = ", ".join(
            f"0x{addr:08x}:exp=0x{expected:08x}/act=0x{actual:08x}"
            for addr, expected, actual in mismatches[:12]
        )
        raise AssertionError(
            f"Checkpoint mismatch at pc=0x{TARGET_PC:08x} "
            f"(model_occ={MODEL_OCCURRENCE}, rtl_occ={RTL_OCCURRENCE}) "
            f"(count={len(mismatches)}): {expected_preview}; "
            f"s1=0x{actual_regs[9]:08x} s2=0x{actual_regs[18]:08x} s3=0x{actual_regs[19]:08x} "
            f"s6=0x{actual_regs[22]:08x} a0=0x{actual_regs[10]:08x} a2=0x{actual_regs[12]:08x} "
            f"a3=0x{actual_regs[13]:08x} a4=0x{actual_regs[14]:08x} a5=0x{actual_regs[15]:08x}"
        )

    actual_regs = [
        int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
        for idx in range(32)
    ]
    assert actual_regs == expected_regs, (
        f"Register mismatch at pc=0x{TARGET_PC:08x} "
        f"(model_occ={MODEL_OCCURRENCE}, rtl_occ={RTL_OCCURRENCE}): "
        f"expected={[hex(v) for v in expected_regs]}, actual={[hex(v) for v in actual_regs]}"
    )


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    incl_dir = rtl_dir / "include"

    sources = []
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith((".v", ".sv")):
                sources.append(os.path.join(root, file))

    sim_build = (
        Path.cwd()
        / "sim_build"
        / f"sim_build_linux_caller_phase_{TARGET_PC:08x}_{MODEL_OCCURRENCE}_{RTL_OCCURRENCE}"
    )
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_linux_caller_phase_checkpoint",
        testcase="test_linux_caller_phase_checkpoint_matches_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
