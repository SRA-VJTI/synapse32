"""Verify store data forwards from the immediately preceding ALU result."""

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

NOP = 0x00000013

PROGRAM_WORDS = [
    0x100002B7,  # lui t0, 0x10000
    0x07000313,  # li t1, 0x70
    0x00100393,  # li t2, 1
    0x00734333,  # xor t1, t1, t2  -> 0x71
    0x0062A023,  # sw t1, 0(t0)
    0x00100E13,  # li t3, 1
    0x0FC28FA3,  # sb t3, 0xff(t0)
    0x0000006F,  # j .
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

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x120, 4):
        dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = 0


@cocotb.test()
async def test_store_data_forwards_from_prior_alu_result(dut):
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
    for _ in range(160):
        await RisingEdge(dut.clk)
        done_word = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DONE_WORD_ADDR)].value) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Store-data forwarding test never completed"

    actual = int(dut.unified_mem_inst.instr_ram[_phys_word_index(DATA_MEM_BASE)].value) & 0xFFFF_FFFF
    assert actual == 0x00000071, (
        f"Store consumed stale rs2 value: expected=0x00000071 actual=0x{actual:08x}"
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_store_data_forwarding"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_store_data_forwarding",
        testcase="test_store_data_forwards_from_prior_alu_result",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
