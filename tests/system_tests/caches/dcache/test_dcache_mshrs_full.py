"""Misses beyond the MSHRs wait for a free one."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import (
    BUILDS,
    DEFAULT_MSHRS,
    FULL_COUNT,
    SWEEP_LATENCY,
    assemble,
    build_latency,
    build_mshrs,
    build_name,
    check_finished,
    Coverage,
    require_cache,
    results,
    run_image,
)
from support import build_directory, mshr_slots, nop_image, run_top


@cocotb.test()
async def test_misses_beyond_the_mshrs_wait(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await run_image(dut, "full.bin", coverage=coverage)
    check_finished(dut, done)
    got = results(dut, 2 * FULL_COUNT)
    expected = 2 * [0x100 + i for i in range(FULL_COUNT)]
    assert got == expected, f"{build_name()}: lines read back {[hex(v) for v in got]}, expected {[hex(v) for v in expected]}"
    cache = require_cache(dut)
    mshrs = mshr_slots(cache)
    assert mshrs == build_mshrs(), f"{build_name()}: the cache has {mshrs} MSHRs"
    if build_latency() == SWEEP_LATENCY:
        assert coverage.max_mshrs == mshrs, (
            f"{build_name()}: at most {coverage.max_mshrs} of {mshrs} MSHRs were in use, so no miss waited for one")
        assert int(cache.stat_mshr_full_cycles.value) > 0, f"{build_name()}: no miss found the MSHRs full"


def runCocotbTests():
    build_dir = build_directory("test_dcache_mshrs_full")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_mshrs_full",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
