"""Verify a branch sees the result of the immediately preceding ADDI."""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from support import DATA_MEM_BASE, NOP, read_word, run_top, word_index


DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC


PROGRAM_WORDS = [
    0x00000493,  # li s1, 0
    0x00800B13,  # li s6, 8
    0x00848493,  # addi s1, s1, 8
    0x01649463,  # bne s1, s6, +8  -> fail path if stale s1 is seen
    0x00100E13,  # li t3, 1         -> pass marker
    0x0FC28FA3,  # sb t3, 0xff(t0)  -> pass writes 1
    0x00200E13,  # li t3, 2         -> fail marker
    0x0FC28FA3,  # sb t3, 0xff(t0)  -> fail writes 2
    0x0000006F,  # j .
]


async def _load_program(dut) -> None:
    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x120, 4):
        dut.unified_mem_inst.instr_ram[word_index(addr)].value = 0

    dut.cpu_inst.rf_inst0.register_file[5].value = DATA_MEM_BASE  # t0


@cocotb.test()
async def test_branch_uses_fresh_addi_result(dut):
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
    for _ in range(120):
        await RisingEdge(dut.clk)
        done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) in (1, 2):
            done = True
            break

    assert done, "Branch-after-addi test never completed"

    done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
    done_byte = (done_word >> 24) & 0xFF
    assert done_byte == 1, f"Branch used stale ADDI result and took fail path (marker={done_byte})"


def runCocotbTests():
    run_top("test_branch_after_addi", testcase="test_branch_uses_fresh_addi_result")


if __name__ == "__main__":
    runCocotbTests()
