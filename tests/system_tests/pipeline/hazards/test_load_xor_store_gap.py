"""Verify a loaded register survives xor+gap before being stored back."""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from support import DATA_MEM_BASE, NOP, read_word, run_top, word_index


DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC


PROGRAM_WORDS = [
    0x100002B7,  # lui t0, 0x10000
    0x0002A303,  # lw t1, 0(t0)
    0x00100393,  # li t2, 1
    0x00000E93,  # li t4, 0
    0x00734333,  # xor t1, t1, t2  -> 0x71
    0x00000F13,  # li t5, 0
    0x0062A023,  # sw t1, 0(t0)
    0x00100E13,  # li t3, 1
    0x0FC28FA3,  # sb t3, 0xff(t0)
    0x0000006F,  # j .
]


async def _load_program(dut) -> None:
    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x120, 4):
        dut.unified_mem_inst.instr_ram[word_index(addr)].value = 0

    dut.unified_mem_inst.instr_ram[word_index(DATA_MEM_BASE)].value = 0x00000070


@cocotb.test()
async def test_loaded_xor_value_stores_after_gap(dut):
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
    for _ in range(180):
        await RisingEdge(dut.clk)
        done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Load-xor-store-gap test never completed"

    actual = read_word(dut, word_index(DATA_MEM_BASE)) & 0xFFFF_FFFF
    assert actual == 0x00000071, (
        f"Store lost xor result derived from load: expected=0x00000071 actual=0x{actual:08x}"
    )


def runCocotbTests():
    run_top("test_load_xor_store_gap", testcase="test_loaded_xor_value_stores_after_gap")


if __name__ == "__main__":
    runCocotbTests()
