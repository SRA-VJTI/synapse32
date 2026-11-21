"""Random loads, stores, AMOs, LR/SC, uncached device accesses and FENCE.I against a memory model, with the memory
stalling at random.

Each seed is one program over a few sets and more lines per set than the cache has ways, so it hits, misses, merges
into MSHRs and evicts dirty lines in orders nobody wrote down. Both memory ports are held off at random cycles, as a
busy memory would, so requests wait a varying time for their grant and their response. A model replays the
operations in program order and every logged value must match; after the last FENCE.I the backing RAM must match
too. SC may fail (the ISA allows it, with result 1): the model takes the logged result and applies the store only
when SC succeeded.
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
from memory_view import dcache, read_word

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_0308
UART_SCR = 0x2000_001C  # uncached, no side effects: reads back the last byte written
STRESS_BASE = 0x1004_0000
STRESS_LOG = 0x1008_0000

BUILDS = [(0, 8), (1, 8), (2, 1), (2, 2), (2, 8)]  # (memory latency, NUM_MSHR)
SEEDS = [1, 2, 3]  # STRESS_SEEDS="4,5" runs others
OPS = 100  # under 3 KB of code, which the default icache holds
PASSES = 4  # passes after the first run warm code, so data traffic, not fetch, sets the pace
SETS_USED = 3

# The dcache's geometry. Most accesses go to SETS_USED sets with two more tags than ways, so lines are evicted;
# store bursts go to every set with as many tags, more lines than the cache holds, so they mostly miss.
WAYS = 4
SETS = 64
LINE_BYTES = 16
WAY_BYTES = LINE_BYTES * SETS
LINES = [STRESS_BASE + tag * WAY_BYTES + s * LINE_BYTES for tag in range(WAYS + 2) for s in range(SETS_USED)]
BURST_BASE = STRESS_BASE + (WAYS + 2) * WAY_BYTES
BURST_LINES = [BURST_BASE + tag * WAY_BYTES + s * LINE_BYTES for tag in range(WAYS + 2) for s in range(SETS)]
WORDS = [line + 4 * w for line in LINES + BURST_LINES for w in range(LINE_BYTES // 4)]

LOADS = {"lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4}
STORES = {"sb": 1, "sh": 2, "sw": 4}
# Operation kinds and their weights; every program has each kind at least once.
KINDS = {"load": 40, "store": 30, "burst": 5, "amo": 15, "lrsc": 6, "mmio_w": 2, "mmio_r": 2, "fence_i": 4}
AMOS = ["amoswap.w", "amoadd.w", "amoxor.w", "amoand.w", "amoor.w", "amomin.w", "amomax.w", "amominu.w",
        "amomaxu.w"]

# dcache.v engine state
E_IDLE = 0


def _ops(seed: int):
    """The operations of one program, and the initial memory."""
    rng = random.Random(seed)
    kinds = rng.choices(list(KINDS), weights=list(KINDS.values()), k=OPS - len(KINDS)) + list(KINDS)
    rng.shuffle(kinds)
    first_write, first_read = kinds.index("mmio_w"), kinds.index("mmio_r")
    if first_read < first_write:
        # Write the scratch register before the first read, so a read checks a written value, not the reset one.
        kinds[first_read], kinds[first_write] = "mmio_w", "mmio_r"
    ops = []
    for kind in kinds:
        line = rng.choice(LINES)
        if kind == "load":
            op = rng.choice(list(LOADS))
            ops.append((op, line + rng.randrange(0, LINE_BYTES, LOADS[op]), None))
        elif kind == "store":
            op = rng.choice(list(STORES))
            ops.append((op, line + rng.randrange(0, LINE_BYTES, STORES[op]), rng.getrandbits(8 * STORES[op])))
        elif kind == "burst":
            # Every word of a few lines, back to back, as memset does: misses pile up in the MSHRs and the later
            # words of each line merge into its MSHR.
            value = rng.getrandbits(32)
            for target in rng.sample(BURST_LINES, rng.randrange(2, 7)):
                ops.extend(("sw", target + offset, value) for offset in range(0, LINE_BYTES, 4))
        elif kind == "amo":
            ops.append((rng.choice(AMOS), line + rng.randrange(0, LINE_BYTES, 4), rng.getrandbits(32)))
        elif kind == "lrsc":
            ops.append(("lrsc", line + rng.randrange(0, LINE_BYTES, 4), rng.getrandbits(32)))
        elif kind == "mmio_w":
            ops.append(("mmio_w", UART_SCR, rng.getrandbits(32)))
        elif kind == "mmio_r":
            ops.append(("mmio_r", UART_SCR, None))
        else:
            ops.append(("fence_i", None, None))
    initial = {addr: rng.getrandbits(32) for addr in WORDS}
    return ops, initial


def _program(seed: int) -> str:
    body = [f"        li      s1, {STRESS_LOG:#x}", f"        li      s2, {UART_SCR:#x}",
            f"        li      s0, {PASSES}", "stress_pass:"]

    def log(reg):
        body.append(f"        sw      {reg}, 0(s1)\n        addi    s1, s1, 4")

    t0 = t1 = None

    def base(addr):
        # As compiled code does: one base register per line, offsets within it, so a burst issues back to back.
        nonlocal t0
        if t0 is None or not 0 <= addr - t0 < LINE_BYTES:
            t0 = addr
            body.append(f"        li      t0, {addr:#x}")
        return addr - t0

    def exact(addr):
        # AMOs and LR/SC take no offset.
        nonlocal t0
        if t0 != addr:
            t0 = addr
            body.append(f"        li      t0, {addr:#x}")

    def operand(value):
        nonlocal t1
        if value != t1:
            body.append(f"        li      t1, {value:#x}")
            t1 = value

    for op, addr, value in _ops(seed)[0]:
        if op == "fence_i":
            body.append("        fence.i")
            continue
        if op == "mmio_w":
            operand(value)
            body.append("        sw      t1, 0(s2)")
        elif op == "mmio_r":
            body.append("        lw      t2, 0(s2)")
            log("t2")
        elif op in LOADS:
            body.append(f"        {op:<7} t2, {base(addr)}(t0)")
            log("t2")
        elif op in STORES:
            operand(value)
            body.append(f"        {op:<7} t1, {base(addr)}(t0)")
        elif op == "lrsc":
            exact(addr)
            operand(value)
            body.append("        lr.w    t2, (t0)\n        sc.w    t3, t1, (t0)")
            log("t2")
            log("t3")
        else:
            exact(addr)
            operand(value)
            body.append(f"        {op:<9} t2, t1, (t0)")
            log("t2")
    body.append("        addi    s0, s0, -1\n        bnez    s0, stress_pass\n        fence.i")
    return f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
""" + "\n".join(body) + f"""
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b

        .align  2
m_trap:
        li      t1, {TRAP_CAUSE:#x}
        csrr    t0, mcause
        sw      t0, 0(t1)
        csrr    t0, mepc
        sw      t0, 4(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
2:
        j       2b
"""


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value >> (bits - 1) else value


def _amo(op: str, old: int, operand: int) -> int:
    s_old, s_op = _signed(old, 32), _signed(operand, 32)
    return {
        "amoswap.w": operand, "amoadd.w": (old + operand), "amoxor.w": old ^ operand, "amoand.w": old & operand,
        "amoor.w": old | operand, "amomin.w": old if s_old < s_op else operand,
        "amomax.w": old if s_old > s_op else operand, "amominu.w": min(old, operand), "amomaxu.w": max(old, operand),
    }[op] & 0xFFFF_FFFF


def _check(ops, initial, log):
    """Replay ops on the model; return the mismatches, the final memory and how many SCs succeeded and failed."""
    mem = dict(initial)
    scr = 0
    wrong = []
    reads = iter(enumerate(log))
    sc_ok = sc_failed = 0

    def read(addr, size):
        word = mem[addr & ~3]
        return (word >> (8 * (addr & 3))) & ((1 << (8 * size)) - 1)

    def write(addr, size, value):
        shift, mask = 8 * (addr & 3), (1 << (8 * size)) - 1
        mem[addr & ~3] = (mem[addr & ~3] & ~(mask << shift)) | ((value & mask) << shift)

    def expect(what, want):
        i, got = next(reads)
        if got != want & 0xFFFF_FFFF:
            wrong.append(f"log {i} ({what}): got 0x{got:08x}, expected 0x{want & 0xFFFF_FFFF:08x}")
        return got

    for op, addr, value in ops * PASSES:
        if op == "mmio_w":
            scr = value & 0xFF
        elif op == "mmio_r":
            expect("UART SCR", scr)
        elif op in LOADS:
            size = LOADS[op]
            loaded = read(addr, size)
            expect(f"{op} 0x{addr:08x}", _signed(loaded, 8 * size) if op in ("lb", "lh") else loaded)
        elif op in STORES:
            write(addr, STORES[op], value)
        elif op == "lrsc":
            expect(f"lr.w 0x{addr:08x}", read(addr, 4))
            i, result = next(reads)
            if result == 0:
                sc_ok += 1
                write(addr, 4, value)
            elif result == 1:
                sc_failed += 1
            else:
                wrong.append(f"log {i} (sc.w 0x{addr:08x}): result {result:#x}, the ISA defines only 0 and 1")
        elif op != "fence_i":
            old = read(addr, 4)
            expect(f"{op} 0x{addr:08x}", old)
            write(addr, 4, _amo(op, old, value))
    return wrong, mem, sc_ok, sc_failed


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
    return Path(os.environ.get("STRESS_BUILD", Path.cwd() / "build" / "dcache_stress"))


def _seeds() -> list:
    return [int(s) for s in os.environ.get("STRESS_SEEDS", ",".join(map(str, SEEDS))).split(",") if s]


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    lds = build_dir / "stress.ld"
    lds.write_text(LINKER_SCRIPT)
    for seed in _seeds():
        src, elf = build_dir / f"stress_{seed}.S", build_dir / f"stress_{seed}.elf"
        src.write_text(_program(seed))
        subprocess.run(
            [
                "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr_zifencei", "-mabi=ilp32",
                "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
                "-T", str(lds), str(src), "-o", str(elf),
            ],
            check=True,
        )
        subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / f"stress_{seed}.bin")],
                       check=True)
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
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


async def _backpressure(dut, adapter, rng: random.Random):
    """Hold the memory off for random stretches: up to 8 cycles held, then up to 8 free."""
    while True:
        for held in (True, False):
            for _ in range(rng.randrange(0, 9)):
                await FallingEdge(dut.clk)
                adapter.sim_hold.value = int(held)


def _log_entries(ops) -> int:
    """Log words one pass writes: one per load, AMO and SCR read, two per LR/SC."""
    return PASSES * sum(2 if op == "lrsc" else 1 for op, _, _ in ops
                        if op not in STORES and op not in ("fence_i", "mmio_w"))


def _name(seed: int) -> str:
    return f"latency {os.environ['STRESS_LATENCY']}, {os.environ['STRESS_MSHRS']} MSHRs, seed {seed}"


async def _run(dut, seed: int, ops, initial, limit=400000):
    """Run one program under random backpressure; return the cycle it finished (or None) and what it exercised."""
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for adapter in (dut.instr_adapter, dut.data_adapter):
        adapter.sim_hold.value = 0
    data = (_build_dir() / f"stress_{seed}.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for addr, value in initial.items():
        _poke(dut, addr, value)
    for addr in [DONE_ADDR, TRAP_CAUSE, TRAP_EPC] + [STRESS_LOG + 4 * i for i in range(_log_entries(ops))]:
        _poke(dut, addr, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    # Requests the held memory refused, per port, and the cache events that took place.
    counts = {"fetch": 0, "data": 0, "max_mshrs": 0, "merges": 0}
    drivers = [cocotb.start_soon(_backpressure(dut, dut.instr_adapter, random.Random(2 * seed))),
               cocotb.start_soon(_backpressure(dut, dut.data_adapter, random.Random(2 * seed + 1)))]
    cache = dcache(dut)
    done = None
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        await ReadOnly()
        for name, adapter in (("fetch", dut.instr_adapter), ("data", dut.data_adapter)):
            counts[name] += int(adapter.req.value) & int(adapter.sim_hold.value)
        counts["max_mshrs"] = max(counts["max_mshrs"], int(cache.mshr_count.value))
        counts["merges"] += int(cache.store_merge.value)
        if done is None and _peek(dut, DONE_ADDR) == DONE_VALUE:
            done = cycle
        if done is not None and int(cache.eng_state.value) == E_IDLE and int(cache.mshr_count.value) == 0:
            break
    for driver in drivers:
        driver.kill()
    await FallingEdge(dut.clk)
    for adapter in (dut.instr_adapter, dut.data_adapter):
        adapter.sim_hold.value = 0
    return done, counts


@cocotb.test()
async def test_random_accesses_match_a_memory_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    cache = dcache(dut)
    assert cache is not None, "this build has no data cache"
    for seed in _seeds():
        name = _name(seed)
        ops, initial = _ops(seed)
        done, seen = await _run(dut, seed, ops, initial)
        assert done is not None, f"{name}: the program did not finish"
        cause = _peek(dut, TRAP_CAUSE)
        assert cause == 0, f"{name}: unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"
        entries = _log_entries(ops)
        log = [_peek(dut, STRESS_LOG + 4 * i) for i in range(entries)]
        wrong, final, sc_ok, sc_failed = _check(ops, initial, log)
        assert not wrong, f"{name}: {len(wrong)} of {entries} logged values differ from the model; first: {wrong[:3]}"
        stale = [hex(a) for a in WORDS if _ram(dut, a) != final[a]]
        assert not stale, f"{name}: after the last FENCE.I, RAM differs from the model at {len(stale)} words, " \
                          f"first {stale[:3]}"
        assert sc_ok, f"{name}: no SC succeeded, so the stores of LR/SC pairs were never checked"
        assert seen["fetch"] and seen["data"], f"{name}: the held memory never refused a request ({seen})"
        # The counters restart with each run's reset.
        hits, misses, evictions = (int(cache.stat_hits.value), int(cache.stat_misses.value),
                                   int(cache.stat_evictions.value))
        assert hits and misses and evictions and seen["merges"], (
            f"{name}: hits {hits}, misses {misses}, evictions {evictions}, merges {seen['merges']}: a path was "
            "not exercised")
        mshrs = int(os.environ["STRESS_MSHRS"])
        assert mshrs == 1 or seen["max_mshrs"] > 1, f"{name}: never more than one miss outstanding"
        full = int(cache.stat_mshr_full_cycles.value)
        dut._log.info(f"{name}: finished at cycle {done}, SCs {sc_ok} succeeded {sc_failed} failed, {seen}, "
                      f"MSHRs full {full} cycles")


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency, mshrs in BUILDS:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_dcache_stress_lat{latency}_mshr{mshrs}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_dcache_stress",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency, "NUM_MSHR": mshrs},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_dcache_stress",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_dcache_stress",
                "STRESS_BUILD": str(build_dir.resolve()),
                "STRESS_LATENCY": str(latency),
                "STRESS_MSHRS": str(mshrs),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
