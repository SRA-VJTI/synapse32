"""Run the final Linux caller tail from the proven-good pre-memset state."""

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

PRESTOP_PATH = Path(__file__).with_name("test_linux_caller_prestop.py")
PRESTOP_SPEC = importlib.util.spec_from_file_location("linux_caller_prestop_helpers", PRESTOP_PATH)
PRESTOP = importlib.util.module_from_spec(PRESTOP_SPEC)
PRESTOP_SPEC.loader.exec_module(PRESTOP)


INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

TAIL_START = 0x8000_5730
TAIL_END = 0x8000_5770
DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC
STATE_COMPARE_SIZE = 0x20
TEST_SEED = int(os.environ.get("LINUX_TAIL_SEED", "0"))

NOP = 0x00000013


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


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


PROGRAM_WORDS = {INSTR_MEM_BASE: _encode_jal(0, INSTR_MEM_BASE, TAIL_START)}
for addr, word in HELPERS.PROGRAM_WORDS.items():
    if TAIL_START <= addr < TAIL_END:
        PROGRAM_WORDS[addr] = word
    elif HELPERS.RELOC_MEMSET_TARGET <= addr < (HELPERS.RELOC_MEMSET_TARGET + len(HELPERS.MEMSET_STUB_WORDS) * 4):
        PROGRAM_WORDS[addr] = word
    elif HELPERS.RETURN_SENTINEL <= addr < (HELPERS.RETURN_SENTINEL + len(HELPERS.RETURN_SENTINEL_WORDS) * 4):
        PROGRAM_WORDS[addr] = word


def _tail_entry_state(seed: int):
    init_regs, init_mem, _ = HELPERS._seed_state(seed)
    regs, mem = PRESTOP._run_model_until(PRESTOP.STOP_PC, init_regs, init_mem)
    regs = regs[:]
    regs[0] = 0
    return regs, mem


def _execute_program(initial_regs: list[int], initial_mem: dict[int, int]):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    pc = TAIL_START
    steps = 0
    max_steps = 12000

    while True:
        instr = PROGRAM_WORDS.get(pc, NOP)
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        next_pc = (pc + 4) & 0xFFFF_FFFF

        if pc == HELPERS.RETURN_SENTINEL + 12:
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
            if funct3 == 0x0:
                regs[rd] = (regs[rs1] + imm) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected I-type op: {instr:08x}")
        elif opcode == 0x17:
            regs[rd] = (pc + (instr & 0xFFFFF000)) & 0xFFFF_FFFF
        elif opcode == 0x37:
            regs[rd] = instr & 0xFFFFF000
        elif opcode == 0x63:
            imm = HELPERS._branch_imm(instr)
            take = False
            if funct3 == 0x0:
                take = regs[rs1] == regs[rs2]
            elif funct3 == 0x1:
                take = regs[rs1] != regs[rs2]
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
            raise AssertionError("Memset tail test did not terminate in model")

    return regs, mem


async def _load_trial_state(dut, regs: list[int], mem: dict[int, int]) -> None:
    for addr, word in PROGRAM_WORDS.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = word

    for addr, value in mem.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value

    for reg_idx, value in enumerate(regs):
        dut.cpu_inst.rf_inst0.register_file[reg_idx].value = value


@cocotb.test()
async def test_linux_memset_tail_matches_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    init_regs, init_mem = _tail_entry_state(TEST_SEED)
    expected_regs, expected_mem = _execute_program(init_regs, init_mem)

    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    await _load_trial_state(dut, init_regs, init_mem)
    dut.rst.value = 0

    done = False
    for _ in range(12000):
        await RisingEdge(dut.clk)
        done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Memset tail test never completed"

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
    assert not mismatches, f"Memset tail mismatch on seed {TEST_SEED}: {preview}"

    actual_regs = [
        int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
        for idx in range(32)
    ]
    assert actual_regs == expected_regs, (
        f"Register mismatch in memset tail test on seed {TEST_SEED}: "
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_linux_memset_tail"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_linux_memset_tail",
        testcase="test_linux_memset_tail_matches_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
