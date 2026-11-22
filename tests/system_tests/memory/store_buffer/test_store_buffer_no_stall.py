"""A store does not wait for memory: the pipeline goes on while it is buffered."""

import cocotb
from cocotb.clock import Clock

from store_buffer_programs import (
    DEFAULT_DEPTH,
    FAST_FETCH,
    FAST_FETCH_DEPTHS,
    LATENCIES,
    RESULT,
    SCRATCH,
    STORE_RUN,
    SWEEP_LATENCY,
    UNRELATED_VALUE,
    assemble,
    run_image,
)
from support import build_directory, nop_image, peek, run_top


@cocotb.test()
async def test_stores_do_not_hold_the_pipeline(dut):
    """With fetch answering at once and data after two cycles, a store must not wait for memory."""
    if not FAST_FETCH:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "ordering.bin", setup=[(SCRATCH + 0x40, UNRELATED_VALUE)])
    assert done is not None, "the program did not finish"
    store_cycles = peek(dut, RESULT)
    alu_cycles = peek(dut, RESULT + 4)
    assert store_cycles == alu_cycles, (
        f"{STORE_RUN} stores among ALU instructions took {store_cycles} cycles, the same run with ALU "
        f"instructions in their place {alu_cycles}: the stores waited for memory")


def runCocotbTests():
    build_dir = build_directory("test_store_buffer_no_stall")
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        run_top(
            "test_store_buffer_no_stall",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            boot_image=nop_image(),
            extra_env={"STORE_BUFFER_BUILD": str(build_dir.resolve()), "STORE_BUFFER_LATENCY": str(latency), "STORE_BUFFER_DEPTH": str(depth), "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0"},
        )


if __name__ == "__main__":
    runCocotbTests()
