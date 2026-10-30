"""Data cache.

Warm accesses cost one cycle; hits continue under a store miss; a full set evicts its PLRU way and writes it
back; stores to a missing line merge in its MSHR and loads wait for the fill; misses beyond the MSHRs wait; a
generated access mix matches a memory model, and RAM matches it after FENCE.I; FENCE.I, the page walker, AMOs
and LR/SC see the cache's data; devices are not cached; an interrupt at any cycle changes nothing.
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
MTIME_LO = 0x0200_BFF8

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
PLRU_OLD = [0x0B0B_0000 + i for i in range(WAYS + 2)]
PLRU_NEW = [0xA0 + i for i in range(WAYS + 2)]
PLRU_WRITTEN_BACK = [1, 2]


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
MERGE_OLD = [0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444]
MERGE_EXPECTED = [0x1111_AA11, 0xBBBB_2222, 0xCCCC_CCCC, 0x4444_4444, 0xFFFF_FFAA, 0xFFFF_BBBB, 0x11, 0xBBBB]

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

# Memory model: byte, halfword and word accesses over more lines than a set has ways, then FENCE.I.
MODEL_BASE = 0x1001_0000
MODEL_LINES = [MODEL_BASE + j * WAY_BYTES + s * 0x10 for j in range(6) for s in range(2)]
MODEL_LOG = 0x1002_0000
MODEL_OPS = 240
MODEL_SEED = 0xDCAC


def _model_ops():
    rng = random.Random(MODEL_SEED)
    ops = []
    for _ in range(MODEL_OPS):
        line = rng.choice(MODEL_LINES)
        if rng.random() < 0.5:
            size = rng.choice([1, 2, 4])
            addr = line + rng.randrange(0, 16, size)
            ops.append(("store", size, addr, rng.getrandbits(8 * size)))
        else:
            kind = rng.choice(["lb", "lbu", "lh", "lhu", "lw"])
            size = {"lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4}[kind]
            ops.append(("load", kind, line + rng.randrange(0, 16, size), None))
    initial = {addr + 4 * w: rng.getrandbits(32) for addr in MODEL_LINES for w in range(4)}
    return ops, initial


def _model_program() -> str:
    ops, _ = _model_ops()
    body = [f"        li      s1, {MODEL_LOG:#x}"]
    for op in ops:
        if op[0] == "store":
            _, size, addr, value = op
            body.append(_store(addr, value, {1: "sb", 2: "sh", 4: "sw"}[size]))
        else:
            _, kind, addr, _ = op
            body.append(_load(addr, kind, "t2"))
            body.append("        sw      t2, 0(s1)\n        addi    s1, s1, 4")
    body.append("        fence.i")
    return START + "\n".join(body) + END


def _model_expected():
    ops, initial = _model_ops()
    mem = dict(initial)
    log = []

    def byte(addr):
        return (mem[addr & ~3] >> (8 * (addr & 3))) & 0xFF

    for op in ops:
        if op[0] == "store":
            _, size, addr, value = op
            for k in range(size):
                a = addr + k
                shift = 8 * (a & 3)
                mem[a & ~3] = (mem[a & ~3] & ~(0xFF << shift)) | (((value >> (8 * k)) & 0xFF) << shift)
        else:
            _, kind, addr, _ = op
            size = {"lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4}[kind]
            value = sum(byte(addr + k) << (8 * k) for k in range(size))
            if kind in ("lb", "lh") and value >> (8 * size - 1):
                value -= 1 << (8 * size)
            log.append(value & 0xFFFF_FFFF)
    return initial, mem, log


# Code written through the data cache (a store miss, then a store hit) runs after FENCE.I.
PATCHED = 0x8000_3000
DIRTY_LINES = [0x1000_5000 + 0x40 * i for i in range(4)]


def _addi_a5(imm: int) -> int:
    return ((imm & 0xFFF) << 20) | (15 << 7) | 0x13


FENCE_I_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        call    patched
        sw      a5, 0(a7)
        la      t0, patched
        li      t1, {_addi_a5(2):#x}
        sw      t1, 0(t0)
""" + "".join(_store(addr, 0xD0 + i) for i, addr in enumerate(DIRTY_LINES)) + f"""
        fence.i
        call    patched
        sw      a5, 4(a7)
        la      t0, patched
        li      t1, {_addi_a5(3):#x}
        sw      t1, 0(t0)
        fence.i
        call    patched
        sw      a5, 8(a7)
""" + END + f"""
        .org    {PATCHED - INSTR_MEM_BASE:#x}
patched:
        addi    a5, zero, 1
        ret
"""

# S-mode writes a leaf PTE, which stays in the cache, and the walk after SFENCE.VMA must use it.
ROOT_TABLE = 0x1003_0000
L0_TABLE = 0x1003_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
VA_DATA = 0x4000_0000
PA_PAGES = [0x1003_2000, 0x1003_3000]
PAGE_VALUES = [0x5A5A_0001, 0x5A5A_0002]
LEAF = L0_TABLE + 4 * ((VA_DATA >> 12) & 0x3FF)
V, R, W, X, A_BIT, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


WALK_SETUP = [
    (ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), _pte(DATA_MEM_BASE, V | R | W | A_BIT | D)),
    (ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), _pte(INSTR_MEM_BASE, V | R | W | X | A_BIT | D)),
    (ROOT_TABLE + 4 * (VA_DATA >> 22), _pte(L0_TABLE, V)),
    (PA_PAGES[0], PAGE_VALUES[0]),
    (PA_PAGES[1], PAGE_VALUES[1]),
]

WALK_PROGRAM = START + f"""
        li      t0, {SATP:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0             # MPP = S
        la      t0, s_main
        csrw    mepc, t0
        mret
s_main:
        li      a7, {RESULT:#x}
        li      t0, {LEAF:#x}
        li      t2, {VA_DATA:#x}
        li      t1, {_pte(PA_PAGES[0], V | R | W | A_BIT | D):#x}
        sw      t1, 0(t0)
        sfence.vma
        lw      a0, 0(t2)
        sw      a0, 0(a7)
        li      t1, {_pte(PA_PAGES[1], V | R | W | A_BIT | D):#x}
        sw      t1, 0(t0)
        sfence.vma
        lw      a0, 0(t2)
        sw      a0, 4(a7)
""" + END

# AMOs and LR/SC on a missing line and on a cached one.
AMO_A = 0x1000_9000
AMO_B = 0x1000_9400
AMO_SETUP = [(AMO_A, 5), (AMO_B, 7)]
AMO_EXPECTED = [5, 8, 7, 11, 0, 1, 12, 0x77]

AMO_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      t0, {AMO_A:#x}
        li      t2, {AMO_B:#x}
        li      t1, 3
        amoadd.w s1, t1, (t0)
        amoadd.w s2, t1, (t0)
        lw      t3, 0(t2)
        li      t1, 0x77
        amoswap.w s3, t1, (t2)
        lr.w    s4, (t0)
        addi    t1, s4, 1
        sc.w    s5, t1, (t0)
        sc.w    s6, t1, (t0)
        lw      s7, 0(t0)
        lw      s8, 0(t2)
        sw      s1, 0(a7)
        sw      s2, 4(a7)
        sw      s3, 8(a7)
        sw      s4, 12(a7)
        sw      s5, 16(a7)
        sw      s6, 20(a7)
        sw      s7, 24(a7)
        sw      s8, 28(a7)
""" + END

# Two reads of mtime 20 cycles apart: a cached timer would return the same value.
DEVICE_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      t0, {MTIME_LO:#x}
        lw      s1, 0(t0)
        .rept   20
        nop
        .endr
        lw      s2, 0(t0)
        sub     s3, s2, s1
        sw      s3, 0(a7)
""" + END

# Interrupt sweep over fills, evictions and merges in one set.
SWEEP_LINES = [0x1000_D000 + i * WAY_BYTES for i in range(WAYS + 1)]
SWEEP_EXPECTED = sum(0x30 + i for i in range(len(SWEEP_LINES)))

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
    "model": _model_program(),
    "fence_i": FENCE_I_PROGRAM,
    "walk": WALK_PROGRAM,
    "amo": AMO_PROGRAM,
    "device": DEVICE_PROGRAM,
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


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


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
    """What the program sees at addr."""
    return read_word(dut, _phys_word_index(addr))


def _ram(dut, addr: int) -> int:
    """What the backing RAM holds at addr, whatever the cache holds."""
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


def _cache(dut):
    try:
        return dut.dcache_inst
    except AttributeError:
        return None


def _require_cache(dut):
    cache = _cache(dut)
    assert cache is not None, f"{_name()}: the design has no data cache"
    return cache


def _load_image(dut, name: str) -> None:
    data = (_build_dir() / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


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


async def _run(dut, image: str, setup=(), inject_cycle=None, limit=40000, coverage=None):
    """Run a program until it stores the done marker, then until the cache is idle; return the done cycle."""
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _load_image(dut, image)
    for offset in range(0, 4 * RESULT_WORDS, 4):
        _poke(dut, RESULT + offset, 0)
    for addr in (DONE_ADDR, TRAP_CAUSE, TRAP_TVAL, TRAP_EPC, IRQ_COUNT):
        _poke(dut, addr, 0)
    for addr, value in setup:
        _poke(dut, addr, value)
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
        if done is None and _peek(dut, DONE_ADDR) == DONE_VALUE:
            done = cycle
        if done is not None and (cache is None or
                                 (int(cache.eng_state.value) == E_IDLE and int(cache.mshr_count.value) == 0)):
            return done
        if pin_high and int(dut.cpu_inst.csr_file_inst.mcause.value) == SSIP_CAUSE:
            await RisingEdge(dut.clk)
            dut.software_interrupt.value = 0
            pin_high = False
    return None


def _latency() -> int:
    return int(os.environ["DCACHE_LATENCY"])


def _mshrs() -> int:
    return int(os.environ["DCACHE_MSHRS"])


def _name() -> str:
    return f"latency {_latency()}, {_mshrs()} MSHRs"


def _check_finished(dut, done) -> None:
    assert done is not None, f"{_name()}: the program did not finish"
    cause = _peek(dut, TRAP_CAUSE)
    assert cause == 0, f"{_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"


def _results(dut, count):
    return [_peek(dut, RESULT + 4 * i) for i in range(count)]


@cocotb.test()
async def test_warm_loads_and_stores_cost_one_cycle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "timing.bin")
    _check_finished(dut, done)
    cold_loads, cold_stores, warm_loads, warm_stores = _results(dut, 4)
    assert cold_loads > BLOCK, (
        f"{_name()}: {BLOCK} loads of four cold lines took {cold_loads} cycles, so they never missed: the "
        "loads were not served by a cache")
    assert warm_loads == BLOCK, (
        f"{_name()}: {BLOCK} loads of warm lines took {warm_loads} cycles, not one each")
    assert warm_stores == BLOCK, (
        f"{_name()}: {BLOCK} stores to warm lines took {warm_stores} cycles, not one each "
        f"(cold: {cold_stores})")


@cocotb.test()
async def test_a_store_miss_does_not_stop_hits(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await _run(dut, "hum.bin", coverage=coverage)
    _check_finished(dut, done)
    load_miss, mixed = _results(dut, 4)[2:]
    assert load_miss > 2, f"{_name()}: a load of a cold line took {load_miss} cycles, so it did not miss"
    assert mixed < load_miss + HUM_LOADS, (
        f"{_name()}: a store miss and {HUM_LOADS} loads of warm lines took {mixed} cycles; a load miss takes "
        f"{load_miss}, so the loads waited for the store's fill")
    _require_cache(dut)
    assert coverage.hits_during_fill > 0, f"{_name()}: no load hit while a fill was running"


@cocotb.test()
async def test_a_full_set_replaces_its_plru_way(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    setup = list(zip(PLRU_LINES, PLRU_OLD))
    done = await _run(dut, "plru.bin", setup=setup)
    _check_finished(dut, done)
    seen = [_peek(dut, addr) for addr in PLRU_LINES]
    assert seen == PLRU_NEW, f"{_name()}: the lines read {[hex(v) for v in seen]}, expected {[hex(v) for v in PLRU_NEW]}"
    in_ram = [i for i, addr in enumerate(PLRU_LINES) if _ram(dut, addr) == PLRU_NEW[i]]
    assert in_ram == PLRU_WRITTEN_BACK, (
        f"{_name()}: lines {in_ram} reached RAM; pseudo-LRU writes back lines {PLRU_WRITTEN_BACK} and keeps "
        "the others dirty in the cache")


@cocotb.test()
async def test_store_misses_merge_and_loads_wait_for_the_fill(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    setup = [(line + 4 * i, v) for line in MERGE_LINES for i, v in enumerate(MERGE_OLD)]
    done = await _run(dut, "merge.bin", setup=setup, coverage=coverage)
    _check_finished(dut, done)
    got = _results(dut, 2 * len(MERGE_EXPECTED))
    assert got == 2 * MERGE_EXPECTED, (
        f"{_name()}: loads returned {[hex(v) for v in got]}, expected {[hex(v) for v in MERGE_EXPECTED]} twice")
    _require_cache(dut)
    assert coverage.merges > 0, f"{_name()}: no store merged into an MSHR"
    assert coverage.load_waits_on_mshr > 0, f"{_name()}: no load waited on an MSHR"


@cocotb.test()
async def test_misses_beyond_the_mshrs_wait(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await _run(dut, "full.bin", coverage=coverage)
    _check_finished(dut, done)
    got = _results(dut, 2 * FULL_COUNT)
    expected = 2 * [0x100 + i for i in range(FULL_COUNT)]
    assert got == expected, f"{_name()}: lines read back {[hex(v) for v in got]}, expected {[hex(v) for v in expected]}"
    cache = _require_cache(dut)
    mshrs = len(cache.mshr_line_q)
    assert mshrs == _mshrs(), f"{_name()}: the cache has {mshrs} MSHRs"
    if _latency() == SWEEP_LATENCY:
        assert coverage.max_mshrs == mshrs, (
            f"{_name()}: at most {coverage.max_mshrs} of {mshrs} MSHRs were in use, so no miss waited for one")
        assert int(cache.stat_mshr_full_cycles.value) > 0, f"{_name()}: no miss found the MSHRs full"


@cocotb.test()
async def test_a_store_to_the_victim_as_it_is_chosen(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await _run(dut, "race.bin", coverage=coverage)
    _check_finished(dut, done)
    got = _results(dut, 4 * len(RACE_GAPS))
    expected = [0xA5, 0x5A] * (2 * len(RACE_GAPS))
    assert got == expected, (
        f"{_name()}: (first line, fifth line) per gap read {[hex(v) for v in got]}, expected 0xa5, 0x5a each: a "
        "store to the line being replaced was lost")
    _require_cache(dut)
    assert coverage.stores_at_victim > 0, f"{_name()}: no store arrived while a victim was chosen"


@cocotb.test()
async def test_mixed_accesses_match_a_memory_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    initial, final, log = _model_expected()
    coverage = Coverage()
    done = await _run(dut, "model.bin", setup=list(initial.items()), coverage=coverage, limit=200000)
    _check_finished(dut, done)
    got = [_peek(dut, MODEL_LOG + 4 * i) for i in range(len(log))]
    wrong = [(i, hex(g), hex(e)) for i, (g, e) in enumerate(zip(got, log)) if g != e]
    assert not wrong, f"{_name()}: {len(wrong)} of {len(log)} loads differ from the model; first (load, got, expected): {wrong[0]}"
    stale = [hex(a) for a in sorted(final) if _ram(dut, a) != final[a]]
    assert not stale, f"{_name()}: after FENCE.I, RAM differs from the model at {len(stale)} words, first {stale[0]}"
    cache = _require_cache(dut)
    hits, misses, evictions = (int(cache.stat_hits.value), int(cache.stat_misses.value),
                               int(cache.stat_evictions.value))
    dut._log.info(f"{_name()}: hits {hits}, misses {misses}, evictions {evictions}, merges {coverage.merges}")
    assert hits and misses and evictions and coverage.merges, (
        f"{_name()}: hits {hits}, misses {misses}, evictions {evictions}, merges {coverage.merges}: a path was "
        "not exercised")


@cocotb.test()
async def test_fence_i_makes_code_written_through_the_cache_visible(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "fence_i.bin")
    _check_finished(dut, done)
    got = _results(dut, 3)
    assert got == [1, 2, 3], (
        f"{_name()}: the patched function returned {got}, expected [1, 2, 3]: after FENCE.I it ran code from "
        "before the patch")
    stale = [hex(a) for i, a in enumerate(DIRTY_LINES) if _ram(dut, a) != 0xD0 + i]
    assert not stale, f"{_name()}: lines written before FENCE.I are not in RAM: {stale}"


@cocotb.test()
async def test_the_walker_sees_page_tables_in_the_cache(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE + offset, 0)
    done = await _run(dut, "walk.bin", setup=WALK_SETUP)
    _check_finished(dut, done)
    got = _results(dut, 2)
    assert got == PAGE_VALUES, (
        f"{_name()}: loads through the PTE written by the program returned {[hex(v) for v in got]}, expected "
        f"{[hex(v) for v in PAGE_VALUES]}")


@cocotb.test()
async def test_amos_and_lr_sc_on_hits_and_misses(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "amo.bin", setup=AMO_SETUP)
    _check_finished(dut, done)
    got = _results(dut, len(AMO_EXPECTED))
    assert got == AMO_EXPECTED, f"{_name()}: got {got}, expected {AMO_EXPECTED}"


@cocotb.test()
async def test_device_registers_are_not_cached(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "device.bin")
    _check_finished(dut, done)
    delta = _peek(dut, RESULT)
    assert 20 <= delta < 200, f"{_name()}: two reads of mtime 20 instructions apart differ by {delta}"


@cocotb.test()
async def test_interrupt_at_every_cycle_of_misses_and_evictions(dut):
    if _latency() != SWEEP_LATENCY or _mshrs() != 8:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    reference = await _run(dut, "sweep.bin")
    _check_finished(dut, reference)
    failures = []
    taken = 0
    for inject in range(reference + 1):
        done = await _run(dut, "sweep.bin", inject_cycle=inject, limit=reference + 400)
        if done is None:
            failures.append(f"interrupt at cycle {inject}: did not finish")
            continue
        count = _peek(dut, IRQ_COUNT)
        taken += count
        if count > 1:
            failures.append(f"interrupt at cycle {inject}: handler ran {count} times")
        if _peek(dut, RESULT) != SWEEP_EXPECTED:
            failures.append(f"interrupt at cycle {inject}: sum {_peek(dut, RESULT):#x}, expected {SWEEP_EXPECTED:#x}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        sim_build = Path.cwd() / "sim_build" / f"sim_build_dcache_lat{latency}_mshr{mshrs}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_dcache",
            parameters=parameters,
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_dcache",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_dcache",
                "DCACHE_BUILD": str(build_dir.resolve()),
                "DCACHE_LATENCY": str(latency),
                "DCACHE_MSHRS": str(mshrs),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
