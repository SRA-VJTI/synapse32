"""An interrupt at any cycle of misses and evictions does not disturb the program."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import (
    BUILDS,
    DEFAULT_MSHRS,
    IRQ_COUNT,
    RESULT,
    SWEEP_LATENCY,
    SWEEP_LINES,
    assemble,
    build_latency,
    build_mshrs,
    check_finished,
    run_image,
)
from support import build_directory, nop_image, peek, run_top


SWEEP_EXPECTED = sum(0x30 + i for i in range(len(SWEEP_LINES)))


@cocotb.test()
async def test_interrupt_at_every_cycle_of_misses_and_evictions(dut):
    if build_latency() != SWEEP_LATENCY or build_mshrs() != 8:
        return
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    reference = await run_image(dut, "sweep.bin")
    check_finished(dut, reference)
    failures = []
    taken = 0
    for inject in range(reference + 1):
        done = await run_image(dut, "sweep.bin", inject_cycle=inject, limit=reference + 400)
        if done is None:
            failures.append(f"interrupt at cycle {inject}: did not finish")
            continue
        count = peek(dut, IRQ_COUNT)
        taken += count
        if count > 1:
            failures.append(f"interrupt at cycle {inject}: handler ran {count} times")
        if peek(dut, RESULT) != SWEEP_EXPECTED:
            failures.append(f"interrupt at cycle {inject}: sum {peek(dut, RESULT):#x}, expected {SWEEP_EXPECTED:#x}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


def runCocotbTests():
    build_dir = build_directory("test_dcache_interrupt_sweep")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_interrupt_sweep",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
