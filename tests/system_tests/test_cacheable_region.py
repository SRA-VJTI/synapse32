"""Outside the cacheable regions is a device: uncached and never forwarded from the store buffer.

top is built with the data RAM's cacheable region halved. unified_mem still backs the old range above it,
standing in for a device the SoC maps there.
"""

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from cpu_program import run_program, run_tests

INSTR_RAM_SIZE = 0x0400_0000
DATA_RAM_BASE = 0x1000_0000
DATA_RAM_SIZE = 0x0008_0000
DEVICE = DATA_RAM_BASE + DATA_RAM_SIZE
RAM = DATA_RAM_BASE
UART_SCR = 0x2000_001C


def _lui(rd, value):
    return (value & 0xFFFF_F000) | (rd << 7) | 0x37


def _addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def _sw(rs2, rs1, imm=0):
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | ((imm & 0x1F) << 7) | 0x23


def _lw(rd, rs1, imm=0):
    return (imm << 20) | (rs1 << 15) | (0b010 << 12) | (rd << 7) | 0x03


async def _watch(dut, counts):
    """Count dcache lookups and store-to-load forwards by word address."""
    cpu = dut.cpu_inst
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(cpu.dcache_inst.lookup.value):
            word = int(cpu.dcache_inst.addr.value) & ~3
            counts["lookup", word] = counts.get(("lookup", word), 0) + 1
        if int(cpu.store_buf_forward_go.value):
            word = int(cpu.phys_data_addr.value) & ~3
            counts["forward", word] = counts.get(("forward", word), 0) + 1


@cocotb.test()
async def test_device_outside_ram_regions(dut):
    """A store queued behind a UART write, then a load of its word: only the RAM word may be forwarded."""
    instr_mem = [
        _lui(1, DEVICE),
        _lui(2, RAM),
        _lui(7, UART_SCR),
        _addi(3, 0, 0x5A),
        _addi(5, 0, 0x3C),
        _sw(3, 7, UART_SCR & 0xFFF),  # holds the data port, so the next store waits in the buffer
        _sw(3, 1),
        _lw(4, 1),
        _sw(5, 7, UART_SCR & 0xFFF),
        _sw(5, 2),
        _lw(6, 2),
    ]
    counts = {}
    cocotb.start_soon(_watch(dut, counts))
    await run_program(dut, instr_mem)

    regs = dut.cpu_inst.rf_inst0.register_file
    assert int(regs[4].value) == 0x5A, f"device load returned {int(regs[4].value):#x}"
    assert int(regs[6].value) == 0x3C, f"RAM load returned {int(regs[6].value):#x}"
    assert counts.get(("lookup", RAM), 0), "the dcache never looked up the RAM word, so the check proves nothing"
    assert counts.get(("forward", RAM), 0), "the RAM word was not forwarded, so the check proves nothing"
    assert not counts.get(("lookup", DEVICE), 0), f"the dcache looked up the device word {DEVICE:#x}"
    assert not counts.get(("forward", DEVICE), 0), f"a buffered store was forwarded from the device word {DEVICE:#x}"


def runCocotbTests():
    run_tests("test_cacheable_region", ["test_device_outside_ram_regions"],
              parameters={"MEM_LATENCY": 2, "CACHEABLE_SIZES": f"64'h{DATA_RAM_SIZE:08x}{INSTR_RAM_SIZE:08x}"})


if __name__ == "__main__":
    runCocotbTests()
