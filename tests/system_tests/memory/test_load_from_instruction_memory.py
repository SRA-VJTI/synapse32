"""Verify data-path LW reads from instruction-memory space.

The Linux caller loads round constants as data from the instruction-memory
region. This test checks that path directly at a high physical address while
the CPU executes from instruction memory normally.
"""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from support import DATA_MEM_BASE, NOP, read_word, run_top, word_index


DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC
TABLE_ADDR = 0x80DC_2648


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


async def _load_program(dut) -> None:
    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for idx, word in enumerate(TABLE_WORDS):
        dut.unified_mem_inst.instr_ram[word_index(TABLE_ADDR) + idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x140, 4):
        dut.unified_mem_inst.instr_ram[word_index(addr)].value = 0


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
        done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
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
        actual = read_word(dut, word_index(addr)) & 0xFFFF_FFFF
        assert actual == value, (
            f"Memory mismatch at 0x{addr:08x}: expected=0x{value:08x} actual=0x{actual:08x}"
        )


def runCocotbTests():
    run_top("test_load_from_instruction_memory", testcase="test_load_data_from_instruction_memory_region")


if __name__ == "__main__":
    runCocotbTests()
