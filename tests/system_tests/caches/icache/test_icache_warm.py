"""Warm code runs one instruction per cycle."""

import cocotb
from cocotb.clock import Clock

from icache_programs import LATENCIES, RESULT, WARM_BLOCK, assemble, build_name, check_finished, run_image
from support import build_directory, nop_image, peek, run_top


@cocotb.test()
async def test_warm_code_runs_one_instruction_per_cycle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "warm.bin")
    check_finished(dut, done)
    cold, warm = peek(dut, RESULT), peek(dut, RESULT + 4)
    assert cold > WARM_BLOCK, (
        f"{build_name()}: the first pass over {WARM_BLOCK} instructions took {cold} cycles, so its fetches never "
        "missed: the code was not fetched through a cache")
    assert warm == WARM_BLOCK, (
        f"{build_name()}: the second pass over {WARM_BLOCK} instructions took {warm} cycles, not one per "
        "instruction: warm code still waited for fetch")


def runCocotbTests():
    build_dir = build_directory("test_icache_warm")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_warm",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
