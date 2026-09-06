"""Execute Linux byte-oriented loops on the CPU and compare them against a
tiny software interpreter.

These loops were extracted from the repeatedly executed Linux region around
0xc02555e0..0xc02556f4. Unlike the earlier straight-line hot block, they
exercise taken back-edges plus byte loads and stores (`lbu`/`sb`).
"""

import os
import random
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

NOP = 0x00000013
NUM_TRIALS = 25

# Linux loop at 0xc02555e0..0xc025564c.
MIX_BYTES_LOOP = [
    0x0017C803, 0x0057C503, 0x0007CE03, 0x0047C883, 0x0027C583, 0x0067C603,
    0x0037C683, 0x0077C703, 0x00881813, 0x00851513, 0x01C86833, 0x01156533,
    0xF2C7AE03, 0xF307A883, 0x01059593, 0x01061613, 0x0105E5B3, 0x01869693,
    0x00A66633, 0x01871713, 0x00B6E6B3, 0x00C76733, 0x00DE46B3, 0x00E8C733,
    0xF2D7A623, 0xF2E7A823, 0x00878793, 0xF8679AE3,
]

# Linux loop at 0xc02556a8..0xc02556f4.
STORE_BYTES_LOOP = [
    0x0005A683, 0x0045A703, 0x00060793, 0x0086DE93, 0x01D600A3, 0x00D60023,
    0x00E60223, 0x0106DE13, 0x0186D313, 0x00875893, 0x01075813, 0x01875513,
    0x00860613, 0x01C78123, 0x006781A3, 0x011782A3, 0x01078323, 0x00A783A3,
    0x00858593, 0xFBE61AE3,
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


def _read_word(memory: dict[int, int], addr: int) -> int:
    return memory.get(addr & 0xFFFF_FFFC, 0) & 0xFFFF_FFFF


def _write_word(memory: dict[int, int], addr: int, value: int) -> None:
    memory[addr & 0xFFFF_FFFC] = value & 0xFFFF_FFFF


def _read_byte(memory: dict[int, int], addr: int) -> int:
    word = _read_word(memory, addr)
    shift = (addr & 0x3) * 8
    return (word >> shift) & 0xFF


def _write_byte(memory: dict[int, int], addr: int, value: int) -> None:
    word_addr = addr & 0xFFFF_FFFC
    shift = (addr & 0x3) * 8
    mask = 0xFF << shift
    word = _read_word(memory, word_addr)
    memory[word_addr] = (word & ~mask) | ((value & 0xFF) << shift)


def _branch_imm(instr: int) -> int:
    imm = (
        ((instr >> 31) & 0x1) << 12
        | ((instr >> 7) & 0x1) << 11
        | ((instr >> 25) & 0x3F) << 5
        | ((instr >> 8) & 0xF) << 1
    )
    return _sign_extend(imm, 13)


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


def _seed_words(memory: dict[int, int], start: int, end: int, rng: random.Random) -> set[int]:
    watched = set()
    word_start = start & 0xFFFF_FFFC
    word_end = (end + 3) & 0xFFFF_FFFC
    for addr in range(word_start, word_end, 4):
        memory[addr] = rng.getrandbits(32)
        watched.add(addr)
    return watched


def _seed_mix_loop(seed: int):
    rng = random.Random(seed)
    regs = [rng.getrandbits(32) for _ in range(32)]
    regs[0] = 0

    iterations = rng.randint(1, 6)
    ptr = DATA_MEM_BASE + 0x2000 + (seed * 0x40)
    end = ptr + (iterations * 8)

    regs[6] = end
    regs[15] = ptr

    mem: dict[int, int] = {}
    watched = set()
    watched |= _seed_words(mem, ptr, end + 8, rng)
    watched |= _seed_words(mem, ptr - 0x100, end - 0xC8, rng)

    return regs, mem, watched


def _seed_store_loop(seed: int):
    rng = random.Random(0x1000 + seed)
    regs = [rng.getrandbits(32) for _ in range(32)]
    regs[0] = 0

    iterations = rng.randint(1, 6)
    src = DATA_MEM_BASE + 0x5000 + (seed * 0x40)
    dst = DATA_MEM_BASE + 0x7000 + (seed * 0x40)
    end = dst + (iterations * 8)

    regs[11] = src
    regs[12] = dst
    regs[30] = end

    mem: dict[int, int] = {}
    watched = set()
    watched |= _seed_words(mem, src, src + (iterations * 8), rng)
    watched |= _seed_words(mem, dst, end, rng)

    return regs, mem, watched


def _execute_program(program: list[int], initial_regs: list[int], initial_mem: dict[int, int]):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    pc = 0
    steps = 0
    max_steps = 4096

    while 0 <= pc < len(program) * 4:
        instr = program[pc // 4]
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        next_pc = pc + 4

        if opcode == 0x03:
            imm = _sign_extend(instr >> 20, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x2:
                regs[rd] = _read_word(mem, addr)
            elif funct3 == 0x4:
                regs[rd] = _read_byte(mem, addr)
            else:
                raise AssertionError(f"Unexpected load in loop: {instr:08x}")
        elif opcode == 0x23:
            imm = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
            imm = _sign_extend(imm, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x0:
                _write_byte(mem, addr, regs[rs2])
            elif funct3 == 0x2:
                _write_word(mem, addr, regs[rs2])
            else:
                raise AssertionError(f"Unexpected store in loop: {instr:08x}")
        elif opcode == 0x13:
            imm = _sign_extend(instr >> 20, 12)
            shamt = (instr >> 20) & 0x1F
            if funct3 == 0x0:
                regs[rd] = (regs[rs1] + imm) & 0xFFFF_FFFF
            elif funct3 == 0x1:
                regs[rd] = (regs[rs1] << shamt) & 0xFFFF_FFFF
            elif funct3 == 0x5:
                assert funct7 == 0x00, f"Unexpected shift-right variant: {instr:08x}"
                regs[rd] = (regs[rs1] >> shamt) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected I-type op in loop: {instr:08x}")
        elif opcode == 0x33:
            if funct7 != 0x00:
                raise AssertionError(f"Unexpected R-type funct7 in loop: {instr:08x}")
            if funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ regs[rs2]) & 0xFFFF_FFFF
            elif funct3 == 0x6:
                regs[rd] = (regs[rs1] | regs[rs2]) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected R-type op in loop: {instr:08x}")
        elif opcode == 0x63:
            assert funct3 == 0x1, f"Unexpected branch in loop: {instr:08x}"
            if regs[rs1] != regs[rs2]:
                next_pc = (pc + _branch_imm(instr)) & 0xFFFF_FFFF
        else:
            raise AssertionError(f"Unexpected opcode in loop: {instr:08x}")

        regs[0] = 0
        pc = next_pc
        steps += 1
        if steps > max_steps:
            raise AssertionError("Program did not terminate in model")

    return regs, mem, steps


async def _load_trial_state(dut, program: list[int], regs: list[int], mem: dict[int, int]) -> None:
    for idx in range(0, len(program) + 16):
        word = program[idx] if idx < len(program) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for addr, value in mem.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value

    for reg_idx, value in enumerate(regs):
        dut.cpu_inst.rf_inst0.register_file[reg_idx].value = value


@cocotb.test()
async def test_linux_byte_loops_match_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    scenarios = [
        ("mix-bytes", MIX_BYTES_LOOP, _seed_mix_loop),
        ("store-bytes", STORE_BYTES_LOOP, _seed_store_loop),
    ]

    for scenario_name, program, seed_state in scenarios:
        for seed in range(NUM_TRIALS):
            init_regs, init_mem, watched_words = seed_state(seed)
            expected_regs, expected_mem, step_count = _execute_program(program, init_regs, init_mem)

            dut.rst.value = 1
            await ClockCycles(dut.clk, 3)
            await _load_trial_state(dut, program, init_regs, init_mem)
            dut.rst.value = 0

            for _ in range(step_count + 32):
                await RisingEdge(dut.clk)

            actual_regs = [
                int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
                for idx in range(32)
            ]

            assert actual_regs == expected_regs, (
                f"{scenario_name} register mismatch on seed {seed}: "
                f"expected={[hex(v) for v in expected_regs]}, "
                f"actual={[hex(v) for v in actual_regs]}"
            )

            for addr in sorted(watched_words):
                actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF
                expected = expected_mem.get(addr, 0) & 0xFFFF_FFFF
                assert actual == expected, (
                    f"{scenario_name} memory mismatch on seed {seed} at 0x{addr:08x}: "
                    f"expected=0x{expected:08x} actual=0x{actual:08x}"
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_linux_byte_loops"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_linux_byte_loops",
        testcase="test_linux_byte_loops_match_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
