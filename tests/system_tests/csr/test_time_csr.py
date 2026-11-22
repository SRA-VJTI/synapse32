"""The time CSR reads the CLINT's mtime."""

import os
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from support import INSTR_MEM_BASE, nop_image, peek, poke, run_top

MTIME_LO = 0x0200_BFF8

RESULT = 0x1000_0200
RESULT_WORDS = 16
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_030C

LATENCIES = [0, 2]  # MEM_LATENCY and FETCH_LATENCY
MTIME_START = 0x0000_0002_FFFF_FF00  # the low word carries 0x100 ticks later
BOUND = 0x100
POLL = 1024


def _read_time(lo_slot: int, hi_slot: int) -> str:
    """Read the 64-bit time with the RV32 idiom and store it at lo_slot(a7), hi_slot(a7)."""
    return f"""
1:
        csrr    a1, timeh
        csrr    a0, time
        csrr    t0, timeh
        bne     a1, t0, 1b
        sw      a0, {lo_slot}(a7)
        sw      a1, {hi_slot}(a7)
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        li      a7, {RESULT:#x}
        li      s0, {MTIME_LO:#x}

        sw      zero, 0(s0)
        li      t0, {MTIME_START >> 32:#x}
        sw      t0, 4(s0)
        li      t0, {MTIME_START & 0xFFFF_FFFF:#x}
        sw      t0, 0(s0)
        fence
{_read_time(0, 4)}

        li      t2, {POLL}
1:
        csrr    t0, timeh
        li      t1, {(MTIME_START >> 32) + 1:#x}
        beq     t0, t1, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
        sw      t0, 8(a7)

        csrwi   mcountinhibit, 1
        csrr    t1, cycle
        csrr    t2, time
        li      t5, 32
1:
        addi    t5, t5, -1
        bnez    t5, 1b
        csrr    t3, cycle
        csrr    t4, time
        csrwi   mcountinhibit, 0
        sub     t3, t3, t1
        sw      t3, 12(a7)
        sub     t4, t4, t2
        sw      t4, 16(a7)

        csrw    mcycle, zero
        csrw    mcycleh, zero
{_read_time(20, 24)}

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
    return Path(os.environ.get("TIME_BUILD", Path.cwd() / "build" / "time_csr"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "time.S"
    lds = build_dir / "time.ld"
    elf = build_dir / "time.elf"
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
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "time.bin")],
                   check=True)


def _name() -> str:
    return f"latency {os.environ['TIME_LATENCY']}"


@cocotb.test()
async def test_time_reads_mtime(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    data = (_build_dir() / "time.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for offset in range(0, 4 * RESULT_WORDS, 4):
        poke(dut, RESULT + offset, 0xDEAD_BEEF)
    for addr in (DONE_ADDR, TRAP_CAUSE, TRAP_EPC):
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
    r = [peek(dut, RESULT + 4 * i) for i in range(7)]
    first = r[0] | r[1] << 32
    after_mcycle = r[5] | r[6] << 32
    wrong = []
    if not MTIME_START <= first < MTIME_START + BOUND:
        wrong.append(f"time after writing mtime 0x{MTIME_START:016x}: 0x{first:016x}")
    if r[2] != (MTIME_START >> 32) + 1:
        wrong.append(f"timeh after the low word wrapped: 0x{r[2]:08x}, expected 0x{(MTIME_START >> 32) + 1:08x}")
    if r[3] != 0:
        wrong.append(f"cycle advanced by {r[3]} while mcountinhibit.CY was set")
    if not 0 < r[4] < 0x8000_0000:
        wrong.append(f"time advanced by 0x{r[4]:08x} while mcountinhibit.CY was set, expected a small positive count")
    if after_mcycle < first:
        wrong.append(f"time after writing mcycle 0: 0x{after_mcycle:016x}, below the earlier 0x{first:016x}")
    assert not wrong, f"{_name()}: " + "; ".join(wrong)


def runCocotbTests():
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_time_csr",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"TIME_BUILD": str(build_dir.resolve()), "TIME_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
