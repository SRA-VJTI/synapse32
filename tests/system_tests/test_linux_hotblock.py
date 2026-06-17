"""Execute a straight-line Linux hot-path block on the CPU and compare the
architectural result against a tiny software interpreter.

The instruction words were extracted from the repeatedly executing PC window
observed during Linux boot (`0xc0254a40..0xc0254b50`). The block contains no
branches or PC-relative operations, so it can be relocated and run as a pure
ALU/load/store stress test.
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

A0_BASE = 0x1000_0800
S0_BASE = 0x1000_1800
SP_BASE = 0x1000_2800

NOP = 0x00000013
NUM_TRIALS = 25

# Linux boot hot block at 0xc0254a40..0xc0254b50 inclusive.
HOT_BLOCK_SAMPLE = [
    0x01452283, 0x00C686B3, 0x06452603, 0x01DE4E33, 0x01DCCCB3, 0x01D64633,
    0x01D2CEB3, 0x0153DF93, 0xF1D42823, 0x00B61E93, 0x009904B3, 0x01FE8EB3,
    0x00B39393, 0x01565613, 0xF7442A23, 0xF0942E23, 0xF5D42023, 0x00C38633,
    0x07452A03, 0x09C52A83, 0xF2C42E23, 0x02452603, 0x04C52E83, 0x0C452483,
    0xF4042283, 0x01D64FB3, 0x014FCFB3, 0x05452603, 0x015FCFB3, 0x009FCFB3,
    0x01F6C6B3, 0x00D64EB3, 0x0A452603, 0x00D64633, 0xFAC42423, 0x07C52603,
    0x00D64633, 0xF8C42023, 0x02C52603, 0x00D64633, 0xF8C42423, 0x00452603,
    0x00D646B3, 0xF1C42603, 0xFAD42C23, 0x00171693, 0xFFF64613, 0x00567633,
    0xFBC42283, 0x01F75713, 0x00564633, 0x00C52023, 0x01FFD613, 0x001F9F93,
    0x00D60633, 0x01F70733, 0x01F5D693, 0x00179F93, 0x00159593, 0x01F7D793,
    0x00B787B3, 0x09052583, 0x01E64633, 0x00674733, 0x00C5C3B3, 0x09452583,
    0x01F686B3, 0x0116C6B3, 0x00E5C2B3,
]


def _load_hot_block() -> list[int]:
    image_path = os.environ.get("LINUX_HOTBLOCK_IMAGE")
    start_str = os.environ.get("LINUX_HOTBLOCK_START")
    end_str = os.environ.get("LINUX_HOTBLOCK_END")

    if image_path and start_str and end_str:
        image_file = Path(image_path)
        if not image_file.is_absolute():
            image_file = (Path(__file__).resolve().parents[2] / image_file).resolve()
        base = 0xC0000000
        start = int(start_str, 16) - base
        end = int(end_str, 16) - base
        image = image_file.read_bytes()
        return [
            int.from_bytes(image[offset:offset + 4], "little")
            for offset in range(start, end, 4)
        ]

    return HOT_BLOCK_SAMPLE


HOT_BLOCK = _load_hot_block()
MAX_CYCLES_PER_TRIAL = len(HOT_BLOCK) + 160


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


def _execute_hot_block(initial_regs: list[int], initial_mem: dict[int, int]):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    touched = set()

    for instr in HOT_BLOCK:
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F

        if opcode == 0x03:
            imm = _sign_extend(instr >> 20, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            assert funct3 == 0x2, f"Unexpected load in hot block: {instr:08x}"
            regs[rd] = _read_word(mem, addr)
            touched.add(addr & 0xFFFF_FFFC)
        elif opcode == 0x23:
            imm = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
            imm = _sign_extend(imm, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            assert funct3 == 0x2, f"Unexpected store in hot block: {instr:08x}"
            _write_word(mem, addr, regs[rs2])
            touched.add(addr & 0xFFFF_FFFC)
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
            elif funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ (imm & 0xFFFF_FFFF)) & 0xFFFF_FFFF
            else:
                raise AssertionError(f"Unexpected I-type op in hot block: {instr:08x}")
        elif opcode == 0x33:
            if funct7 != 0x00:
                raise AssertionError(f"Unexpected R-type funct7 in hot block: {instr:08x}")
            if funct3 == 0x0:
                regs[rd] = (regs[rs1] + regs[rs2]) & 0xFFFF_FFFF
            elif funct3 == 0x4:
                regs[rd] = (regs[rs1] ^ regs[rs2]) & 0xFFFF_FFFF
            elif funct3 == 0x7:
                regs[rd] = regs[rs1] & regs[rs2]
            else:
                raise AssertionError(f"Unexpected R-type op in hot block: {instr:08x}")
        else:
            raise AssertionError(f"Unexpected opcode in hot block: {instr:08x}")

        regs[0] = 0

    return regs, mem, touched


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


def _touched_seed_values(seed: int):
    rng = random.Random(seed)
    regs = [rng.getrandbits(32) for _ in range(32)]
    regs[0] = 0
    regs[2] = SP_BASE      # sp
    regs[8] = S0_BASE      # s0
    regs[10] = A0_BASE     # a0

    mem = {}
    # Seed all words the block touches under a0 and s0.
    for addr in range(A0_BASE, A0_BASE + 0x100, 4):
        mem[addr] = rng.getrandbits(32)
    for addr in range(S0_BASE - 0x100, S0_BASE, 4):
        mem[addr] = rng.getrandbits(32)
    for addr in range(SP_BASE + 0xF0, SP_BASE + 0x100, 4):
        mem[addr] = rng.getrandbits(32)

    return regs, mem


async def _load_trial_state(dut, regs: list[int], mem: dict[int, int]) -> None:
    for idx in range(0, len(HOT_BLOCK) + 16):
        word = HOT_BLOCK[idx] if idx < len(HOT_BLOCK) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for addr, value in mem.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value

    for reg_idx in range(32):
        dut.cpu_inst.rf_inst0.register_file[reg_idx].value = regs[reg_idx]


@cocotb.test()
async def test_linux_hotblock_matches_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    for seed in range(NUM_TRIALS):
        init_regs, init_mem = _touched_seed_values(seed)
        expected_regs, expected_mem, touched_words = _execute_hot_block(init_regs, init_mem)

        dut.rst.value = 1
        await ClockCycles(dut.clk, 3)
        await _load_trial_state(dut, init_regs, init_mem)
        dut.rst.value = 0

        for _ in range(MAX_CYCLES_PER_TRIAL):
            await RisingEdge(dut.clk)

        actual_regs = [
            int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
            for idx in range(32)
        ]

        assert actual_regs == expected_regs, (
            f"Register mismatch on seed {seed}: "
            f"expected={[hex(v) for v in expected_regs]}, "
            f"actual={[hex(v) for v in actual_regs]}"
        )

        for addr in sorted(touched_words):
            actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF
            expected = expected_mem.get(addr, 0) & 0xFFFF_FFFF
            assert actual == expected, (
                f"Memory mismatch on seed {seed} at 0x{addr:08x}: "
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_linux_hotblock"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_linux_hotblock",
        testcase="test_linux_hotblock_matches_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
