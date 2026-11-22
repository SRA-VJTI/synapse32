"""Verify unified_mem writes bytes into the correct word across word boundaries."""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from support import INSTR_MEM_BASE, run_unit


@cocotb.test()
async def test_cross_word_store_updates_next_word(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.clk.value = 0
    dut.instr_addr.value = 0
    dut.instr_addr_p2.value = INSTR_MEM_BASE + 3
    dut.data_wr_req.value = 1
    dut.data_rd_en.value = 0
    dut.wr_en.value = 0
    dut.write_byte_enable.value = 0
    dut.wr_data.value = 0
    dut.load_type.value = 0
    dut.pte_wr_en_a.value = 0
    dut.pte_wr_addr_a.value = 0
    dut.pte_wr_value_a.value = 0
    dut.pte_wr_en_b.value = 0
    dut.pte_wr_addr_b.value = 0
    dut.pte_wr_value_b.value = 0
    dut.pte_rd_addr_a.value = 0
    dut.pte_rd_addr_b.value = 0
    dut.pte_rd_addr_c.value = 0
    dut.pte_rd_addr_d.value = 0

    dut.instr_ram[0].value = 0
    dut.instr_ram[1].value = 0

    await RisingEdge(dut.clk)

    # Simulate a 2-byte store starting at byte offset 3:
    # low byte should land in word 0 byte lane 3, high byte in word 1 byte lane 0.
    dut.wr_en.value = 1
    dut.write_byte_enable.value = 0b0011
    dut.wr_data.value = 0x0000_BBAA

    await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    dut.write_byte_enable.value = 0
    dut.wr_data.value = 0

    await RisingEdge(dut.clk)

    word0 = int(dut.instr_ram[0].value) & 0xFFFF_FFFF
    word1 = int(dut.instr_ram[1].value) & 0xFFFF_FFFF

    assert word0 == 0xAA00_0000, f"expected low byte in first word, got 0x{word0:08x}"
    assert word1 == 0x0000_00BB, f"expected high byte in second word, got 0x{word1:08x}"


def runCocotbTests():
    run_unit("unified_mem", "test_unified_mem_cross_word_store", ["rtl/unified_mem.v"],
             testcase="test_cross_word_store_updates_next_word", compile_args=["-Wno-WIDTHTRUNC"])

if __name__ == "__main__":
    runCocotbTests()
