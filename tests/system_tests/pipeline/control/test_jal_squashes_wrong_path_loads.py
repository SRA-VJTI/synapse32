"""Verify that a direct JAL fully redirects before dependent fall-through loads.

The instructions after the call load words that the callee overwrites. If those
loads are allowed to retire before the jump takes effect, the final XOR result
will reflect stale pre-call memory.
"""


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from support import DATA_MEM_BASE, NOP, read_word, run_top, word_index


DONE_ADDR = DATA_MEM_BASE + 0xFF
DONE_WORD_ADDR = DONE_ADDR & 0xFFFF_FFFC


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


async def _load_program(dut) -> None:
    for idx in range(len(PROGRAM_WORDS) + 16):
        word = PROGRAM_WORDS[idx] if idx < len(PROGRAM_WORDS) else NOP
        dut.unified_mem_inst.instr_ram[idx].value = word

    for addr in range(DATA_MEM_BASE, DATA_MEM_BASE + 0x120, 4):
        dut.unified_mem_inst.instr_ram[word_index(addr)].value = 0

    # Seed old values that must be replaced by the callee before the caller's
    # fall-through loads observe them.
    dut.unified_mem_inst.instr_ram[word_index(DATA_MEM_BASE + 0x00)].value = 0xAAAAAAAA
    dut.unified_mem_inst.instr_ram[word_index(DATA_MEM_BASE + 0x04)].value = 0x55555555


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
        done_word = read_word(dut, word_index(DONE_WORD_ADDR)) & 0xFFFF_FFFF
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
        actual = read_word(dut, word_index(addr)) & 0xFFFF_FFFF
        assert actual == value, (
            f"Memory mismatch at 0x{addr:08x}: expected=0x{value:08x} actual=0x{actual:08x}"
        )


def runCocotbTests():
    run_top("test_jal_squashes_wrong_path_loads", testcase="test_direct_jal_flushes_fallthrough_loads")


if __name__ == "__main__":
    runCocotbTests()
