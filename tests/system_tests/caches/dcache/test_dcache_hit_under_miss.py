"""A store that misses does not stop later hits."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import (
    BUILDS,
    DEFAULT_MSHRS,
    HUM_LOADS,
    assemble,
    build_name,
    check_finished,
    Coverage,
    require_cache,
    results,
    run_image,
)
from support import build_directory, nop_image, run_top


@cocotb.test()
async def test_a_store_miss_does_not_stop_hits(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await run_image(dut, "hum.bin", coverage=coverage)
    check_finished(dut, done)
    load_miss, mixed = results(dut, 4)[2:]
    assert load_miss > 2, f"{build_name()}: a load of a cold line took {load_miss} cycles, so it did not miss"
    assert mixed < load_miss + HUM_LOADS, (
        f"{build_name()}: a store miss and {HUM_LOADS} loads of warm lines took {mixed} cycles; a load miss takes "
        f"{load_miss}, so the loads waited for the store's fill")
    require_cache(dut)
    assert coverage.hits_during_fill > 0, f"{build_name()}: no load hit while a fill was running"


def runCocotbTests():
    build_dir = build_directory("test_dcache_hit_under_miss")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_hit_under_miss",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
