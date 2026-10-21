"""Store buffer.

Translated writes wait in front of the data port, so stores cost no more than ALU instructions. Each
check runs while the write is still buffered: loads, LR and AMOs of that word, a device read after a
device write, FENCE.I, the page walk after SFENCE.VMA, and an interrupt handler (swept over every
cycle). A generated mix of stores and loads must match a memory model at buffer depths 1, 2 and 4.
Every program runs at latency 0, 1, 2 and 4, plus a build with fast fetch and slow data.
"""

import os
import random
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from cocotb_test.simulator import run
from memory_view import read_word

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

SCRATCH = 0x1000_0100
FILLER = 0x1000_0180
RESULT = 0x1000_0200
RESULT_WORDS = 16
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
M_SCRATCH = 0x1000_0800
UART_RBR_DLL = 0x2000_0000
UART_LCR = 0x2000_000C
UART_DEFAULT_DLL = 10
UNRELATED_VALUE = 0x77
STORE_RUN = 4

LATENCIES = [0, 1, 2, 4]
SWEEP_LATENCY = 2
DEFAULT_DEPTH = 4
FAST_FETCH_DEPTHS = [1, 2, 4]
FAST_FETCH = os.environ.get("STORE_BUFFER_FAST_FETCH") == "1"

# Three writes ahead of the one under test, so it waits behind them.
FILL = f"""
        sw      s1, 0(s2)
        sw      s1, 4(s2)
        sw      s1, 8(s2)
"""


def _store_run(op: str) -> str:
    return "".join(f"""
        {op.format(offset=4 * i)}
        addi    t0, t0, 1
        addi    t0, t0, 1
        addi    t0, t0, 1""" for i in range(STORE_RUN))


ORDERING_PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a0, {SCRATCH:#x}
        li      a7, {RESULT:#x}
        li      s1, 0x11111111
        li      s2, {FILLER:#x}

        # Stores cost no more cycles than ALU instructions while the buffer has room.
        csrr    t5, mcycle{_store_run("sw      zero, {offset}(a0)")}
        csrr    t6, mcycle
        sub     t6, t6, t5
        sw      t6, 0(a7)
        csrr    t5, mcycle{_store_run("addi    t1, t1, {offset}")}
        csrr    t6, mcycle
        sub     t6, t6, t5
        sw      t6, 4(a7)

        # A load of a buffered word, whole and in part.
{FILL}
        li      t1, 0xA1B2C3D4
        sw      t1, 0(a0)
        lw      t2, 0(a0)
        sw      t2, 8(a7)
{FILL}
        li      t1, 0x5A
        sb      t1, 1(a0)
        lw      t2, 0(a0)
        sw      t2, 12(a7)
{FILL}
        li      t1, 0xBEEF
        sh      t1, 2(a0)
        lhu     t2, 2(a0)
        sw      t2, 16(a7)
{FILL}
        li      t1, 0x12345678
        sw      t1, 4(a0)
        lbu     t2, 7(a0)
        sw      t2, 20(a7)

        # A load of another word goes first; the buffered word still reads back.
{FILL}
        li      t1, 0xCAFE
        sw      t1, 8(a0)
        lw      t2, 0x40(a0)
        lw      t3, 8(a0)
        sw      t2, 24(a7)
        sw      t3, 28(a7)

        # AMO and LR/SC on a buffered word.
        addi    a1, a0, 12
{FILL}
        li      t1, 5
        sw      t1, 0(a1)
        li      t2, 3
        amoadd.w t3, t2, (a1)
        lw      t4, 0(a1)
        sw      t3, 32(a7)
        sw      t4, 36(a7)
        addi    a2, a0, 16
{FILL}
        li      t1, 7
        sw      t1, 0(a2)
        lr.w    t3, (a2)
        li      t4, 9
        sc.w    t5, t4, (a2)
        lw      t6, 0(a2)
        sw      t3, 40(a7)
        sw      t5, 44(a7)
        sw      t6, 48(a7)

        # A device read after a device write: with LCR.DLAB set, register 0 is the divisor latch.
        li      a3, {UART_LCR:#x}
        li      a4, {UART_RBR_DLL:#x}
{FILL}
        li      t1, 0x80
        sw      t1, 0(a3)
        lw      t2, 0(a4)
        sw      zero, 0(a3)
        sw      t2, 52(a7)

        # The instruction written before FENCE.I runs after it.
        la      a5, patch
        li      t1, 0x02a00793          # addi a5, zero, 42
{FILL}
        sw      t1, 0(a5)
        fence.i
        jal     ra, patch
        sw      a5, 56(a7)

        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

patch:
        addi    a5, zero, 1
        ret

        .align  2
m_trap:
        csrr    t0, mcause
        li      t1, {TRAP_CAUSE:#x}
        sw      t0, 0(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
"""

ORDERING_EXPECTED = {
    2: 0xA1B2C3D4,
    3: 0xA1B25AD4,
    4: 0xBEEF,
    5: 0x12,
    6: UNRELATED_VALUE,
    7: 0xCAFE,
    8: 5,
    9: 8,
    10: 7,
    11: 0,
    12: 9,
    13: UART_DEFAULT_DLL,
    14: 42,
}

# Paging: data is identity-mapped by a megapage; the code runs on page A and falls through into page B,
# both mapped through a level-0 table. The last two words of page A repoint page B and fence, so the
# first walk after the fence is page B's, and it must read the new entry.
ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
PAGE_A_VA = 0x4000_0000
PAGE_B_VA = 0x4000_1000
PAGE_A_PA = 0x8000_2000
PAGE_B_OLD_PA = 0x8000_3000
PAGE_B_NEW_PA = 0x8000_4000
L0_ENTRY_A = L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF)
L0_ENTRY_B = L0_TABLE + 4 * ((PAGE_B_VA >> 12) & 0x3FF)
OLD_MARKER = 0x0BAD_0BAD
NEW_MARKER = 0x600D_600D
V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


def _page_b(marker: int) -> str:
    return f"""
        li      t2, {marker:#x}
        sw      t2, 0(a7)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
"""


PAGING_PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      t0, {SATP:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0             # MPP = S
        li      t0, {PAGE_A_VA:#x}
        csrw    mepc, t0
        mret

        .align  2
m_trap:
        csrr    t0, mcause
        li      t1, {TRAP_CAUSE:#x}
        sw      t0, 0(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b

        .org    {PAGE_A_PA - INSTR_MEM_BASE:#x}
        li      a7, {RESULT:#x}
        li      s1, 0x11111111
        li      s2, {FILLER:#x}
        li      a1, {L0_ENTRY_B:#x}
        li      t1, {_pte(PAGE_B_NEW_PA, V | R | X | A):#x}
        j       page_a_tail
        .org    {PAGE_A_PA - INSTR_MEM_BASE + 0x1000 - 20:#x}
page_a_tail:
{FILL}
        sw      t1, 0(a1)
        sfence.vma

        .org    {PAGE_B_OLD_PA - INSTR_MEM_BASE:#x}
{_page_b(OLD_MARKER)}
        .org    {PAGE_B_NEW_PA - INSTR_MEM_BASE:#x}
{_page_b(NEW_MARKER)}
"""

# The handler reads the word the loop stores last; precise interrupts say it holds s0, or s0 - 1 when
# the interrupt was taken at that store.
COUNTER = SCRATCH
BAD_READS = RESULT + 8
LOOPS = 6

IRQ_PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        la      t0, m_trap
        csrw    mtvec, t0
        li      t0, 0x8
        csrw    mie, t0
        csrsi   mstatus, 0x8
        li      a0, {COUNTER:#x}
        li      s1, 0x11111111
        li      s2, {FILLER:#x}
        li      s0, 0
        li      s3, {LOOPS}
loop:
{FILL}
        addi    s0, s0, 1
counter_store:
        sw      s0, 0(a0)
        addi    s3, s3, -1
        bnez    s3, loop
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

        .align  2
m_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        lw      t0, 0(a0)
        sub     t0, s0, t0
        csrr    t1, mepc
        la      t2, counter_store
        bne     t1, t2, 1f
        addi    t0, t0, -1
1:
        beqz    t0, 2f
        li      t1, {BAD_READS:#x}
        lw      t2, 0(t1)
        addi    t2, t2, 1
        sw      t2, 0(t1)
2:
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret
"""

# Stress: stores use preloaded registers, so they issue back to back; each load's value is logged.
STRESS = 0x1000_0400
STRESS_BYTES = 64
STRESS_LOG = 0x1000_0500
STRESS_OPS = 160
STRESS_LOADS = 64
STRESS_SEED = 0x5B
STRESS_REGS = ["s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11"]
STORE_OPS = {1: "sb", 2: "sh", 4: "sw"}
LOAD_OPS = [("lb", 1, True), ("lbu", 1, False), ("lh", 2, True), ("lhu", 2, False), ("lw", 4, False)]


def _stress():
    """The stress program, the memory it starts from, and what a correct core loads and leaves behind."""
    rng = random.Random(STRESS_SEED)
    memory = bytearray(rng.randrange(256) for _ in range(STRESS_BYTES))
    initial = bytes(memory)
    values = [rng.randrange(1 << 32) for _ in STRESS_REGS]
    body, log = [], []
    for _ in range(STRESS_OPS):
        if rng.random() < 0.6 or len(log) == STRESS_LOADS:
            size = rng.choice([1, 2, 4])
            offset = rng.randrange(0, STRESS_BYTES, size)
            reg = rng.randrange(len(STRESS_REGS))
            body.append(f"        {STORE_OPS[size]}      {STRESS_REGS[reg]}, {offset}(a0)")
            memory[offset:offset + size] = values[reg].to_bytes(4, "little")[:size]
        else:
            op, size, signed = rng.choice(LOAD_OPS)
            offset = rng.randrange(0, STRESS_BYTES, size)
            value = int.from_bytes(memory[offset:offset + size], "little", signed=signed) & 0xFFFF_FFFF
            body.append(f"        {op:<8}t2, {offset}(a0)")
            body.append(f"        sw      t2, {4 * len(log)}(a7)")
            log.append(value)
    preload = "\n".join(f"        li      {r}, {v:#x}" for r, v in zip(STRESS_REGS, values))
    program = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a0, {STRESS:#x}
        li      a7, {STRESS_LOG:#x}
{preload}
""" + "\n".join(body) + f"""
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

        .align  2
m_trap:
        csrr    t0, mcause
        li      t1, {TRAP_CAUSE:#x}
        sw      t0, 0(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
"""
    words = lambda b: [int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)]
    return program, words(initial), log, words(memory)


LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) }}
}}
"""


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("STORE_BUFFER_BUILD", Path.cwd() / "build" / "store_buffer"))


def _compile(build_dir: Path, name: str, program: str) -> None:
    src = build_dir / f"{name}.S"
    lds = build_dir / "store_buffer.ld"
    elf = build_dir / f"{name}.elf"
    src.write_text(program)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr_zifencei", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / f"{name}.bin")],
                   check=True)


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    _compile(build_dir, "ordering", ORDERING_PROGRAM)
    _compile(build_dir, "paging", PAGING_PROGRAM)
    _compile(build_dir, "irq", IRQ_PROGRAM)
    _compile(build_dir, "stress", _stress()[0])
    (build_dir / "nop.hex").write_text("@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128)


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < INSTR_MEM_BASE + INSTR_MEM_SIZE:
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address 0x{addr:08x}")


def _poke(dut, addr: int, value: int) -> None:
    dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value & 0xFFFF_FFFF


def _peek(dut, addr: int) -> int:
    return read_word(dut, _phys_word_index(addr)) & 0xFFFF_FFFF


def _load_image(dut, name: str) -> None:
    data = (_build_dir() / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


async def _run(dut, image: str, setup=(), inject_cycle=None, limit=20000, coverage=None):
    """Run a program until it stores the done marker; return the cycle it did, or None."""
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _load_image(dut, image)
    for offset in range(0, 0x100, 4):
        _poke(dut, SCRATCH + offset, 0)
        _poke(dut, FILLER + offset, 0)
        _poke(dut, RESULT + offset, 0)
    for addr in (DONE_ADDR, TRAP_CAUSE):
        _poke(dut, addr, 0)
    for addr, value in setup:
        _poke(dut, addr, value)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    pin_high = False
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        if inject_cycle is not None and cycle == inject_cycle:
            dut.software_interrupt.value = 1
            pin_high = True
        await ReadOnly()
        if coverage is not None:
            writing = int(dut.cpu_mem_write_en.value)
            # A store that waits because the buffer is full; a load that waits on a buffered word.
            if writing and int(dut.store_buffer_inst.full.value):
                coverage["full"] += 1
            if not writing and int(dut.cpu_mem_read_en.value) and int(dut.store_buf_match.value):
                coverage["match"] += 1
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            return cycle
        # Once the handler is entered, lower the pin so the interrupt is taken once.
        if pin_high and int(dut.cpu_inst.csr_file_inst.mcause.value) == 0x8000_0003:
            await RisingEdge(dut.clk)
            dut.software_interrupt.value = 0
            pin_high = False
    return None


def _latency() -> int:
    return int(os.environ["STORE_BUFFER_LATENCY"])


def _depth() -> int:
    return int(os.environ["STORE_BUFFER_DEPTH"])


@cocotb.test()
async def test_buffered_writes_keep_program_order(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "ordering.bin", setup=[(SCRATCH + 0x40, UNRELATED_VALUE)])
    name = f"latency {_latency()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert _peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{_peek(dut, TRAP_CAUSE):08x}"
    got = {i: _peek(dut, RESULT + 4 * i) for i in ORDERING_EXPECTED}
    wrong = {i: (f"0x{got[i]:x}", f"0x{v:x}") for i, v in ORDERING_EXPECTED.items() if got[i] != v}
    assert not wrong, f"{name}: result words (got, expected): {wrong}"


@cocotb.test()
async def test_stores_do_not_hold_the_pipeline(dut):
    """With fetch answering at once and data after two cycles, a store must not wait for memory."""
    if not FAST_FETCH:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "ordering.bin", setup=[(SCRATCH + 0x40, UNRELATED_VALUE)])
    assert done is not None, "the program did not finish"
    store_cycles = _peek(dut, RESULT)
    alu_cycles = _peek(dut, RESULT + 4)
    assert store_cycles == alu_cycles, (
        f"{STORE_RUN} stores among ALU instructions took {store_cycles} cycles, the same run with ALU "
        f"instructions in their place {alu_cycles}: the stores waited for memory")


@cocotb.test()
async def test_page_walk_sees_buffered_pte(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    setup = [
        (ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), _pte(DATA_MEM_BASE, V | R | W | A | D)),
        (ROOT_TABLE + 4 * (PAGE_A_VA >> 22), _pte(L0_TABLE, V)),
        (L0_ENTRY_A, _pte(PAGE_A_PA, V | R | X | A)),
        (L0_ENTRY_B, _pte(PAGE_B_OLD_PA, V | R | X | A)),
    ]
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE + offset, 0)
    done = await _run(dut, "paging.bin", setup=setup)
    name = f"latency {_latency()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert _peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{_peek(dut, TRAP_CAUSE):08x}"
    marker = _peek(dut, RESULT)
    assert marker == NEW_MARKER, (
        f"{name}: page B ran the code at 0x{PAGE_B_OLD_PA if marker == OLD_MARKER else 0:08x} "
        f"(marker 0x{marker:08x}): the walk after SFENCE.VMA did not see the entry written before it")


@cocotb.test()
async def test_mixed_stores_and_loads_match_a_memory_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _, initial, expected_log, expected_memory = _stress()
    setup = [(STRESS + 4 * i, word) for i, word in enumerate(initial)]
    setup += [(STRESS_LOG + 4 * i, 0) for i in range(STRESS_LOADS)]
    coverage = {"full": 0, "match": 0}
    done = await _run(dut, "stress.bin", setup=setup, coverage=coverage)
    name = f"latency {_latency()}, depth {_depth()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert _peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{_peek(dut, TRAP_CAUSE):08x}"
    log = [_peek(dut, STRESS_LOG + 4 * i) for i in range(len(expected_log))]
    bad_loads = [(i, f"0x{g:x}", f"0x{e:x}") for i, (g, e) in enumerate(zip(log, expected_log)) if g != e]
    assert not bad_loads, f"{name}: loads (index, got, expected): {bad_loads[:6]}"
    memory = [_peek(dut, STRESS + 4 * i) for i in range(len(expected_memory))]
    bad_words = [(i, f"0x{g:x}", f"0x{e:x}") for i, (g, e) in enumerate(zip(memory, expected_memory)) if g != e]
    assert not bad_words, f"{name}: final words (index, got, expected): {bad_words[:6]}"
    dut._log.info(f"{name}: {coverage['full']} cycles a store waited on a full buffer, "
                  f"{coverage['match']} cycles a load waited on a buffered word")
    if FAST_FETCH:
        assert coverage["full"] and coverage["match"], (
            f"{name}: the buffer never filled or no load waited on a buffered word ({coverage}), "
            "so this run did not exercise the buffer")


@cocotb.test()
async def test_handler_reads_buffered_store(dut):
    """An interrupt at any cycle: the handler must read the value of every store before mepc."""
    if _latency() != SWEEP_LATENCY or FAST_FETCH:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    reference = await _run(dut, "irq.bin")
    assert reference is not None, "reference run did not finish"
    failures = []
    taken = 0
    for inject in range(reference + 1):
        done = await _run(dut, "irq.bin", inject_cycle=inject, limit=reference + 400)
        if done is None:
            failures.append(f"interrupt at cycle {inject}: did not finish")
            continue
        if int(dut.cpu_inst.csr_file_inst.mcause.value) == 0x8000_0003:
            taken += 1
        if _peek(dut, BAD_READS):
            failures.append(f"interrupt at cycle {inject}: handler read a stale value")
        if _peek(dut, COUNTER) != LOOPS:
            failures.append(f"interrupt at cycle {inject}: final counter {_peek(dut, COUNTER)}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_store_buffer_{name}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_store_buffer",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_store_buffer",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_store_buffer",
                "STORE_BUFFER_BUILD": str(build_dir.resolve()),
                "STORE_BUFFER_LATENCY": str(latency),
                "STORE_BUFFER_DEPTH": str(depth),
                "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0",
            },
        )


if __name__ == "__main__":
    runCocotbTests()
