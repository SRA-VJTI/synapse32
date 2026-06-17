"""Verify that a direct JAL fully redirects before dependent fall-through loads.

The instructions after the call load words that the callee overwrites. If those
loads are allowed to retire before the jump takes effect, the final XOR result
will reflect stale pre-call memory.
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

NOP = 0x00000013

PROGRAM_WORDS = [
    0x100002B7,  # lui t0, 0x10000
    0x020000EF,  # jal ra, stub
    0x0002A303,  # lw t1, 0(t0)
    0x0042A383,  # lw t2, 4(t0)
    0x00734E33,  # xor t3, t1, t2
    0x01C2A423,  # sw t3, 8(t0)
    0x00100E93,  # li t4, 1
    0x0FD28FA3,  # sb t4, 0xff(t0)
    0x0000006F,  # j .
    0x01100E93,  # stub: li t4, 17
    0x01D2A023,  # sw t4, 0(t0)
    0x02200F13,  # li t5, 34
    0x01E2A223,  # sw t5, 4(t0)
    0x00008067,  # ret
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

    # Seed old values that must be replaced by the callee before the caller's
    # fall-through loads observe them.
    dut.unified_mem_inst.instr_ram[_phys_word_index(DATA_MEM_BASE + 0x00)].value = 0xAAAAAAAA
    dut.unified_mem_inst.instr_ram[_phys_word_index(DATA_MEM_BASE + 0x04)].value = 0x55555555


@cocotb.test()
async def test_direct_jal_flushes_fallthrough_loads(dut):
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

    assert done, "Direct-JAL flush test never completed"

    expected = {
        DATA_MEM_BASE + 0x00: 0x00000011,
        DATA_MEM_BASE + 0x04: 0x00000022,
        DATA_MEM_BASE + 0x08: 0x00000033,
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

    sim_build = Path.cwd() / "sim_build" / "sim_build_jal_flush"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_jal_flush",
        testcase="test_direct_jal_flushes_fallthrough_loads",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
