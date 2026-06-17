"""Verify data-path LW reads from instruction-memory space.

The Linux caller loads round constants as data from the instruction-memory
region. This test checks that path directly at a high physical address while
the CPU executes from instruction memory normally.
"""

import os
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000
DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC
TABLE_ADDR = 0x80DC_2648

NOP = 0x00000013

PROGRAM_WORDS = [
    0x100002B7,  # lui t0, 0x10000
    0x80DC24B7,  # lui s1, 0x80dc2
    0x64848493,  # addi s1, s1, 0x648
    0x0004A303,  # lw t1, 0(s1)
    0x0044A383,  # lw t2, 4(s1)
    0x00734E33,  # xor t3, t1, t2
    0x0062A023,  # sw t1, 0(t0)
    0x0072A223,  # sw t2, 4(t0)
    0x01C2A423,  # sw t3, 8(t0)
    0x00848493,  # addi s1, s1, 8
    0x0004AE83,  # lw t4, 0(s1)
    0x0044AF03,  # lw t5, 4(s1)
    0x01EECFB3,  # xor t6, t4, t5
    0x01D2A623,  # sw t4, 12(t0)
    0x01E2A823,  # sw t5, 16(t0)
    0x01F2AA23,  # sw t6, 20(t0)
    0x00100E93,  # li t4, 1
    0x0FD28FA3,  # sb t4, 0xff(t0)
    0x0000006F,  # j .
]

TABLE_WORDS = [
    0x11223344,
    0x55667788,
    0xAABBCCDD,
    0x12345678,
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < (INSTR_MEM_BASE + INSTR_MEM_SIZE):
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address for test: 0x{addr:08x}")


async def _load_program(dut) -> None:
    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for idx, word in enumerate(TABLE_WORDS):
        dut.unified_mem_inst.instr_ram[_phys_word_index(TABLE_ADDR) + idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x140, 4):
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = 0


@cocotb.test()
async def test_load_data_from_instruction_memory_region(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1

    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    await _load_program(dut)
    dut.rst.value = 0

    done = False
    for _ in range(220):
        await RisingEdge(dut.clk)
        done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Instruction-memory data-load test never completed"

    expected = {
        DATA_MEM_BASE + 0x00: 0x11223344,
        DATA_MEM_BASE + 0x04: 0x55667788,
        DATA_MEM_BASE + 0x08: 0x444444CC,
        DATA_MEM_BASE + 0x0C: 0xAABBCCDD,
        DATA_MEM_BASE + 0x10: 0x12345678,
        DATA_MEM_BASE + 0x14: 0xB88F9AA5,
        DONE_WORD_ADDR: 0x01000000,
    }

    for addr, value in expected.items():
        actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF
        assert actual == value, (
            f"Memory mismatch at 0x{addr:08x}: expected=0x{value:08x} actual=0x{actual:08x}"
        )


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    incl_dir = rtl_dir / "include"

    sources = []
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith((".v", ".sv")):
                sources.append(os.path.join(root, file))

    sim_build = Path.cwd() / "sim_build" / "sim_build_instrmem_data_load"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_instrmem_data_load",
        testcase="test_load_data_from_instruction_memory_region",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
