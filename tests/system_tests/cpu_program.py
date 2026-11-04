"""Run a list of instruction words as a program on top and wait until it parks."""

import os
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
NOP = 0x0000_0013
PARK = 0x0000_006F  # jal x0, 0


def _parks(word: int) -> bool:
    """jal x0 to itself or backwards: the end of a test program."""
    return (word & 0xFFF) == 0x06F and (word >> 31 or word >> 12 == 0)


async def run_program(dut, instr_mem, done=None, max_cycles=5000):
    """Load instr_mem at INSTR_MEM_BASE, run it until done(dut) or a parking jump retires."""
    program = list(instr_mem) + [PARK]
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for index, word in enumerate(program):
        dut.unified_mem_inst.instr_ram[index].value = word
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    cpu = dut.cpu_inst
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if done is not None:
            if done(dut):
                break
        elif int(cpu.instret_increment.value):
            index = (int(cpu.id_ex_inst0_pc_out.value) - INSTR_MEM_BASE) // 4
            if 0 <= index < len(program) and _parks(program[index]):
                break
    else:
        raise AssertionError(f"the program did not finish within {max_cycles} cycles")
    # Older instructions are still in MEM and WB.
    await ClockCycles(dut.clk, 15)


def run_tests(module, tests):
    """Build top once for module, then run each cocotb test in its own simulation."""
    root = Path.cwd()
    while not (root / "rtl").exists():
        if root.parent == root:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root = root.parent
    rtl_dir = root / "rtl"
    sim_build = Path.cwd() / "sim_build" / f"sim_build_{module}"
    if sim_build.exists():
        shutil.rmtree(sim_build)
    waves = os.getenv("WAVES", "0") == "1"
    for test_name in tests:
        plus_args = []
        if waves:
            waveform_dir = Path.cwd() / "waveforms"
            waveform_dir.mkdir(exist_ok=True)
            plus_args = [f"+dumpfile={waveform_dir / f'{test_name}.fst'}"]
        run(
            verilog_sources=[str(p) for p in sorted(rtl_dir.rglob("*.v"))],
            toplevel="top",
            module=module,
            testcase=test_name,
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            sim_build=str(sim_build),
            waves=waves,
            plus_args=plus_args,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": module,
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": module,
            },
        )
