"""An interrupt handler reads the value of every store before mepc, at any interrupt cycle."""

import cocotb
from cocotb.clock import Clock

from store_buffer_programs import (
    BAD_READS,
    COUNTER,
    DEFAULT_DEPTH,
    FAST_FETCH,
    FAST_FETCH_DEPTHS,
    LATENCIES,
    LOOPS,
    SWEEP_LATENCY,
    assemble,
    build_latency,
    run_image,
)
from support import build_directory, nop_image, peek, run_top


@cocotb.test()
async def test_handler_reads_buffered_store(dut):
    """An interrupt at any cycle: the handler must read the value of every store before mepc."""
    if build_latency() != SWEEP_LATENCY or FAST_FETCH:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    reference = await run_image(dut, "irq.bin")
    assert reference is not None, "reference run did not finish"
    failures = []
    taken = 0
    for inject in range(reference + 1):
        done = await run_image(dut, "irq.bin", inject_cycle=inject, limit=reference + 400)
        if done is None:
            failures.append(f"interrupt at cycle {inject}: did not finish")
            continue
        if int(dut.cpu_inst.csr_file_inst.mcause.value) == 0x8000_0003:
            taken += 1
        if peek(dut, BAD_READS):
            failures.append(f"interrupt at cycle {inject}: handler read a stale value")
        if peek(dut, COUNTER) != LOOPS:
            failures.append(f"interrupt at cycle {inject}: final counter {peek(dut, COUNTER)}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


def runCocotbTests():
    build_dir = build_directory("test_store_buffer_handler")
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        run_top(
            "test_store_buffer_handler",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            boot_image=nop_image(),
            extra_env={"STORE_BUFFER_BUILD": str(build_dir.resolve()), "STORE_BUFFER_LATENCY": str(latency), "STORE_BUFFER_DEPTH": str(depth), "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0"},
        )


if __name__ == "__main__":
    runCocotbTests()
