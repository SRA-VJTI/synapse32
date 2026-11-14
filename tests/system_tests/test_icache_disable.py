"""With ICACHE_ENABLE 0 every instruction is fetched from the fetch port; the default build caches the loop."""

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from cpu_program import run_program, run_tests

LATENCY = 2
LOOPS = 20
STEP = 3


def _addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def _bne(rs1, rs2, offset):
    imm = offset & 0x1FFF
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | \
        (0b001 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63


PROGRAM = [
    _addi(5, 0, LOOPS),
    _addi(6, 0, 0),
    _addi(6, 6, STEP),  # loop
    _addi(5, 5, -1),
    _bne(5, 0, -8),
]


async def _run(dut):
    """Run the loop; return (fetch-port grants, retired instructions)."""
    grants = 0

    async def count():
        nonlocal grants
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.instr_mem_req.value) and int(dut.instr_mem_gnt.value):
                grants += 1

    cocotb.start_soon(count())
    await run_program(dut, PROGRAM)
    sum_value = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    assert sum_value == LOOPS * STEP, f"x6 = {sum_value}, expected {LOOPS * STEP}"
    return grants, int(dut.cpu_inst.csr_file_inst.instret_counter.value)


@cocotb.test()
async def test_disabled_fetches_every_instruction(dut):
    """No cache: at least one fetch-port grant per retired instruction."""
    grants, retired = await _run(dut)
    assert grants >= retired, f"{grants} fetch grants for {retired} retired instructions: something cached them"


@cocotb.test()
async def test_enabled_caches_the_loop(dut):
    """Control: the default build fetches the loop's line once."""
    grants, retired = await _run(dut)
    assert grants < retired // 2, f"{grants} fetch grants for {retired} retired instructions: the loop was not cached"


def runCocotbTests():
    latency = {"MEM_LATENCY": LATENCY, "FETCH_LATENCY": LATENCY}
    run_tests("test_icache_disable", ["test_disabled_fetches_every_instruction"],
              parameters={**latency, "ICACHE_ENABLE": 0})
    run_tests("test_icache_disable", ["test_enabled_caches_the_loop"], parameters=latency)


if __name__ == "__main__":
    runCocotbTests()
