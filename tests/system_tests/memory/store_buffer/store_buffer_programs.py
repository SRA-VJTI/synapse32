"""Programs, builds and helpers shared by the store buffer tests; each test file runs them on every build."""

import os
import random
import subprocess
from pathlib import Path

from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

from support import INSTR_MEM_BASE, peek, poke, pte


SCRATCH = 0x1000_0100
FILLER = 0x1000_0180
RESULT = 0x1000_0200

DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
M_SCRATCH = 0x1000_0800
UART_RBR_DLL = 0x2000_0000
UART_LCR = 0x2000_000C

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

L0_ENTRY_B = L0_TABLE + 4 * ((PAGE_B_VA >> 12) & 0x3FF)
OLD_MARKER = 0x0BAD_0BAD
NEW_MARKER = 0x600D_600D
V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80


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
        li      t1, {pte(PAGE_B_NEW_PA, V | R | X | A):#x}
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


def stress_case():
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
    _compile(build_dir, "stress", stress_case()[0])


def _load_image(dut, name: str) -> None:
    data = (_build_dir() / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


async def run_image(dut, image: str, setup=(), inject_cycle=None, limit=20000, coverage=None):
    """Run a program until it stores the done marker; return the cycle it did, or None."""
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _load_image(dut, image)
    for offset in range(0, 0x100, 4):
        poke(dut, SCRATCH + offset, 0)
        poke(dut, FILLER + offset, 0)
        poke(dut, RESULT + offset, 0)
    for addr in (DONE_ADDR, TRAP_CAUSE):
        poke(dut, addr, 0)
    for addr, value in setup:
        poke(dut, addr, value)
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
            writing = int(dut.cpu_inst.module_mem_wr_en.value)
            # A store that waits because the buffer is full; a load that waits on a buffered word.
            if writing and int(dut.cpu_inst.store_buffer_inst.full.value):
                coverage["full"] += 1
            if not writing and int(dut.cpu_inst.module_mem_rd_en.value) and int(dut.cpu_inst.store_buf_match.value):
                coverage["match"] += 1
        if peek(dut, DONE_ADDR) == DONE_VALUE:
            return cycle
        # Once the handler is entered, lower the pin so the interrupt is taken once.
        if pin_high and int(dut.cpu_inst.csr_file_inst.mcause.value) == 0x8000_0003:
            await RisingEdge(dut.clk)
            dut.software_interrupt.value = 0
            pin_high = False
    return None


def build_latency() -> int:
    return int(os.environ["STORE_BUFFER_LATENCY"])
