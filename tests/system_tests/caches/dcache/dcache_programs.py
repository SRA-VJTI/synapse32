"""Programs, builds and helpers shared by the data cache tests; each test file runs them on every build."""

import os
import subprocess
from pathlib import Path

from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

from support import INSTR_MEM_BASE, dcache, peek, poke


RESULT = 0x1000_0200
RESULT_WORDS = 64
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_TVAL = 0x1000_0308
TRAP_EPC = 0x1000_030C
IRQ_COUNT = 0x1000_0310
M_SCRATCH = 0x1000_0380

BUILDS = [(0, 8), (1, 8), (2, 8), (2, 1)]  # (memory latency, NUM_MSHR); DCACHE_BUILDS="0:8,2:1" picks some
DEFAULT_MSHRS = 8  # top's NUM_MSHR, passed only when a build differs
SWEEP_LATENCY = 2
WAYS = 4
WAY_BYTES = 0x400  # 64 sets x 16-byte lines
SSIP_CAUSE = 0x8000_0003


# dcache.v engine states
E_IDLE, E_VICTIM, E_FILL = 0, 2, 5


def _done() -> str:
    return f"""
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
"""


M_TRAP = f"""
        .align  2
m_trap:
        csrr    t0, mcause
        li      t1, {TRAP_CAUSE:#x}
        sw      t0, 0(t1)
        csrr    t0, mtval
        sw      t0, 4(t1)
        csrr    t0, mepc
        sw      t0, 8(t1)
{_done()}
1:
        j       1b
"""

START = """
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
"""

END = f"""
{_done()}
1:
        j       1b
{M_TRAP}
"""


def _timed(name: str, body: str, slot: str) -> str:
    """Time body with mcycle, less the cost of reading mcycle, into slot(a7)."""
    return f"""
        csrr    t5, mcycle
        csrr    t6, mcycle
        sub     t6, t6, t5
        csrr    t5, mcycle
{body}
        csrr    t4, mcycle
        sub     t4, t4, t5
        sub     t4, t4, t6
        sw      t4, {slot}(a7)          # {name}
"""


# Two passes over a block of loads and a block of stores; the second pass must cost one cycle each.
BLOCK = 16
LOAD_BUF = 0x1000_2000
STORE_BUF = 0x1000_2040

_LOAD_BLOCK = "".join(f"        lw      t1, {4 * i}(s1)\n" for i in range(BLOCK))
_STORE_BLOCK = "".join(f"        sw      s3, {4 * i}(s2)\n" for i in range(BLOCK))

TIMING_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      s1, {LOAD_BUF:#x}
        li      s2, {STORE_BUF:#x}
        li      s3, 2
loop:
{_timed("loads", _LOAD_BLOCK, "0")}
{_timed("stores", _STORE_BLOCK, "4")}
        addi    a7, a7, 8
        addi    s3, s3, -1
        bnez    s3, loop
""" + END


# A load miss waits for its line; a store miss followed by loads to warm lines does not.
HUM_LOADS = 8
HUM_WARM = 0x1000_B000
HUM_STORE = 0x1000_C000
HUM_LOAD = 0x1000_C400

_HUM_HITS = "".join(f"        lw      t2, {4 * i}(s1)\n" for i in range(HUM_LOADS))

HUM_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      s1, {HUM_WARM:#x}
""" + "".join(f"        lw      t1, {4 * i}(s1)\n" for i in range(HUM_LOADS)) + f"""
        li      s4, {HUM_LOAD:#x}
        li      s5, {HUM_STORE:#x}
        li      s3, 2
loop:
{_timed("load miss", "        lw      t1, 0(s4)", "0")}
{_timed("store miss then hits", "        sw      s3, 0(s5)\n" + _HUM_HITS, "4")}
        addi    a7, a7, 8
        addi    s4, s4, 0x10
        addi    s5, s5, 0x10
        addi    s3, s3, -1
        bnez    s3, loop
""" + END


# Six lines of one set; after hits on lines 3 and 0, PLRU evicts line 2, then line 1, and writes both back.
PLRU_LINES = [0x1000_4000 + i * WAY_BYTES for i in range(WAYS + 2)]

PLRU_NEW = [0xA0 + i for i in range(WAYS + 2)]


def _store(addr: int, value: int, op: str = "sw", offset: int = 0) -> str:
    return f"""
        li      t0, {addr:#x}
        li      t1, {value:#x}
        {op}    t1, {offset}(t0)"""


def _load(addr: int, op: str = "lw", reg: str = "t2", offset: int = 0) -> str:
    return f"""
        li      t0, {addr:#x}
        {op}    {reg}, {offset}(t0)"""


PLRU_PROGRAM = START + "".join(_store(PLRU_LINES[i], PLRU_NEW[i]) for i in range(WAYS)) + \
    _load(PLRU_LINES[3]) + _load(PLRU_LINES[0]) + \
    _store(PLRU_LINES[4], PLRU_NEW[4]) + _store(PLRU_LINES[5], PLRU_NEW[5]) + END


# Stores to a missing line merge into its MSHR; loads wait for the fill. The second pass runs from warm code.
MERGE_LINES = [0x1000_8100, 0x1000_8110]


MERGE_PROGRAM = START + f"""
        li      t0, {MERGE_LINES[0]:#x}
        li      t4, {RESULT:#x}
        li      t1, 0xAA
        li      t2, 0xBBBB
        li      t3, 0xCCCCCCCC
        li      s3, 2
loop:
        sb      t1, 1(t0)
        sh      t2, 6(t0)
        sw      t3, 8(t0)
        lw      a0, 0(t0)
        lw      a1, 4(t0)
        lw      a2, 8(t0)
        lw      a3, 12(t0)
        lb      a4, 1(t0)
        lh      a5, 6(t0)
        lbu     a6, 3(t0)
        lhu     s2, 6(t0)
        sw      a0, 0(t4)
        sw      a1, 4(t4)
        sw      a2, 8(t4)
        sw      a3, 12(t4)
        sw      a4, 16(t4)
        sw      a5, 20(t4)
        sw      a6, 24(t4)
        sw      s2, 28(t4)
        addi    t0, t0, 0x10
        addi    t4, t4, 32
        addi    s3, s3, -1
        bnez    s3, loop
""" + END


# More store misses than MSHRs, then every line read back. The second pass runs from warm code.
FULL_BASE = 0x1000_A000
FULL_COUNT = 12
FULL_PASS = 0x100

FULL_PROGRAM = START + f"""
        li      t0, {FULL_BASE:#x}
        li      t4, {RESULT:#x}
        li      s3, 2
loop:
        li      t1, 0x100
""" + "".join(f"""
        sw      t1, {16 * i}(t0)
        addi    t1, t1, 1""" for i in range(FULL_COUNT)) + "".join(f"""
        lw      t2, {16 * i}(t0)
        sw      t2, {4 * i}(t4)""" for i in range(FULL_COUNT)) + f"""
        addi    t0, t0, {FULL_PASS:#x}
        addi    t4, t4, {4 * FULL_COUNT}
        addi    s3, s3, -1
        bnez    s3, loop
""" + END


# A miss picks way 0 as the victim, and a store to way 0's line follows 0 to 3 instructions later.
RACE_BASE = 0x1000_E000
RACE_GAPS = [0, 1, 2, 3]
RACE_PASS_SETS = 8


def _race_block(gap: int) -> str:
    return f"""
        addi    t0, s1, {0x10 * gap}
        li      t3, {2 * WAY_BYTES:#x}
        add     t1, t0, t3
        add     t3, t1, t3
        lw      t2, 0(t0)
        lw      t2, {WAY_BYTES}(t0)
        lw      t2, 0(t1)
        lw      t2, {WAY_BYTES}(t1)
        sw      a0, 0(t3)
""" + "        nop\n" * gap + f"""        sw      a1, 0(t0)
        lw      t2, 0(t0)
        sw      t2, {8 * gap}(t4)
        lw      t2, 0(t3)
        sw      t2, {8 * gap + 4}(t4)
"""


RACE_PROGRAM = START + f"""
        li      s1, {RACE_BASE:#x}
        li      t4, {RESULT:#x}
        li      a0, 0x5A
        li      a1, 0xA5
        li      s3, 2
loop:
""" + "".join(_race_block(g) for g in RACE_GAPS) + f"""
        addi    s1, s1, {0x10 * RACE_PASS_SETS}
        addi    t4, t4, {8 * len(RACE_GAPS)}
        addi    s3, s3, -1
        bnez    s3, loop
""" + END


V, R, W, X, A_BIT, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80


# Interrupt sweep over fills, evictions and merges in one set.
SWEEP_LINES = [0x1000_D000 + i * WAY_BYTES for i in range(WAYS + 1)]


SWEEP_PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        la      t0, irq_trap
        csrw    mtvec, t0
        li      t0, 0x8
        csrw    mie, t0
        csrsi   mstatus, 0x8
""" + "".join(_store(addr, 0x30 + i) for i, addr in enumerate(SWEEP_LINES)) + f"""
        li      s0, 0
""" + "".join(f"""
        li      t0, {addr:#x}
        lw      t1, 0(t0)
        add     s0, s0, t1""" for addr in SWEEP_LINES) + f"""
        li      t0, {RESULT:#x}
        sw      s0, 0(t0)
{_done()}
1:
        j       1b

        .align  2
irq_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
        sw      t1, 4(sp)
        li      t0, {IRQ_COUNT:#x}
        lw      t1, 0(t0)
        addi    t1, t1, 1
        sw      t1, 0(t0)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret
"""

PROGRAMS = {
    "timing": TIMING_PROGRAM,
    "hum": HUM_PROGRAM,
    "plru": PLRU_PROGRAM,
    "merge": MERGE_PROGRAM,
    "full": FULL_PROGRAM,
    "race": RACE_PROGRAM,
    "sweep": SWEEP_PROGRAM,
}

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) }}
}}
"""


def _build_dir() -> Path:
    return Path(os.environ.get("DCACHE_BUILD", Path.cwd() / "build" / "dcache"))


def _compile(build_dir: Path, name: str, program: str) -> None:
    src = build_dir / f"{name}.S"
    lds = build_dir / "dcache.ld"
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
    for name, program in PROGRAMS.items():
        _compile(build_dir, name, program)


def _cache(dut):
    return dcache(dut)


def require_cache(dut):
    cache = _cache(dut)
    assert cache is not None, f"{build_name()}: the design has no data cache"
    return cache


def _load_image(dut, name: str) -> None:
    data = (_build_dir() / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


class Coverage:
    """Cache events seen over a run, sampled every cycle."""

    def __init__(self):
        self.merges = 0
        self.load_waits_on_mshr = 0
        self.hits_during_fill = 0
        self.max_mshrs = 0
        self.stores_at_victim = 0

    def sample(self, cache) -> None:
        self.merges += int(cache.store_merge.value)
        req, we, match = int(cache.req.value), int(cache.we.value), int(cache.match_any.value)
        self.load_waits_on_mshr += req and not we and match
        self.hits_during_fill += int(cache.load_hit.value) and int(cache.eng_state.value) != E_IDLE
        self.max_mshrs = max(self.max_mshrs, int(cache.mshr_count.value))
        self.stores_at_victim += req and we and int(cache.eng_state.value) == E_VICTIM


async def run_image(dut, image: str, setup=(), inject_cycle=None, limit=40000, coverage=None):
    """Run a program until it stores the done marker, then until the cache is idle; return the done cycle."""
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _load_image(dut, image)
    for offset in range(0, 4 * RESULT_WORDS, 4):
        poke(dut, RESULT + offset, 0)
    for addr in (DONE_ADDR, TRAP_CAUSE, TRAP_TVAL, TRAP_EPC, IRQ_COUNT):
        poke(dut, addr, 0)
    for addr, value in setup:
        poke(dut, addr, value)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    cache = _cache(dut)
    pin_high = False
    done = None
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        if inject_cycle is not None and cycle == inject_cycle:
            dut.software_interrupt.value = 1
            pin_high = True
        await ReadOnly()
        if coverage is not None and cache is not None:
            coverage.sample(cache)
        if done is None and peek(dut, DONE_ADDR) == DONE_VALUE:
            done = cycle
        if done is not None and (cache is None or
                                 (int(cache.eng_state.value) == E_IDLE and int(cache.mshr_count.value) == 0)):
            return done
        if pin_high and int(dut.cpu_inst.csr_file_inst.mcause.value) == SSIP_CAUSE:
            await RisingEdge(dut.clk)
            dut.software_interrupt.value = 0
            pin_high = False
    return None


def build_latency() -> int:
    return int(os.environ["DCACHE_LATENCY"])


def build_mshrs() -> int:
    return int(os.environ["DCACHE_MSHRS"])


def build_name() -> str:
    return f"latency {build_latency()}, {build_mshrs()} MSHRs"


def check_finished(dut, done) -> None:
    assert done is not None, f"{build_name()}: the program did not finish"
    cause = peek(dut, TRAP_CAUSE)
    assert cause == 0, f"{build_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{peek(dut, TRAP_EPC):08x}"


def results(dut, count):
    return [peek(dut, RESULT + 4 * i) for i in range(count)]
