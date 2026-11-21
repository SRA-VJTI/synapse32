"""Exercise ordinary far calls encoded as AUIPC+JALR plus RET.

Linux relies heavily on this pattern for out-of-range calls. The existing
control-hazard coverage does not really touch it.
"""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from support import DATA_MEM_BASE, INSTR_MEM_BASE, NOP, read_word, run_top, word_index


DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC

STUB1_ADDR = INSTR_MEM_BASE + 0x1000
STUB2_ADDR = STUB1_ADDR + 0x0C

MAIN_WORDS = [
    0x100002B7,  # li t0, 0x10000000
    0x00001097,  # auipc ra, %pcrel_hi(stub1)
    0xFFC080E7,  # jalr ra, %pcrel_lo(stub1)(ra)
    0x05500313,  # li t1, 0x55
    0x0062A023,  # sw t1, 0(t0)
    0x00001097,  # auipc ra, %pcrel_hi(stub2)
    0xFF8080E7,  # jalr ra, %pcrel_lo(stub2)(ra)
    0x06600393,  # li t2, 0x66
    0x0072A223,  # sw t2, 4(t0)
    0x0012A423,  # sw ra, 8(t0)
    0x00100E13,  # li t3, 1
    0x0FC28FA3,  # sb t3, 0xff(t0)
    0x0000006F,  # j .
]

STUB1_WORDS = [
    0x07700E93,  # li t4, 0x77
    0x01D2A823,  # sw t4, 16(t0)
    0x00008067,  # ret
]

STUB2_WORDS = [
    0x08800F13,  # li t5, 0x88
    0x01E2AA23,  # sw t5, 20(t0)
    0x00008067,  # ret
]


async def _load_program(dut) -> None:
    for idx in range(len(MAIN_WORDS) + 16):
        word = MAIN_WORDS[idx] if idx < len(MAIN_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    stub1_base = word_index(STUB1_ADDR)
    for idx, word in enumerate(STUB1_WORDS):
        dut.unified_mem_inst.instr_ram[stub1_base + idx].value = word

    stub2_base = word_index(STUB2_ADDR)
    for idx, word in enumerate(STUB2_WORDS):
        dut.unified_mem_inst.instr_ram[stub2_base + idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x120, 4):
        dut.unified_mem_inst.instr_ram[word_index(addr)].value = 0


@cocotb.test()
async def test_auipc_jalr_far_calls_and_ret(dut):
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
        done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
        if ((done_word >> 24) & 0xFF) == 1:
            done = True
            break

    assert done, "Far-call test never completed"

    expected = {
        DATA_MEM_BASE + 0x00: 0x00000055,
        DATA_MEM_BASE + 0x04: 0x00000066,
        DATA_MEM_BASE + 0x08: 0x8000001C,
        DATA_MEM_BASE + 0x10: 0x00000077,
        DATA_MEM_BASE + 0x14: 0x00000088,
        DONE_WORD_ADDR: 0x01000000,
    }

    for addr, value in expected.items():
        actual = read_word(dut, word_index(addr)) & 0xFFFF_FFFF
        assert actual == value, (
            f"Memory mismatch at 0x{addr:08x}: expected=0x{value:08x} actual=0x{actual:08x}"
        )


def runCocotbTests():
    run_top("test_call_flow", testcase="test_auipc_jalr_far_calls_and_ret")


if __name__ == "__main__":
    runCocotbTests()
