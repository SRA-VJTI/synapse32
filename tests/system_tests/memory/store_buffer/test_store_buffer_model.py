"""Mixed stores and loads match a memory model."""

import os

import cocotb
from cocotb.clock import Clock

from store_buffer_programs import (
    DEFAULT_DEPTH,
    FAST_FETCH,
    FAST_FETCH_DEPTHS,
    LATENCIES,
    STRESS,
    STRESS_LOADS,
    STRESS_LOG,
    SWEEP_LATENCY,
    TRAP_CAUSE,
    assemble,
    build_latency,
    run_image,
    stress_case,
)
from support import build_directory, nop_image, peek, run_top


def _depth() -> int:
    return int(os.environ["STORE_BUFFER_DEPTH"])


@cocotb.test()
async def test_mixed_stores_and_loads_match_a_memory_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _, initial, expected_log, expected_memory = stress_case()
    setup = [(STRESS + 4 * i, word) for i, word in enumerate(initial)]
    setup += [(STRESS_LOG + 4 * i, 0) for i in range(STRESS_LOADS)]
    coverage = {"full": 0, "match": 0}
    done = await run_image(dut, "stress.bin", setup=setup, coverage=coverage)
    name = f"latency {build_latency()}, depth {_depth()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{peek(dut, TRAP_CAUSE):08x}"
    log = [peek(dut, STRESS_LOG + 4 * i) for i in range(len(expected_log))]
    bad_loads = [(i, f"0x{g:x}", f"0x{e:x}") for i, (g, e) in enumerate(zip(log, expected_log)) if g != e]
    assert not bad_loads, f"{name}: loads (index, got, expected): {bad_loads[:6]}"
    memory = [peek(dut, STRESS + 4 * i) for i in range(len(expected_memory))]
    bad_words = [(i, f"0x{g:x}", f"0x{e:x}") for i, (g, e) in enumerate(zip(memory, expected_memory)) if g != e]
    assert not bad_words, f"{name}: final words (index, got, expected): {bad_words[:6]}"
    dut._log.info(f"{name}: {coverage['full']} cycles a store waited on a full buffer, "
                  f"{coverage['match']} cycles a load waited on a buffered word")
    if FAST_FETCH:
        assert coverage["full"] and coverage["match"], (
            f"{name}: the buffer never filled or no load waited on a buffered word ({coverage}), "
            "so this run did not exercise the buffer")


def runCocotbTests():
    build_dir = build_directory("test_store_buffer_model")
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        run_top(
            "test_store_buffer_model",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            boot_image=nop_image(),
            extra_env={"STORE_BUFFER_BUILD": str(build_dir.resolve()), "STORE_BUFFER_LATENCY": str(latency), "STORE_BUFFER_DEPTH": str(depth), "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0"},
        )


if __name__ == "__main__":
    runCocotbTests()
