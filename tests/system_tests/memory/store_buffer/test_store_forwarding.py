"""A load fully covered by the last buffered store to its word takes its bytes from the store buffer."""

import os
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from support import INSTR_MEM_BASE, nop_image, peek, poke, run_top

UART_SCR = 0x2000_001C

RESULT = 0x1000_0200
BASELINE = 0x1000_0400
WARM = 0x1000_0410
WORDS = 0x1000_1000
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_030C

LATENCIES = [2, 4]  # MEM_LATENCY and FETCH_LATENCY; the device writes hold the port long enough
X, Y, Z = 0x89AB_CDEF, 0x9C, 0xF00D
FORWARD_CYCLES = 1  # a forward is registered: one cycle more than a warm hit

# (stores (op, offset, value), load (op, offset), forwarded)
CASES = [
    ([("sw", 0, X)], ("lw", 0), True),
    ([("sw", 0, X)], ("lb", 0), True),
    ([("sw", 0, X)], ("lb", 1), True),
    ([("sw", 0, X)], ("lbu", 2), True),
    ([("sw", 0, X)], ("lb", 3), True),
    ([("sw", 0, X)], ("lh", 0), True),
    ([("sw", 0, X)], ("lhu", 2), True),
    ([("sw", 0, X)], ("lh", 2), True),
    ([("sb", 2, Y)], ("lbu", 2), True),
    ([("sh", 2, Z)], ("lh", 2), True),
    ([("sb", 1, Y), ("sw", 0, X)], ("lw", 0), True),
    ([("sw", 0, X), ("sb", 1, Y)], ("lbu", 1), True),
    ([("sb", 1, Y)], ("lw", 0), False),
    ([("sh", 0, Z)], ("lw", 0), False),
    ([("sb", 0, Y)], ("lh", 0), False),
    ([("sw", 0, X), ("sb", 1, Y)], ("lw", 0), False),
    ([("sw", 0, X)], ("lw", 4), False),
]
SIZES = {"sb": 1, "sh": 2, "sw": 4, "lb": 1, "lbu": 1, "lh": 2, "lhu": 2, "lw": 4}


def _word(index: int) -> int:
    return WORDS + 16 * index


def _initial(index: int, offset: int) -> int:
    return (0x1122_3344 + 0x0101_0101 * index + offset) & 0xFFFF_FFFF


def _expected(stores, load, index: int) -> int:
    memory = bytearray()
    for offset in (0, 4):
        memory += _initial(index, offset).to_bytes(4, "little")
    for op, offset, value in stores:
        memory[offset:offset + SIZES[op]] = (value & ((1 << (8 * SIZES[op])) - 1)).to_bytes(SIZES[op], "little")
    op, offset = load
    value = int.from_bytes(memory[offset:offset + SIZES[op]], "little")
    if op in ("lb", "lh") and value >> (8 * SIZES[op] - 1):
        value -= 1 << (8 * SIZES[op])
    return value & 0xFFFF_FFFF


def _case(index: int, stores, load) -> str:
    body = "".join(f"        li      t0, {value:#x}\n        {op}      t0, {offset}(s1)\n"
                   for op, offset, value in stores)
    op, offset = load
    return f"""
        fence
        li      s1, {_word(index):#x}
        li      t0, 0x5A
        sw      t0, 0(s0)               # UART scratch register, twice: holds the data port
        sw      t0, 0(s0)
{body}        csrr    t5, mcycle
        {op}      t1, {offset}(s1)
        csrr    t4, mcycle
        sub     t4, t4, t5
        sw      t1, {8 * index}(a7)
        sw      t4, {8 * index + 4}(a7)
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a7, {RESULT:#x}
        li      s0, {UART_SCR:#x}
        li      s2, {WARM:#x}
        li      s3, 2                   # the second pass runs with code and data cached
pass:
        lw      t1, 0(s2)
        fence
        csrr    t5, mcycle
        lw      t1, 0(s2)
        csrr    t4, mcycle
        sub     t4, t4, t5
        li      t0, {BASELINE:#x}
        sw      t4, 0(t0)
{"".join(_case(i, stores, load) for i, (stores, load, _) in enumerate(CASES))}

        addi    s3, s3, -1
        bnez    s3, pass
        fence
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


def _build_dir() -> Path:
    return Path(os.environ.get("FORWARD_BUILD", Path.cwd() / "build" / "store_forwarding"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "fwd.S"
    lds = build_dir / "fwd.ld"
    elf = build_dir / "fwd.elf"
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
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "fwd.bin")],
                   check=True)


def _name() -> str:
    return f"latency {os.environ['FORWARD_LATENCY']}"


def _describe(stores, load) -> str:
    return ", ".join(f"{op} {offset}" for op, offset, _ in stores) + f" then {load[0]} {load[1]}"


@cocotb.test()
async def test_covered_loads_take_bytes_from_the_buffer(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    data = (_build_dir() / "fwd.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for index in range(len(CASES)):
        for offset in (0, 4):
            poke(dut, _word(index) + offset, _initial(index, offset))
        poke(dut, RESULT + 8 * index, 0xDEAD_BEEF)
    for addr in (BASELINE, WARM, DONE_ADDR, TRAP_CAUSE, TRAP_EPC):
        poke(dut, addr, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if peek(dut, DONE_ADDR) == DONE_VALUE:
            done = True
            break

    assert done, f"{_name()}: the program did not finish"
    cause = peek(dut, TRAP_CAUSE)
    assert cause == 0, f"{_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{peek(dut, TRAP_EPC):08x}"
    baseline = peek(dut, BASELINE)
    wrong = []
    for index, (stores, load, forwarded) in enumerate(CASES):
        got = peek(dut, RESULT + 8 * index)
        cycles = peek(dut, RESULT + 8 * index + 4)
        want = _expected(stores, load, index)
        if got != want:
            wrong.append(f"{_describe(stores, load)}: loaded 0x{got:08x}, expected 0x{want:08x}")
        if forwarded and cycles != baseline + FORWARD_CYCLES:
            wrong.append(f"{_describe(stores, load)}: load took {cycles} cycles, a warm hit {baseline} "
                         f"(a forward is expected to take {FORWARD_CYCLES} more)")
    assert not wrong, f"{_name()}: " + "; ".join(wrong)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_store_forwarding",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"FORWARD_BUILD": str(build_dir.resolve()), "FORWARD_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
