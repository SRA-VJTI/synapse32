"""Memory that answers late.

top takes a MEM_LATENCY parameter, the cycles the backing store takes to answer an access. 0 is
today's combinational memory; a larger latency holds the pipeline until the response arrives.

The same program runs at latency 0, 1, 2 and 4. Every later run must commit the same stores in the
same order, end with the same memory, and retire the same number of instructions, while taking more
cycles. Interrupts are swept across every cycle of the latency-2 run. A second program checks that
each load from the UART data register pops exactly one received byte.
"""

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

SCRATCH = 0x1000_0100
ATOMIC = 0x1000_0140
AMO = 0x1000_0180
RESULT_LO = 0x1000_0200
RESULT_WORDS = 16
RESULT_HI = RESULT_LO + 4 * RESULT_WORDS
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
ACK_ADDR = 0x1000_0304
UART_RBR = 0x2000_0000
UART_GO = 0x1000_0400
UART_RESULT = 0x1000_0404
M_SCRATCH = 0x1000_0800
LOOPS = 8
# Each AMO is a read then a write, so MEM waits even when memory answers in the same cycle.
AMO_COUNT = LOOPS
LATENCIES = [0, 1, 2, 4]
SWEEP_LATENCY = 2

PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        la      t0, m_trap
        csrw    mtvec, t0
        li      t0, 0xAAA
        csrw    mie, t0
        csrsi   mstatus, 0x8
        li      t6, {RESULT_LO:#x}
        li      a1, {SCRATCH:#x}
        li      a2, {ATOMIC:#x}
        li      a3, {AMO:#x}
        li      s0, 0
        li      s1, {LOOPS}
loop:
        sw      s0, 0(a1)
        lw      t0, 0(a1)
        addi    t0, t0, 3
        sb      t0, 4(a1)
        lbu     t1, 4(a1)
        sh      t1, 8(a1)
        lhu     t2, 8(a1)
        lr.w    t3, (a2)
        addi    t3, t3, 1
        sc.w    t4, t3, (a2)
        amoadd.w t5, t2, (a3)
        add     s0, s0, t0
        add     s0, s0, t5
        sw      s0, 0(t6)
        jal     ra, tail
        addi    s1, s1, -1
        bnez    s1, loop
        lw      t0, 0(a2)
        sw      t0, 4(t6)
        lw      t0, 0(a3)
        sw      t0, 8(t6)
        sw      s0, 12(t6)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

tail:
        lw      t0, 0(a1)
        xori    t0, t0, 0x55
        sw      t0, 12(a1)
        ret

        .align  2
m_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
        csrr    t0, mcause
        bltz    t0, m_irq
        csrr    t0, mepc
        addi    t0, t0, 4
        csrw    mepc, t0
        j       m_ret
m_irq:
        li      t0, {ACK_ADDR:#x}
        sw      t0, 0(t0)
m_ret:
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret
"""

UART_PROGRAM = f"""
        .section .text.init, "ax"
        .global _start
_start:
        li      a0, {UART_RBR:#x}
        li      a1, {UART_GO:#x}
wait_go:
        lw      t0, 0(a1)
        beqz    t0, wait_go
        lw      t1, 0(a0)
        lw      t2, 0(a0)
        li      a2, {UART_RESULT:#x}
        sw      t1, 0(a2)
        sw      t2, 4(a2)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin
"""

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
    return Path(os.environ.get("MEMORY_WAIT_BUILD", Path.cwd() / "build" / "memory_wait"))


def _compile(build_dir: Path, name: str, program: str) -> None:
    src = build_dir / f"{name}.S"
    lds = build_dir / "memory_wait.ld"
    elf = build_dir / f"{name}.elf"
    src.write_text(program)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / f"{name}.bin")], check=True)


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    _compile(build_dir, "image", PROGRAM)
    _compile(build_dir, "uart", UART_PROGRAM)
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
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


def _load_image(dut, build_dir: Path, name: str = "image.bin") -> None:
    data = (build_dir / name).read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))


class Run:
    def __init__(self):
        self.stores = []
        self.memory = []
        self.cycles = None
        self.instret = None
        self.wait_cycles = 0


async def run_program(dut, inject_cycle=None, limit=20000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for offset in range(0, 0x100, 4):
        _poke(dut, SCRATCH + offset, 0)
        _poke(dut, RESULT_LO + offset, 0)
    _poke(dut, ATOMIC, 0)
    _poke(dut, AMO, 0)
    _poke(dut, DONE_ADDR, 0)
    _poke(dut, ACK_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    result = Run()
    pin_high = False
    lower_pin = False
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        if inject_cycle is not None and cycle == inject_cycle:
            dut.software_interrupt.value = 1
            pin_high = True
        if lower_pin:
            dut.software_interrupt.value = 0
            pin_high = False
            lower_pin = False
        await ReadOnly()
        if int(dut.cpu_inst.mem_wait.value) or int(dut.cpu_inst.fetch_wait.value):
            result.wait_cycles += 1
        if int(dut.cpu_mem_write_en.value) and not int(dut.cpu_store_page_fault.value):
            addr = int(dut.cpu_mem_write_addr.value)
            # Count the write once, in the cycle the memory port accepts it.
            if int(dut.data_write_fire.value):
                if RESULT_LO <= addr < RESULT_HI:
                    result.stores.append((addr, int(dut.cpu_mem_write_data.value),
                                          int(dut.cpu_write_byte_enable.value)))
                elif addr == ACK_ADDR and pin_high:
                    lower_pin = True
                elif addr == DONE_ADDR and int(dut.cpu_mem_write_data.value) == DONE_VALUE:
                    result.cycles = cycle
    # the done store ends the run
        if result.cycles is not None:
            break
    await RisingEdge(dut.clk)
    result.memory = [_peek(dut, RESULT_LO + 4 * i) for i in range(RESULT_WORDS)]
    result.memory += [_peek(dut, SCRATCH), _peek(dut, ATOMIC), _peek(dut, AMO)]
    result.instret = int(dut.cpu_inst.csr_file_inst.instret_counter.value)
    dut.software_interrupt.value = 0
    return result


def _reference_path(latency: int) -> Path:
    return _build_dir() / f"reference-lat{latency}.json"


@cocotb.test()
async def test_program_is_latency_independent(dut):
    latency = int(os.environ["MEMORY_WAIT_LATENCY"])
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _load_image(dut, _build_dir())

    result = await run_program(dut)
    assert result.cycles is not None, f"latency {latency}: the program did not finish"
    assert result.stores, f"latency {latency}: no result stores"

    record = {"cycles": result.cycles, "instret": result.instret, "wait_cycles": result.wait_cycles,
              "stores": result.stores, "memory": result.memory}
    _reference_path(latency).write_text(json.dumps(record))
    dut._log.info(f"latency {latency}: {result.cycles} cycles, {result.instret} instret, "
                  f"{result.wait_cycles} wait cycles, {len(result.stores)} result stores")

    if latency == 0:
        assert result.wait_cycles == AMO_COUNT, (
            f"a memory that answers in the same cycle should only make MEM wait for the write phase of "
            f"each of the {AMO_COUNT} AMOs, but it waited {result.wait_cycles} cycles")
        return

    base = json.loads(_reference_path(0).read_text())
    problems = []
    if result.wait_cycles == 0:
        problems.append("the pipeline never waited, so the latency had no effect")
    if [list(s) for s in result.stores] != base["stores"]:
        first = next((i for i, (a, b) in enumerate(zip(result.stores, base["stores"])) if list(a) != b),
                     min(len(result.stores), len(base["stores"])))
        problems.append(f"store #{first} differs: {result.stores[first:first + 1]} vs {base['stores'][first:first + 1]}")
    if result.memory != base["memory"]:
        problems.append(f"final memory differs: {result.memory} vs {base['memory']}")
    if result.instret != base["instret"]:
        problems.append(f"retired {result.instret} instructions, latency 0 retired {base['instret']}")
    if result.cycles <= base["cycles"]:
        problems.append(f"took {result.cycles} cycles, not more than latency 0's {base['cycles']}")
    assert not problems, f"latency {latency}: " + "; ".join(problems)


@cocotb.test()
async def test_interrupt_during_wait_is_transparent(dut):
    """With a waiting memory, an interrupt at any cycle must not disturb the program."""
    latency = int(os.environ["MEMORY_WAIT_LATENCY"])
    if latency != SWEEP_LATENCY:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _load_image(dut, _build_dir())

    reference = await run_program(dut)
    assert reference.cycles is not None, "reference run did not finish"
    failures = []
    for inject in range(reference.cycles + 1):
        trial = await run_program(dut, inject_cycle=inject, limit=reference.cycles + 400)
        if trial.cycles is None:
            failures.append(f"interrupt at cycle {inject}: did not finish")
        elif trial.stores != reference.stores:
            first = next((i for i, (a, b) in enumerate(zip(trial.stores, reference.stores)) if a != b),
                         min(len(trial.stores), len(reference.stores)))
            failures.append(f"interrupt at cycle {inject}: store #{first} differs")
        elif trial.memory != reference.memory:
            failures.append(f"interrupt at cycle {inject}: final memory differs")
    dut._log.info(f"latency {latency}: swept {reference.cycles + 1} interrupt cycles, {len(failures)} failures")
    assert not failures, f"{len(failures)} interrupt cycles not transparent; first: {failures[0]}"


async def _send_byte(dut, value: int) -> None:
    bit_cycles = int(dut.uart_inst.baud_div.value) + 1
    for bit in [0] + [(value >> i) & 1 for i in range(8)] + [1]:
        dut.uart_rx.value = bit
        await ClockCycles(dut.clk, bit_cycles)


@cocotb.test()
async def test_uart_read_pops_one_byte(dut):
    """Three bytes wait in the UART; two loads from its data register must return the first two.

    A third byte is needed: once the queue empties, the register shows the last byte received.
    """
    latency = int(os.environ["MEMORY_WAIT_LATENCY"])
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _load_image(dut, _build_dir(), "uart.bin")
    for addr in (UART_GO, UART_RESULT, UART_RESULT + 4, DONE_ADDR):
        _poke(dut, addr, 0)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    await _send_byte(dut, ord("A"))
    await _send_byte(dut, ord("B"))
    await _send_byte(dut, ord("C"))
    _poke(dut, UART_GO, 1)
    for _ in range(2000):
        await RisingEdge(dut.clk)
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            break
    assert _peek(dut, DONE_ADDR) == DONE_VALUE, f"latency {latency}: the program did not finish"
    got = [chr(_peek(dut, UART_RESULT) & 0xFF), chr(_peek(dut, UART_RESULT + 4) & 0xFF)]
    assert got == ["A", "B"], f"latency {latency}: read {got}, expected ['A', 'B']"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_memory_wait_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_memory_wait",
            parameters={"MEM_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_memory_wait",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_memory_wait",
                "MEMORY_WAIT_BUILD": str(build_dir.resolve()),
                "MEMORY_WAIT_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
