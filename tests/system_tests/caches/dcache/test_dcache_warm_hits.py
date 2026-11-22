"""Loads and stores that hit a warm line cost one cycle."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import BLOCK, BUILDS, DEFAULT_MSHRS, assemble, build_name, check_finished, results, run_image
from support import build_directory, nop_image, run_top


@cocotb.test()
async def test_warm_loads_and_stores_cost_one_cycle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "timing.bin")
    check_finished(dut, done)
    cold_loads, cold_stores, warm_loads, warm_stores = results(dut, 4)
    assert cold_loads > BLOCK, (
        f"{build_name()}: {BLOCK} loads of four cold lines took {cold_loads} cycles, so they never missed: the "
        "loads were not served by a cache")
    assert warm_loads == BLOCK, (
        f"{build_name()}: {BLOCK} loads of warm lines took {warm_loads} cycles, not one each")
    assert warm_stores == BLOCK, (
        f"{build_name()}: {BLOCK} stores to warm lines took {warm_stores} cycles, not one each "
        f"(cold: {cold_stores})")


def runCocotbTests():
    build_dir = build_directory("test_dcache_warm_hits")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_warm_hits",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
