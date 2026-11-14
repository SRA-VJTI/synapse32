"""With DCACHE_ENABLE 0 every store reaches the data port; the default build keeps them in the write-back cache."""

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from cpu_program import run_program, run_tests
from memory_view import read_word

LATENCY = 2
LOOPS = 16
DATA_MEM_BASE = 0x1000_0000
INSTR_MEM_SIZE = 0x0400_0000


def _lui(rd, value):
    return (value & 0xFFFF_F000) | (rd << 7) | 0x37


def _addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def _add(rd, rs1, rs2):
    return (rs2 << 20) | (rs1 << 15) | (rd << 7) | 0x33


def _sw(rs2, rs1):
    return (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | 0x23


def _lw(rd, rs1):
    return (rs1 << 15) | (0b010 << 12) | (rd << 7) | 0x03


def _bne(rs1, rs2, offset):
    imm = offset & 0x1FFF
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | \
        (0b001 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63


# Each iteration stores the counter to one RAM word, loads it back and adds it up.
PROGRAM = [
    _lui(1, DATA_MEM_BASE),
    _addi(5, 0, LOOPS),
    _addi(6, 0, 0),
    _addi(8, 0, 0),
    _sw(6, 1),  # loop
    _lw(7, 1),
    _add(8, 8, 7),
    _addi(6, 6, 1),
    _addi(5, 5, -1),
    _bne(5, 0, -20),
]


async def _run(dut):
    """Run the loop; return the number of writes granted on the data port."""
    writes = 0

    async def count():
        nonlocal writes
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.data_mem_req.value) and int(dut.data_mem_gnt.value) and int(dut.data_mem_we.value):
                writes += 1

    cocotb.start_soon(count())
    await run_program(dut, PROGRAM)
    total = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    assert total == LOOPS * (LOOPS - 1) // 2, f"x8 = {total}, expected {LOOPS * (LOOPS - 1) // 2}"
    stored = read_word(dut, INSTR_MEM_SIZE // 4)
    assert stored == LOOPS - 1, f"memory holds {stored}, expected {LOOPS - 1}"
    return writes


@cocotb.test()
async def test_disabled_writes_every_store(dut):
    """No cache: each store is a write on the data port."""
    writes = await _run(dut)
    assert writes >= LOOPS, f"{writes} data-port writes for {LOOPS} stores: something cached them"


@cocotb.test()
async def test_enabled_keeps_the_stores(dut):
    """Control: the write-back cache keeps the stores."""
    writes = await _run(dut)
    assert writes < LOOPS // 2, f"{writes} data-port writes for {LOOPS} stores: the stores were not cached"


def runCocotbTests():
    latency = {"MEM_LATENCY": LATENCY, "FETCH_LATENCY": LATENCY}
    run_tests("test_dcache_disable", ["test_disabled_writes_every_store"],
              parameters={**latency, "DCACHE_ENABLE": 0})
    run_tests("test_dcache_disable", ["test_enabled_keeps_the_stores"], parameters=latency)


if __name__ == "__main__":
    runCocotbTests()
