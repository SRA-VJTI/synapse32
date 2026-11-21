"""The UART sends and receives at 16 x divisor clock cycles per bit, as a 16550 does."""

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
UART_BASE = 0x2000_0000

RESULT = 0x1000_0200
READY = RESULT + 0x20
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_030C

LATENCIES = [0]
DIVISORS = [1, 2, 27]  # 27 is 115200 baud at 50 MHz
TX_BYTES = [0x55, 0xA3]  # 0x55 changes level at every bit boundary
RX_BYTES = [0xC6, 0x39, 0x96]
POLL = 8000
LIMIT = 80000


def _wait_lsr(mask: int) -> str:
    """Poll LSR until a bit of mask is set, at most POLL times; t0 is 0 on a timeout."""
    return f"""
        li      t2, {POLL}
1:
        lw      t0, 20(s0)
        andi    t0, t0, {mask:#x}
        bnez    t0, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
"""


def _divisor_block(index: int, divisor: int) -> str:
    sends = "".join(f"        li      t0, {b:#x}\n        sw      t0, 0(s0)\n" for b in TX_BYTES)
    return f"""
        li      t0, 0x83
        sw      t0, 12(s0)              # LCR: DLAB, 8N1
        li      t0, {divisor & 0xFF:#x}
        sw      t0, 0(s0)               # DLL
        li      t0, {divisor >> 8:#x}
        sw      t0, 4(s0)               # DLM
        li      t0, 0x03
        sw      t0, 12(s0)              # LCR: 8N1
        li      t0, 0x07
        sw      t0, 8(s0)               # FCR: enable and clear FIFOs
{sends}{_wait_lsr(0x40)}
        li      t0, {divisor}
        sw      t0, {READY - RESULT}(a7)
{_wait_lsr(0x01)}
        beqz    t0, 3f
        lw      t0, 0(s0)
        sw      t0, {4 * index}(a7)
3:
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a7, {RESULT:#x}
        li      s0, {UART_BASE:#x}
{"".join(_divisor_block(i, d) for i, d in enumerate(DIVISORS))}
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
        sw      t0, 8(t1)
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
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
    return Path(os.environ.get("UART_BAUD_BUILD", Path.cwd() / "build" / "uart_baud"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "uart.S"
    lds = build_dir / "uart.ld"
    elf = build_dir / "uart.elf"
    src.write_text(PROGRAM)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr_zifencei", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "uart.bin")],
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


async def _send(dut, value: int, bit_cycles: int) -> None:
    await FallingEdge(dut.clk)
    for bit in [0] + [(value >> i) & 1 for i in range(8)] + [1]:
        dut.uart_rx.value = bit
        await ClockCycles(dut.clk, bit_cycles, rising=False)


def _level(edges, at: int) -> int:
    level = 1
    for cycle, value in edges:
        if cycle > at:
            break
        level = value
    return level


def _frames(edges):
    """Decode the frames on uart_tx, frame i at the bit time of DIVISORS[i // 2]; return (byte, misplaced edges)."""
    frames = []
    after = -1
    for index in range(len(DIVISORS) * len(TX_BYTES)):
        bit = 16 * DIVISORS[index // len(TX_BYTES)]
        start = next((c for c, v in edges if c > after and v == 0), None)
        if start is None:
            break
        levels = [_level(edges, start + bit // 2 + k * bit) for k in range(10)]
        value = sum(levels[1 + i] << i for i in range(8))
        if levels[0] != 0 or levels[9] != 1:
            value = None
        misplaced = [c - start for c, _ in edges if start < c < start + 10 * bit and (c - start) % bit]
        frames.append((value, misplaced))
        after = start + 9 * bit + bit // 2
    return frames


@cocotb.test()
async def test_bit_time_is_16_times_the_divisor(dut):
    cocotb.start_soon(Clock(dut.clk, 20, units="ns").start())
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    data = (_build_dir() / "uart.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for offset in range(0, 4 * len(DIVISORS), 4):
        _poke(dut, RESULT + offset, 0xDEAD_BEEF)
    for addr in (READY, DONE_ADDR, TRAP_CAUSE, TRAP_EPC):
        _poke(dut, addr, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    edges = []
    level = 1
    sent = set()
    done = False
    for cycle in range(LIMIT):
        await RisingEdge(dut.clk)
        await ReadOnly()
        tx = int(dut.uart_tx.value)
        if tx != level:
            edges.append((cycle, tx))
            level = tx
        ready = _peek(dut, READY)
        if ready in DIVISORS and ready not in sent:
            sent.add(ready)
            index = DIVISORS.index(ready)
            cocotb.start_soon(_send(dut, RX_BYTES[index], 16 * ready))
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            done = True
            break

    cause = _peek(dut, TRAP_CAUSE)
    assert cause == 0, f"unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"
    wrong = [] if done else [f"the program did not finish in {LIMIT} cycles"]
    frames = _frames(edges)
    expected = [b for _ in DIVISORS for b in TX_BYTES]
    for index, want in enumerate(expected):
        divisor = DIVISORS[index // len(TX_BYTES)]
        if index >= len(frames):
            wrong.append(f"divisor {divisor}: frame 0x{want:02x} not sent")
            continue
        value, misplaced = frames[index]
        if value != want:
            wrong.append(f"divisor {divisor}: frame decoded as {value!r}, sent 0x{want:02x}")
        if misplaced:
            wrong.append(f"divisor {divisor}: edges at {misplaced[:4]} cycles after the start edge, "
                         f"not multiples of {16 * divisor}")
    for index, (divisor, want) in enumerate(zip(DIVISORS, RX_BYTES)):
        got = _peek(dut, RESULT + 4 * index)
        if got != want:
            wrong.append(f"divisor {divisor}: received 0x{got:08x}, sent 0x{want:02x}")
    assert not wrong, "; ".join(wrong)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_uart_baud_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_uart_baud",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_uart_baud",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_uart_baud",
                "UART_BAUD_BUILD": str(build_dir.resolve()),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
