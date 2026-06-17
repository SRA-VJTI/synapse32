"""Exercise a small multi-round state recurrence with helper calls.

Each round:
- helper loads state words from memory and writes transformed values back
- caller loads round constants from instruction-memory space
- caller xors those constants into the same state words and stores them
- next round immediately reloads that state

This mirrors the shape of the Linux failing path without the full Keccak body.
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
DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC
STATE_ADDR = DATA_MEM_BASE + 0x200
TABLE_ADDR = 0x80DC_2648

NOP = 0x00000013
NUM_TRIALS = 25

PROGRAM_WORDS = [
    0x100002B7,  # lui t0, 0x10000
    0x20028913,  # addi s2, t0, 0x200
    0x80DC24B7,  # lui s1, 0x80dc2
    0x64848493,  # addi s1, s1, 0x648
    0x01048993,  # addi s3, s1, 16
    0x00090513,  # mv a0, s2
    0x048000EF,  # jal ra, helper
    0x0004A303,  # lw t1, 0(s1)
    0x0044A383,  # lw t2, 4(s1)
    0x00092E03,  # lw t3, 0(s2)
    0x00492E83,  # lw t4, 4(s2)
    0x00848493,  # addi s1, s1, 8
    0x006E4E33,  # xor t3, t3, t1
    0x007ECEB3,  # xor t4, t4, t2
    0x01C92023,  # sw t3, 0(s2)
    0x01D92223,  # sw t4, 4(s2)
    0xFD349AE3,  # bne s1, s3, loop
    0x00092F03,  # lw t5, 0(s2)
    0x00492F83,  # lw t6, 4(s2)
    0x01E2A023,  # sw t5, 0(t0)
    0x01F2A223,  # sw t6, 4(t0)
    0x00100E13,  # li t3, 1
    0x0FC28FA3,  # sb t3, 0xff(t0)
    0x0000006F,  # j .
    0x00052583,  # helper: lw a1, 0(a0)
    0x00452603,  # lw a2, 4(a0)
    0x00159593,  # slli a1, a1, 1
    0x05564613,  # xori a2, a2, 0x55
    0x00B52023,  # sw a1, 0(a0)
    0x00C52223,  # sw a2, 4(a0)
    0x00008067,  # ret
]

TABLE_WORDS = [
    0x11223344,
    0x55667788,
    0xAABBCCDD,
    0x12345678,
]


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


def _expected_state(seed: int) -> tuple[int, int]:
    rng = random.Random(seed)
    a = rng.getrandbits(32)
    b = rng.getrandbits(32)

    for idx in range(0, len(TABLE_WORDS), 2):
        a = ((a << 1) & 0xFFFF_FFFF) ^ TABLE_WORDS[idx]
        b = (b ^ 0x55) ^ TABLE_WORDS[idx + 1]

    return a & 0xFFFF_FFFF, b & 0xFFFF_FFFF


async def _load_trial_state(dut, seed: int) -> tuple[int, int]:
    rng = random.Random(seed)
    init_a = rng.getrandbits(32)
    init_b = rng.getrandbits(32)

    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for idx, word in enumerate(TABLE_WORDS):
        dut.unified_mem_inst.instr_ram[_phys_word_index(TABLE_ADDR) + idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x400, 4):
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = 0

    dut.unified_mem_inst.instr_ram[_phys_word_index(STATE_ADDR + 0)].value = init_a
    dut.unified_mem_inst.instr_ram[_phys_word_index(STATE_ADDR + 4)].value = init_b

    return init_a, init_b


@cocotb.test()
async def test_repeated_state_roundtrip_across_calls(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    for seed in range(NUM_TRIALS):
        expected_a, expected_b = _expected_state(seed)

        dut.rst.value = 1
        await ClockCycles(dut.clk, 3)
        await _load_trial_state(dut, seed)
        dut.rst.value = 0

        done = False
        for _ in range(320):
            await RisingEdge(dut.clk)
            done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
            if ((done_word >> 24) & 0xFF) == 1:
                done = True
                break

        assert done, f"Round-recurrence test never completed on seed {seed}"

        actual = {
            DATA_MEM_BASE + 0x00: int(dut.unified_mem_inst.instr_ram[_phys_word_index(DATA_MEM_BASE + 0x00)].value) & 0xFFFF_FFFF,
            DATA_MEM_BASE + 0x04: int(dut.unified_mem_inst.instr_ram[_phys_word_index(DATA_MEM_BASE + 0x04)].value) & 0xFFFF_FFFF,
            STATE_ADDR + 0x00: int(dut.unified_mem_inst.instr_ram[_phys_word_index(STATE_ADDR + 0x00)].value) & 0xFFFF_FFFF,
            STATE_ADDR + 0x04: int(dut.unified_mem_inst.instr_ram[_phys_word_index(STATE_ADDR + 0x04)].value) & 0xFFFF_FFFF,
            DONE_WORD_ADDR: int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF,
        }

        expected = {
            DATA_MEM_BASE + 0x00: expected_a,
            DATA_MEM_BASE + 0x04: expected_b,
            STATE_ADDR + 0x00: expected_a,
            STATE_ADDR + 0x04: expected_b,
            DONE_WORD_ADDR: 0x01000000,
        }

        for addr, value in expected.items():
            assert actual[addr] == value, (
                f"Mismatch on seed {seed} at 0x{addr:08x}: "
                f"expected=0x{value:08x} actual=0x{actual[addr]:08x}"
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_round_recurrence"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_round_recurrence",
        testcase="test_repeated_state_roundtrip_across_calls",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
