"""FENCE.I makes patched code visible, also while a line is being filled."""

import cocotb
from cocotb.clock import Clock

from icache_programs import (
    LATENCIES,
    RACE_CASES,
    REFETCH_LOG,
    REFETCH_PASSES,
    RESULT,
    assemble,
    build_name,
    check_finished,
    run_image,
    slots,
)
from support import build_directory, nop_image, peek, run_top


@cocotb.test()
async def test_fence_i_makes_patched_code_visible(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "patch.bin")
    check_finished(dut, done)
    times, values = slots(dut, 4)
    assert times[2] < times[1], (
        f"{build_name()}: the function took {times[1]} cycles cold and {times[2]} warm: it was not cached when "
        "it was patched")
    assert values[1:] == [1, 1, 2], (
        f"{build_name()}: the function returned {values[1:]}, expected [1, 1, 2]: after FENCE.I it ran the "
        "instruction from before the patch")
    refetched = [peek(dut, REFETCH_LOG + 4 * i) for i in range(REFETCH_PASSES)]
    assert refetched == list(range(1, REFETCH_PASSES + 1)), (
        f"{build_name()}: the instruction after FENCE.I returned {refetched} over {REFETCH_PASSES} passes, "
        f"expected {list(range(1, REFETCH_PASSES + 1))}: it ran the line cached on the previous pass")


@cocotb.test()
async def test_fence_i_during_a_line_fill(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "race.bin")
    check_finished(dut, done)
    got = [peek(dut, RESULT + 4 * c) for c in range(len(RACE_CASES))]
    expected = [c + 1 for c in range(len(RACE_CASES))]
    assert got == expected, (
        f"{build_name()}: patched instructions after FENCE.I returned {got}, expected {expected} (0 is the "
        "instruction from before the patch)")


def runCocotbTests():
    build_dir = build_directory("test_icache_fence_i")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_fence_i",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
