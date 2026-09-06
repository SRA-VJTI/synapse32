"""Run the two-iteration Linux round tail with a tiny stacky helper stub.

This checks whether ordinary call/return plus the round-tail loop is enough to
trigger the corruption, or whether the real Linux helper body is required.
"""

import importlib.util
import os
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


STITCH_PATH = Path(__file__).with_name("test_linux_caller_stitch.py")
STITCH_SPEC = importlib.util.spec_from_file_location("linux_caller_stitch_helpers", STITCH_PATH)
STITCH = importlib.util.module_from_spec(STITCH_SPEC)
STITCH_SPEC.loader.exec_module(STITCH)

PHASE_PATH = Path(__file__).with_name("test_linux_caller_phase_checkpoint.py")
PHASE_SPEC = importlib.util.spec_from_file_location("linux_caller_phase_helpers", PHASE_PATH)
PHASE = importlib.util.module_from_spec(PHASE_SPEC)
PHASE_SPEC.loader.exec_module(PHASE)


INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000
RESET_PC = INSTR_MEM_BASE
DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC
ROUND_LOOP_START = 0x8000_5660
ROUND_LOOP_END = 0x8000_5690
HELPER_BASE = 0x8000_4800
STATE_COMPARE_SIZE = 0x20

NOP = 0x00000013

RETURN_SENTINEL_WORDS = [
    0x100002B7,
    0x00100E13,
    0x0FC28FA3,
    0x0000006F,
]

# addi sp,-16 ; sw ra,12(sp) ; sw s0,8(sp) ; addi s0,sp,16 ; lw s0,8(sp) ;
# lw ra,12(sp) ; addi sp,16 ; ret
HELPER_STUB_WORDS = [
    0xFF010113,
    0x00112623,
    0x00812423,
    0x01010413,
    0x00812403,
    0x00C12083,
    0x01010113,
    0x00008067,
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _encode_jal(rd: int, src_pc: int, target_pc: int) -> int:
    offset = target_pc - src_pc
    assert offset % 2 == 0
    assert -(1 << 20) <= offset < (1 << 20)
    imm = offset & 0x1F_FFFF
    return (
        (((imm >> 20) & 0x1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 0x1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | (rd << 7)
        | 0x6F
    )


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


PROGRAM_WORDS = {}
PROGRAM_WORDS[RESET_PC] = _encode_jal(0, RESET_PC, ROUND_LOOP_START)
for addr in range(ROUND_LOOP_START, ROUND_LOOP_END, 4):
    word = STITCH.PROGRAM_WORDS[addr]
    if addr == 0x8000_5664:
        word = _encode_jal(1, 0x8000_5664, HELPER_BASE)
    PROGRAM_WORDS[addr] = word
for idx, word in enumerate(HELPER_STUB_WORDS):
    PROGRAM_WORDS[HELPER_BASE + idx * 4] = word
for addr in range(STITCH.RELOC_TABLE_START, STITCH.RELOC_TABLE_START + 0x20, 4):
    PROGRAM_WORDS[addr] = STITCH.PROGRAM_WORDS[addr]
for idx, word in enumerate(RETURN_SENTINEL_WORDS):
    PROGRAM_WORDS[ROUND_LOOP_END + idx * 4] = word


def _entry_state():
    init_regs, init_mem, _ = STITCH._seed_state(0)
    regs, mem = PHASE._model_state_at_pc(init_regs, init_mem, ROUND_LOOP_START, 1)
    regs = regs[:]
    regs[0] = 0
    regs[22] = (regs[9] + 16) & 0xFFFF_FFFF
    return regs, mem


def _execute_program(initial_regs: list[int], initial_mem: dict[int, int]):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    pc = ROUND_LOOP_START
    steps = 0
    max_steps = 400

    while True:
        instr = PROGRAM_WORDS.get(pc, NOP)
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        next_pc = (pc + 4) & 0xFFFF_FFFF

        if pc == ROUND_LOOP_END + 12:
            break

        if opcode == 0x03:
            imm = STITCH._sign_extend(instr >> 20, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            regs[rd] = STITCH._read_word(mem, addr)
        elif opcode == 0x23:
            imm = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
            imm = STITCH._sign_extend(imm, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x0:
                STITCH._write_byte(mem, addr, regs[rs2])
            else:
                STITCH._write_word(mem, addr, regs[rs2])
        elif opcode == 0x13:
            imm = STITCH._sign_extend(instr >> 20, 12)
            if funct3 == 0x0:
                regs[rd] = (regs[rs1] + imm) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected I-type op: {instr:08x}")
        elif opcode == 0x33:
            if funct7 == 0x00 and funct3 == 0x0:
                regs[rd] = (regs[rs1] + regs[rs2]) & 0xFFFF_FFFF
            elif funct7 == 0x00 and funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ regs[rs2]) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected R-type op: {instr:08x}")
        elif opcode == 0x63:
            imm = STITCH._branch_imm(instr)
            assert funct3 == 0x1, f"Unexpected branch: {instr:08x}"
            if regs[rs1] != regs[rs2]:
                next_pc = (pc + imm) & 0xFFFF_FFFF
        elif opcode == 0x6F:
            regs[rd] = next_pc
            next_pc = (pc + STITCH._jal_imm(instr)) & 0xFFFF_FFFF
        elif opcode == 0x67:
            imm = STITCH._sign_extend(instr >> 20, 12)
            target = (regs[rs1] + imm) & 0xFFFF_FFFE
            regs[rd] = next_pc
            next_pc = target
        elif opcode == 0x37:
            regs[rd] = instr & 0xFFFFF000
        else:
            raise AssertionError(f"Unexpected opcode: {instr:08x} at pc=0x{pc:08x}")

        regs[0] = 0
        pc = next_pc
        steps += 1
        if steps > max_steps:
            raise AssertionError("Stub-helper round loop did not terminate in model")

    return regs, mem


async def _load_trial_state(dut, regs: list[int], mem: dict[int, int]) -> None:
    for addr, word in PROGRAM_WORDS.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = word

    for addr, value in mem.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value

    for reg_idx, value in enumerate(regs):
        dut.cpu_inst.rf_inst0.register_file[reg_idx].value = value


@cocotb.test()
async def test_round_loop_two_iter_stub_helper_matches_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    init_regs, init_mem = _entry_state()
    expected_regs, expected_mem = _execute_program(init_regs, init_mem)

    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    await _load_trial_state(dut, init_regs, init_mem)
    dut.rst.value = 0

    done = False
    for _ in range(2000):
        await RisingEdge(dut.clk)
        done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Stub-helper round loop test never completed"

    ctx = init_regs[18]
    mismatches = []
    for addr in range(ctx + 8, ctx + 8 + STATE_COMPARE_SIZE, 4):
        actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF
        expected = expected_mem.get(addr, 0) & 0xFFFF_FFFF
        if actual != expected:
            mismatches.append((addr, expected, actual))

    preview = ", ".join(
        f"0x{addr:08x}:exp=0x{expected:08x}/act=0x{actual:08x}"
        for addr, expected, actual in mismatches[:8]
    ) or "none"
    assert not mismatches, f"Stub-helper round-loop mismatch: {preview}"

    actual_regs = [
        int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
        for idx in range(32)
    ]
    assert actual_regs == expected_regs, (
        f"Register mismatch in stub-helper round loop: "
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_round_loop_two_iter_stub_helper"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_round_loop_two_iter_stub_helper",
        testcase="test_round_loop_two_iter_stub_helper_matches_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
