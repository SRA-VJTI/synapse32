"""Store misses to one line merge into its MSHR, and loads of that line wait for the fill."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import (
    BUILDS,
    DEFAULT_MSHRS,
    MERGE_LINES,
    assemble,
    build_name,
    check_finished,
    Coverage,
    require_cache,
    results,
    run_image,
)
from support import build_directory, nop_image, run_top


MERGE_OLD = [0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444]

MERGE_EXPECTED = [0x1111_AA11, 0xBBBB_2222, 0xCCCC_CCCC, 0x4444_4444, 0xFFFF_FFAA, 0xFFFF_BBBB, 0x11, 0xBBBB]


@cocotb.test()
async def test_store_misses_merge_and_loads_wait_for_the_fill(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    setup = [(line + 4 * i, v) for line in MERGE_LINES for i, v in enumerate(MERGE_OLD)]
    done = await run_image(dut, "merge.bin", setup=setup, coverage=coverage)
    check_finished(dut, done)
    got = results(dut, 2 * len(MERGE_EXPECTED))
    assert got == 2 * MERGE_EXPECTED, (
        f"{build_name()}: loads returned {[hex(v) for v in got]}, expected {[hex(v) for v in MERGE_EXPECTED]} twice")
    require_cache(dut)
    assert coverage.merges > 0, f"{build_name()}: no store merged into an MSHR"
    assert coverage.load_waits_on_mshr > 0, f"{build_name()}: no load waited on an MSHR"


def runCocotbTests():
    build_dir = build_directory("test_dcache_mshr_merge")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_mshr_merge",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
