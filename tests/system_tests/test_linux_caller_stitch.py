"""Execute the real Linux caller plus helper together on the CPU.

This stitches together:
- the caller window around 0xc02555cc..0xc025576c
- the full helper body at 0xc025478c..0xc02554e0
- a synthetic far memset stub at the original AUIPC+JALR target distance

The code is relocated sparsely into physical instruction RAM while preserving
the original relative distances, so the real PC-relative calls and jumps still
land correctly.
"""

import os
import random
import shutil
from collections import deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

ORIG_BASE = 0xC025_0000
IMAGE_BASE = 0xC000_0000

RESET_PC = INSTR_MEM_BASE
CALLER_START = 0xC025_55CC
# End addresses are exclusive; include the final RET at 0xc025576c.
CALLER_END = 0xC025_5770
HELPER_START = 0xC025_478C
HELPER_END = 0xC025_54E4
TABLE_START = 0xC101_2648
TABLE_END = 0xC101_2708
MEMSET_TARGET = 0xC04C_EF84

RELOC_CALLER_START = RESET_PC + (CALLER_START - ORIG_BASE)
RELOC_HELPER_START = RESET_PC + (HELPER_START - ORIG_BASE)
RELOC_TABLE_START = RESET_PC + (TABLE_START - ORIG_BASE)
RELOC_MEMSET_TARGET = RESET_PC + (MEMSET_TARGET - ORIG_BASE)
RETURN_SENTINEL = RESET_PC + 0x3000

DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC

NOP = 0x00000013
NUM_TRIALS = 20

TRAMPOLINE_WORDS = [
    0x5CC0506F,  # jal x0, RELOC_CALLER_START
]

# lui t0, 0x10000 ; addi t3, x0, 1 ; sb t3, 0xff(t0) ; jal x0, 0
RETURN_SENTINEL_WORDS = [
    0x100002B7,
    0x00100E13,
    0x0FC28FA3,
    0x0000006F,
]

# Tiny memset(a0=dst, a1=value, a2=len) stub.
MEMSET_STUB_WORDS = [
    0x00060863,  # beq a2, x0, +16
    0x00B50023,  # sb a1, 0(a0)
    0x00150513,  # addi a0, a0, 1
    0xFFF60613,  # addi a2, a2, -1
    0xFE0618E3,  # bne a2, x0, -16
    0x00008067,  # ret
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
    word_addr = addr & 0xFFFF_FFFC
    if word_addr in memory:
        return memory[word_addr] & 0xFFFF_FFFF
    # The Linux caller reads round constants as data from instruction-memory
    # space. Mirror that in the software model by falling back to the relocated
    # program image when no data-memory override exists.
    return PROGRAM_WORDS.get(word_addr, 0) & 0xFFFF_FFFF


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


def _jal_imm(instr: int) -> int:
    imm = (
        ((instr >> 31) & 0x1) << 20
        | ((instr >> 12) & 0xFF) << 12
        | ((instr >> 20) & 0x1) << 11
        | ((instr >> 21) & 0x3FF) << 1
    )
    return _sign_extend(imm, 21)


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


def _load_image_words(start: int, end: int) -> dict[int, int]:
    image = (Path(__file__).resolve().parents[2] / "sim/.out/linux/Image").read_bytes()
    words = {}
    for addr in range(start, end, 4):
        off = addr - IMAGE_BASE
        words[RESET_PC + (addr - ORIG_BASE)] = int.from_bytes(image[off:off + 4], "little")
    return words


def _program_words() -> dict[int, int]:
    words = {}
    words[RESET_PC] = TRAMPOLINE_WORDS[0]
    for idx, word in enumerate(RETURN_SENTINEL_WORDS):
        words[RETURN_SENTINEL + idx * 4] = word
    for idx, word in enumerate(MEMSET_STUB_WORDS):
        words[RELOC_MEMSET_TARGET + idx * 4] = word
    words.update(_load_image_words(HELPER_START, HELPER_END))
    words.update(_load_image_words(CALLER_START, CALLER_END))
    words.update(_load_image_words(TABLE_START, TABLE_END))
    return words


PROGRAM_WORDS = _program_words()


def _seed_state(seed: int):
    rng = random.Random(seed)
    regs = [0] * 32
    mem: dict[int, int] = {}
    watched = set()

    ctx = DATA_MEM_BASE + 0x2000 + seed * 0x200
    out_buf = DATA_MEM_BASE + 0x5000 + seed * 0x200
    sp_after_prologue = DATA_MEM_BASE + 0x9000 + seed * 0x100
    fp = sp_after_prologue + 32

    regs[2] = sp_after_prologue
    regs[5] = DATA_MEM_BASE          # t0 for return sentinel
    regs[8] = fp                     # s0/fp
    regs[9] = ctx + 220              # s1 / loop byte base
    regs[18] = ctx                   # s2 / ctx base
    regs[19] = ctx + 8               # s3 / helper state base
    regs[20] = out_buf               # s4 / byte output base
    regs[21] = rng.choice([0x08, 0x10, 0x18, 0x20])  # s5 / tail byte count
    regs[22] = 0                     # s6 gets initialized later in caller

    saved = {
        sp_after_prologue + 0: rng.getrandbits(32),
        sp_after_prologue + 4: rng.getrandbits(32),
        sp_after_prologue + 8: rng.getrandbits(32),
        sp_after_prologue + 12: rng.getrandbits(32),
        sp_after_prologue + 16: rng.getrandbits(32),
        sp_after_prologue + 20: rng.getrandbits(32),
        sp_after_prologue + 24: rng.getrandbits(32),
        sp_after_prologue + 28: RETURN_SENTINEL,
    }
    mem.update(saved)
    watched.update(saved.keys())

    # Context region touched by the caller and helper.
    for addr in range(ctx, ctx + 0x200, 4):
        mem[addr] = rng.getrandbits(32)
        watched.add(addr)

    # Keep the first caller loop bounded and active.
    mem[ctx + 212] = rng.randint(1, 4)
    watched.add(ctx + 212)

    # Output buffer region written by the tail-copy path and final memset.
    for addr in range(out_buf, out_buf + 0x40, 4):
        mem[addr] = rng.getrandbits(32)
        watched.add(addr)

    # The final memset clears 360 bytes at ctx+8.
    for addr in range(ctx + 8, ctx + 8 + 0x180, 4):
        watched.add(addr)

    # Byte-output tail writes at out_buf.
    for addr in range(out_buf, out_buf + 0x20, 4):
        watched.add(addr)

    regs[0] = 0
    return regs, mem, watched


def _execute_program(initial_regs: list[int], initial_mem: dict[int, int]):
    regs = initial_regs[:]
    mem = dict(initial_mem)
    pc = RESET_PC
    steps = 0
    # The caller runs the 24-round permutation helper once per round-table
    # entry, so the full stitched path legitimately executes well past 20k
    # instructions before returning.
    max_steps = 30000

    while True:
        instr = PROGRAM_WORDS.get(pc, NOP)
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F
        next_pc = (pc + 4) & 0xFFFF_FFFF

        if pc == RETURN_SENTINEL + 12:
            break

        if opcode == 0x03:
            imm = _sign_extend(instr >> 20, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x2:
                regs[rd] = _read_word(mem, addr)
            elif funct3 == 0x4:
                regs[rd] = _read_byte(mem, addr)
            else:
                raise AssertionError(f"Unexpected load: {instr:08x}")
        elif opcode == 0x23:
            imm = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
            imm = _sign_extend(imm, 12)
            addr = (regs[rs1] + imm) & 0xFFFF_FFFF
            if funct3 == 0x0:
                _write_byte(mem, addr, regs[rs2])
            elif funct3 == 0x2:
                _write_word(mem, addr, regs[rs2])
            else:
                raise AssertionError(f"Unexpected store: {instr:08x}")
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
            elif funct3 == 0x6:
                regs[rd] = (regs[rs1] | (imm & 0xFFFF_FFFF)) & 0xFFFF_FFFF
            elif funct3 == 0x7:
                regs[rd] = regs[rs1] & (imm & 0xFFFF_FFFF)
            else:
                raise AssertionError(f"Unexpected I-type op: {instr:08x}")
        elif opcode == 0x17:
            imm = instr & 0xFFFFF000
            regs[rd] = (pc + imm) & 0xFFFF_FFFF
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
            imm = _branch_imm(instr)
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
            next_pc = (pc + _jal_imm(instr)) & 0xFFFF_FFFF
        elif opcode == 0x67:
            imm = _sign_extend(instr >> 20, 12)
            target = (regs[rs1] + imm) & 0xFFFF_FFFE
            regs[rd] = next_pc
            next_pc = target
        else:
            raise AssertionError(f"Unexpected opcode: {instr:08x} at pc=0x{pc:08x}")

        regs[0] = 0
        pc = next_pc
        steps += 1
        if steps > max_steps:
            raise AssertionError("Program did not terminate in model")

    return regs, mem, steps


async def _load_trial_state(dut, regs: list[int], mem: dict[int, int]) -> None:
    for addr, word in PROGRAM_WORDS.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = word

    # Each stitched seed reuses the same simulated RAM, so clear the completion
    # sentinel before loading trial-specific state.
    dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value = 0

    for addr, value in mem.items():
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value

    for reg_idx, value in enumerate(regs):
        dut.cpu_inst.rf_inst0.register_file[reg_idx].value = value


@cocotb.test()
async def test_linux_caller_stitch_matches_model(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    for seed in range(NUM_TRIALS):
        init_regs, init_mem, watched_words = _seed_state(seed)
        expected_regs, expected_mem, step_count = _execute_program(init_regs, init_mem)

        dut.rst.value = 1
        await ClockCycles(dut.clk, 3)
        await _load_trial_state(dut, init_regs, init_mem)
        dut.rst.value = 0

        ctx = init_regs[18]
        done = False
        max_cycles = (step_count * 3) + 256
        pc_history = deque(maxlen=16)
        tail_history = deque(maxlen=64)
        memset_pc_hits = 0
        memset_ctx_stores = 0
        tail_jalr_hits = 0
        for _ in range(max_cycles):
            await RisingEdge(dut.clk)
            pc_val = int(dut.pc_debug.value) & 0xFFFF_FFFF
            instr_val = int(dut.instr_debug.value) & 0xFFFF_FFFF
            wr_en = int(dut.cpu_inst.module_mem_wr_en.value) & 0x1
            wr_addr = int(dut.cpu_inst.module_write_addr.value) & 0xFFFF_FFFF
            wr_data = int(dut.cpu_inst.module_wr_data_out.value) & 0xFFFF_FFFF
            pc_history.append(
                (
                    pc_val,
                    instr_val,
                    int(dut.cpu_inst.pipeline_stall.value) & 0x1,
                    int(dut.cpu_inst.hazard_stall.value) & 0x1,
                )
            )
            if pc_val == RELOC_MEMSET_TARGET:
                memset_pc_hits += 1
            if pc_val == 0x80005740:
                tail_jalr_hits += 1
            if wr_en and (ctx + 8) <= wr_addr < (ctx + 8 + 0x180):
                memset_ctx_stores += 1
            if (
                (RELOC_CALLER_START <= pc_val < CALLER_END - ORIG_BASE + RESET_PC)
                or (RELOC_MEMSET_TARGET <= pc_val < (RELOC_MEMSET_TARGET + 0x20))
                or wr_en
            ):
                tail_history.append(
                    (
                        pc_val,
                        instr_val,
                        wr_en,
                        wr_addr,
                        wr_data,
                        int(dut.cpu_inst.pipeline_stall.value) & 0x1,
                        int(dut.cpu_inst.hazard_stall.value) & 0x1,
                    )
                )
            done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
            if ((done_word >> 24) & 0xFF) == 1:
                done = True
                break

        if not done:
            actual_regs = [
                int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
                for idx in range(32)
            ]
            history = " ".join(
                f"pc=0x{pc:08x}/insn=0x{insn:08x}/stall={stall}/haz={haz}"
                for pc, insn, stall, haz in pc_history
            )
            raise AssertionError(
                f"Stitched caller path did not complete on seed {seed}: "
                f"pc=0x{int(dut.pc_debug.value) & 0xFFFF_FFFF:08x} "
                f"instr=0x{int(dut.instr_debug.value) & 0xFFFF_FFFF:08x} "
                f"id_ex_pc=0x{int(dut.cpu_inst.id_ex_inst0_pc_out.value) & 0xFFFF_FFFF:08x} "
                f"ex_mem_pc=0x{int(dut.cpu_inst.ex_mem_inst0_pc_out.value) & 0xFFFF_FFFF:08x} "
                f"mem_addr=0x{int(dut.cpu_inst.ex_mem_inst0_mem_addr_out.value) & 0xFFFF_FFFF:08x} "
                f"stall={int(dut.cpu_inst.pipeline_stall.value) & 0x1} "
                f"hazard={int(dut.cpu_inst.hazard_stall.value) & 0x1} "
                f"ra=0x{actual_regs[1]:08x} sp=0x{actual_regs[2]:08x} "
                f"s0=0x{actual_regs[8]:08x} s1=0x{actual_regs[9]:08x} "
                f"s2=0x{actual_regs[18]:08x} s3=0x{actual_regs[19]:08x} "
                f"s4=0x{actual_regs[20]:08x} s5=0x{actual_regs[21]:08x} "
                f"s6=0x{actual_regs[22]:08x} a0=0x{actual_regs[10]:08x} "
                f"a1=0x{actual_regs[11]:08x} a2=0x{actual_regs[12]:08x} "
                f"a3=0x{actual_regs[13]:08x} a4=0x{actual_regs[14]:08x} "
                f"a5=0x{actual_regs[15]:08x}; recent={history}"
            )

        memory_mismatches = []
        for addr in sorted(watched_words):
            actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF
            expected = expected_mem.get(addr, 0) & 0xFFFF_FFFF
            if actual != expected:
                memory_mismatches.append((addr, expected, actual))

        actual_regs = [
            int(dut.cpu_inst.rf_inst0.register_file[idx].value) & 0xFFFF_FFFF
            for idx in range(32)
        ]

        if memory_mismatches:
            preview = ", ".join(
                f"0x{addr:08x}:exp=0x{expected:08x}/act=0x{actual:08x}"
                for addr, expected, actual in memory_mismatches[:8]
            )
            tail_preview = " ".join(
                f"pc=0x{pc:08x}/insn=0x{insn:08x}/wr={wr}/addr=0x{addr:08x}/data=0x{data:08x}/stall={stall}/haz={haz}"
                for pc, insn, wr, addr, data, stall, haz in tail_history
            )
            recent_preview = " ".join(
                f"pc=0x{pc:08x}/insn=0x{insn:08x}/stall={stall}/haz={haz}"
                for pc, insn, stall, haz in pc_history
            )
            raise AssertionError(
                f"Memory mismatch on seed {seed}: {preview}; "
                f"jalr_hits={tail_jalr_hits} memset_hits={memset_pc_hits} ctx_store_count={memset_ctx_stores}; "
                f"tail_recent={tail_preview}; recent={recent_preview}"
            )

        assert actual_regs == expected_regs, (
            f"Register mismatch on seed {seed}: "
            f"expected={[hex(v) for v in expected_regs]}, "
            f"actual={[hex(v) for v in actual_regs]}"
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_linux_caller_stitch"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_linux_caller_stitch",
        testcase="test_linux_caller_stitch_matches_model",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
