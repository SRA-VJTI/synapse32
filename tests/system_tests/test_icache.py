"""Instruction cache.

Warm code runs at one instruction per cycle whatever the fetch latency; a set holds four lines and the
fifth replaces the oldest; FENCE.I makes patched code visible, also when it lands during a line fill; entry into any word of
a line; an interrupt swept over cold code; two virtual pages share one physical line, and a fetch without
execute permission still faults on a cached line; fetches outside RAM bypass the cache. Each program
times its own calls with mcycle, so every check also proves the cache missed or hit where it should.
"""

import os
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

RESULT = 0x1000_0200
VALUES = 0x40  # offset of the value log from the time log
RESULT_WORDS = 48
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_TVAL = 0x1000_0308
TRAP_EPC = 0x1000_030C
IRQ_COUNT = 0x1000_0310
M_SCRATCH = 0x1000_0800

LATENCIES = [0, 1, 2]
SWEEP_LATENCY = 2
WARM_BLOCK = 32
ENTRY_OFFSETS = [0, 4, 8, 12]
SWEEP_RUN = 24
UNCACHED = 0x0000_2000  # unbacked: the simulation memory reads NOPs there
UNCACHED_CYCLES = 40
UNCACHED_SLACK = 6  # instructions in flight when the interrupt is taken, plus margin
SSIP_CAUSE = 0x8000_0003

A5, A6 = 15, 16


def _addi(rd: int, imm: int) -> int:
    return ((imm & 0xFFF) << 20) | (rd << 7) | 0x13


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


def _timed(suffix: str = "", counter: str = "mcycle") -> str:
    """Call the function at s5 (link s6); log its cycles and the a5 it returns, one slot per call."""
    return f"""
timed{suffix}:
        csrr    t5, {counter}
        jalr    ra, 0(s5)
        csrr    t4, {counter}
        sub     t4, t4, t5
        sw      t4, 0(a7)
        sw      a5, {VALUES}(a7)
        addi    a7, a7, 4
        jr      s6
noop{suffix}:
        ret
"""


def _call(label: str, suffix: str = "") -> str:
    return f"""
        la      s5, {label}
        jal     s6, timed{suffix}"""


# Straight-line code timed twice: the second pass must cost one cycle per instruction.
WARM_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      s3, 2
loop:
        csrr    t5, mcycle
        csrr    t6, mcycle
        sub     t6, t6, t5
        csrr    t5, mcycle
        .rept   {WARM_BLOCK}
        addi    t1, t1, 1
        .endr
        csrr    t4, mcycle
        sub     t4, t4, t5
        sub     t4, t4, t6
        sw      t4, 0(a7)
        addi    a7, a7, 4
        addi    s3, s3, -1
        bnez    s3, loop
{_done()}
1:
        j       1b
{M_TRAP}
"""

# Five blocks one way-size apart share a set (4 ways x 64 sets x 16-byte lines); set 0x30 is unused
# by the code around them.
WAYS = 4
WAY_BYTES = 0x400
SET_BLOCKS = [0x8000_1B00 + i * WAY_BYTES for i in range(WAYS + 1)]
MARKS = [0xA0 + i for i in range(WAYS + 1)]
# Fill the set, hit every way, then round-robin: the fifth block replaces way 0, block 0 comes back into
# way 1 and block 1 into way 2; block 3 in way 3 stays.
EVICT_ORDER = list(range(WAYS)) * 2 + [WAYS, 0, WAYS, 1, 3]

EVICT_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
{_call("noop")}
""" + "".join(_call(f"block_{i}") for i in EVICT_ORDER) + f"""
{_done()}
1:
        j       1b
{_timed()}
{M_TRAP}
""" + "".join(f"""
        .org    {addr - INSTR_MEM_BASE:#x}
block_{i}:
        addi    a5, zero, {MARKS[i]:#x}
        ret
""" for i, addr in enumerate(SET_BLOCKS))

# A cached function is patched, and FENCE.I makes the new instruction visible.
PATCHED = 0x8000_1C00
REFETCH_LOG = RESULT + 0x80
REFETCH_PASSES = 3

PATCH_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
{_call("noop")}
{_call("patched")}
{_call("patched")}
        la      t0, patched
        li      t1, {_addi(A5, 2):#x}
        sw      t1, 0(t0)
        fence.i
{_call("patched")}

        # The instruction right after FENCE.I, in a line cached on the previous pass.
        li      a7, {REFETCH_LOG:#x}
        la      a5, refetch
        li      s3, {REFETCH_PASSES}
        li      t1, {_addi(A6, 1):#x}
        li      t2, 1 << 20             # one step of the addi immediate
refetch_loop:
        sw      t1, 0(a5)
        fence.i
refetch:
        addi    a6, zero, 0
        sw      a6, 0(a7)
        addi    a7, a7, 4
        add     t1, t1, t2
        addi    s3, s3, -1
        bnez    s3, refetch_loop
{_done()}
1:
        j       1b
{_timed()}
{M_TRAP}
        .org    {PATCHED - INSTR_MEM_BASE:#x}
patched:
        addi    a5, zero, 1
        ret
"""


RACE_GAPS = [0, 1, 2, 3]
RACE_FENCE_OFFSETS = [8, 12]
RACE_CASES = [(gap, pos) for pos in RACE_FENCE_OFFSETS for gap in RACE_GAPS]


def _race_block(case: int) -> str:
    """Patch the line after FENCE.I, which sits at line offset pos, gap instructions after the store:
    fetch runs ahead into the patched line while FENCE.I waits for the store to drain."""
    gap, pos = RACE_CASES[case]
    pad = (pos // 4 - 1 - gap) % 4
    return f"""
        la      a5, race_patch_{case}
        li      t1, {_addi(A6, case + 1):#x}
        .p2align 4
        .rept   {pad}
        nop
        .endr
        sw      t1, 0(a5)
        .rept   {gap}
        nop
        .endr
        fence.i
        .p2align 4
race_patch_{case}:
        addi    a6, zero, 0
        sw      a6, {4 * case}(a7)
"""


RACE_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
""" + "".join(_race_block(c) for c in range(len(RACE_CASES))) + f"""
{_done()}
1:
        j       1b
{M_TRAP}
"""


def _entry_block(off: int) -> str:
    """Jump into word off/4 of a cold line; the words before it count as wrong-path execution."""
    return f"""
        j       entry_{off}
        .p2align 4
        .rept   8
        nop
        .endr
        .rept   {off // 4}
        addi    s7, s7, 1
        .endr
entry_{off}:
        addi    a6, zero, {0x40 + off}
        addi    a6, a6, 1
        sw      a6, {off}(a7)
"""


ENTRY_PROGRAM = START + f"""
        li      a7, {RESULT:#x}
        li      s7, 0
""" + "".join(_entry_block(off) for off in ENTRY_OFFSETS) + f"""
        sw      s7, {VALUES}(a7)
{_done()}
1:
        j       1b
{M_TRAP}
"""

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
        li      s0, 0
        .rept   {SWEEP_RUN}
        addi    s0, s0, 1
        .endr
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

# Paging: VA1 and VA2 map the same physical code page for execution, VA3 maps it readable only.
ROOT_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
VA1 = 0x4000_0000
VA2 = 0x4000_1000
VA3 = 0x4000_2000
VA_MAIN = 0x4000_3000
PA_SHARED = 0x8000_5000
PA_MAIN = 0x8000_4000
V, R, W, X, A_BIT, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80
INSTR_PAGE_FAULT = 12


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


PAGING_SETUP = [
    (ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), _pte(DATA_MEM_BASE, V | R | W | A_BIT | D)),
    (ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), _pte(INSTR_MEM_BASE, V | R | W | A_BIT | D)),
    (ROOT_TABLE + 4 * (VA1 >> 22), _pte(L0_TABLE, V)),
    (L0_TABLE + 4 * ((VA1 >> 12) & 0x3FF), _pte(PA_SHARED, V | R | X | A_BIT)),
    (L0_TABLE + 4 * ((VA2 >> 12) & 0x3FF), _pte(PA_SHARED, V | R | X | A_BIT)),
    (L0_TABLE + 4 * ((VA3 >> 12) & 0x3FF), _pte(PA_SHARED, V | R | A_BIT)),
    (L0_TABLE + 4 * ((VA_MAIN >> 12) & 0x3FF), _pte(PA_MAIN, V | R | X | A_BIT)),
]


def _call_va(va: int) -> str:
    return f"""
        li      s5, {va:#x}
        jal     s6, timed_s"""


PAGING_PROGRAM = START + f"""
        li      t0, {SATP:#x}
        csrw    satp, t0
        csrwi   mcounteren, 1           # S-mode reads cycle
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0             # MPP = S
        li      t0, {VA_MAIN:#x}
        csrw    mepc, t0
        mret
{M_TRAP}
        .org    {PA_MAIN - INSTR_MEM_BASE:#x}
        li      a7, {RESULT:#x}
        la      s5, noop_s
        jal     s6, timed_s
{_call_va(VA1)}
{_call_va(VA2)}
        li      t0, {PA_SHARED:#x}
        li      t1, {_addi(A5, 2):#x}
        sw      t1, 0(t0)
        fence.i
{_call_va(VA2)}
{_call_va(VA1)}
{_call_va(VA3)}
1:
        j       1b
{_timed("_s", "cycle")}
        .org    {PA_SHARED - INSTR_MEM_BASE:#x}
        addi    a5, zero, 1
        ret
"""

UNCACHED_PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      t0, 0x8
        csrw    mie, t0
        csrsi   mstatus, 0x8
        li      t0, {UNCACHED:#x}
        jr      t0
{M_TRAP}
"""

PROGRAMS = {
    "warm": WARM_PROGRAM,
    "evict": EVICT_PROGRAM,
    "patch": PATCH_PROGRAM,
    "race": RACE_PROGRAM,
    "entry": ENTRY_PROGRAM,
    "sweep": SWEEP_PROGRAM,
    "paging": PAGING_PROGRAM,
    "uncached": UNCACHED_PROGRAM,
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
    return Path(os.environ.get("ICACHE_BUILD", Path.cwd() / "build" / "icache"))


def _compile(build_dir: Path, name: str, program: str) -> None:
    src = build_dir / f"{name}.S"
    lds = build_dir / "icache.ld"
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
    return read_word(dut, _phys_word_index(addr)) & 0xFFFF_FFFF


def _load_image(dut, name: str) -> None:
    data = (_build_dir() / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


async def _run(dut, image: str, setup=(), inject_cycle=None, inject_uncached=False, limit=20000):
    """Run a program until it stores the done marker; return the cycle it did, or None."""
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

    pin_high = False
    uncached_cycles = 0
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        if inject_cycle is not None and cycle == inject_cycle:
            dut.software_interrupt.value = 1
            pin_high = True
        if inject_uncached and uncached_cycles == UNCACHED_CYCLES and not pin_high:
            dut.software_interrupt.value = 1
            pin_high = True
        await ReadOnly()
        if UNCACHED <= int(dut.pc_debug.value) < UNCACHED + 0x1000:
            uncached_cycles += 1
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            return cycle
        # Once the handler is entered, lower the pin so the interrupt is taken once.
        if pin_high and int(dut.cpu_inst.csr_file_inst.mcause.value) == SSIP_CAUSE:
            await RisingEdge(dut.clk)
            dut.software_interrupt.value = 0
            pin_high = False
            inject_uncached = False
    return None


def _latency() -> int:
    return int(os.environ["ICACHE_LATENCY"])


def _name() -> str:
    return f"latency {_latency()}"


def _check_finished(dut, done, expect_trap=False) -> None:
    assert done is not None, f"{_name()}: the program did not finish"
    if not expect_trap:
        cause = _peek(dut, TRAP_CAUSE)
        assert cause == 0, f"{_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"


def _slots(dut, count):
    times = [_peek(dut, RESULT + 4 * i) for i in range(count)]
    values = [_peek(dut, RESULT + VALUES + 4 * i) for i in range(count)]
    return times, values


@cocotb.test()
async def test_warm_code_runs_one_instruction_per_cycle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "warm.bin")
    _check_finished(dut, done)
    cold, warm = _peek(dut, RESULT), _peek(dut, RESULT + 4)
    assert cold > WARM_BLOCK, (
        f"{_name()}: the first pass over {WARM_BLOCK} instructions took {cold} cycles, so its fetches never "
        "missed: the code was not fetched through a cache")
    assert warm == WARM_BLOCK, (
        f"{_name()}: the second pass over {WARM_BLOCK} instructions took {warm} cycles, not one per "
        "instruction: warm code still waited for fetch")


@cocotb.test()
async def test_a_set_holds_its_ways_and_replaces_round_robin(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "evict.bin")
    _check_finished(dut, done)
    times, values = _slots(dut, 1 + len(EVICT_ORDER))
    expected = [MARKS[i] for i in EVICT_ORDER]
    assert values[1:] == expected, (
        f"{_name()}: blocks returned {[hex(v) for v in values[1:]]}, expected {[hex(v) for v in expected]}")
    cold, warm = times[1:1 + WAYS], times[1 + WAYS:1 + 2 * WAYS]
    assert all(w < c for c, w in zip(cold, warm)), (
        f"{_name()}: {WAYS} blocks in one set took {cold} cycles cold and {warm} warm: the set did not hold "
        "them all")
    hit = warm[0]
    _, first_again, fifth_again, second_again, fourth_again = times[1 + 2 * WAYS:]
    got = {"block 0 after the fifth": first_again, "the fifth again": fifth_again,
           "block 1 after block 0": second_again, "block 3": fourth_again}
    want = {"block 0 after the fifth": "miss", "the fifth again": "hit", "block 1 after block 0": "miss",
            "block 3": "hit"}
    wrong = {k: f"{v} cycles" for k, v in got.items() if (v == hit) != (want[k] == "hit")}
    assert not wrong, (
        f"{_name()}: a hit takes {hit} cycles; round-robin expects {want}, got {wrong}")


@cocotb.test()
async def test_fence_i_makes_patched_code_visible(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "patch.bin")
    _check_finished(dut, done)
    times, values = _slots(dut, 4)
    assert times[2] < times[1], (
        f"{_name()}: the function took {times[1]} cycles cold and {times[2]} warm: it was not cached when "
        "it was patched")
    assert values[1:] == [1, 1, 2], (
        f"{_name()}: the function returned {values[1:]}, expected [1, 1, 2]: after FENCE.I it ran the "
        "instruction from before the patch")
    refetched = [_peek(dut, REFETCH_LOG + 4 * i) for i in range(REFETCH_PASSES)]
    assert refetched == list(range(1, REFETCH_PASSES + 1)), (
        f"{_name()}: the instruction after FENCE.I returned {refetched} over {REFETCH_PASSES} passes, "
        f"expected {list(range(1, REFETCH_PASSES + 1))}: it ran the line cached on the previous pass")


@cocotb.test()
async def test_fence_i_during_a_line_fill(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "race.bin")
    _check_finished(dut, done)
    got = [_peek(dut, RESULT + 4 * c) for c in range(len(RACE_CASES))]
    expected = [c + 1 for c in range(len(RACE_CASES))]
    assert got == expected, (
        f"{_name()}: patched instructions after FENCE.I returned {got}, expected {expected} (0 is the "
        "instruction from before the patch)")


@cocotb.test()
async def test_entry_into_any_word_of_a_line(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "entry.bin")
    _check_finished(dut, done)
    got = [_peek(dut, RESULT + off) for off in ENTRY_OFFSETS]
    expected = [0x41 + off for off in ENTRY_OFFSETS]
    assert got == expected, f"{_name()}: entries returned {[hex(v) for v in got]}, expected {[hex(v) for v in expected]}"
    wrong_path = _peek(dut, RESULT + VALUES)
    assert wrong_path == 0, f"{_name()}: {wrong_path} instructions before a jump target ran"


@cocotb.test()
async def test_interrupt_at_every_cycle_of_cold_code(dut):
    if _latency() != SWEEP_LATENCY:
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
        if _peek(dut, RESULT) != SWEEP_RUN:
            failures.append(f"interrupt at cycle {inject}: counted {_peek(dut, RESULT)}, expected {SWEEP_RUN}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


@cocotb.test()
async def test_virtual_pages_share_a_physical_line(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for offset in range(0, 0x1000, 4):
        _poke(dut, ROOT_TABLE + offset, 0)
        _poke(dut, L0_TABLE + offset, 0)
    done = await _run(dut, "paging.bin", setup=PAGING_SETUP)
    _check_finished(dut, done, expect_trap=True)
    times, values = _slots(dut, 5)
    cause, tval, epc = _peek(dut, TRAP_CAUSE), _peek(dut, TRAP_TVAL), _peek(dut, TRAP_EPC)
    assert values[1:] == [1, 1, 2, 2], (
        f"{_name()}: VA1, VA2, then after the patch VA2, VA1 returned {values[1:]}, expected [1, 1, 2, 2] "
        f"(trap: mcause {cause}, mtval 0x{tval:08x}, mepc 0x{epc:08x})")
    assert times[2] < times[1], (
        f"{_name()}: the first call through VA2 took {times[2]} cycles, through VA1 {times[1]}: VA2 did not "
        "hit the line VA1 filled")
    assert (cause, tval, epc) == (INSTR_PAGE_FAULT, VA3, VA3), (
        f"{_name()}: fetch through VA3 (no execute permission) gave mcause {cause}, mtval 0x{tval:08x}, "
        f"mepc 0x{epc:08x}; expected an instruction page fault at 0x{VA3:08x}")


@cocotb.test()
async def test_fetch_outside_ram_bypasses(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await _run(dut, "uncached.bin", inject_uncached=True)
    _check_finished(dut, done, expect_trap=True)
    cause, epc = _peek(dut, TRAP_CAUSE), _peek(dut, TRAP_EPC)
    assert cause == SSIP_CAUSE, f"{_name()}: expected the software interrupt, got mcause 0x{cause:08x}"
    assert UNCACHED < epc < UNCACHED + 0x1000, (
        f"{_name()}: interrupted at 0x{epc:08x}, expected inside the NOPs at 0x{UNCACHED:08x}")
    # Uncached, each NOP takes one fetch; filling lines there would take longer.
    ran, uncached_rate = (epc - UNCACHED) // 4, UNCACHED_CYCLES // (_latency() + 1)
    assert ran >= uncached_rate - UNCACHED_SLACK, (
        f"{_name()}: {ran} NOPs ran in the {UNCACHED_CYCLES} cycles before the interrupt, uncached fetch gives "
        f"about {uncached_rate}: fetches outside RAM were cached")


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_icache_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_icache",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_icache",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_icache",
                "ICACHE_BUILD": str(build_dir.resolve()),
                "ICACHE_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
