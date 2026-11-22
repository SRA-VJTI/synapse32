"""An interrupt at any cycle of cold code does not disturb the program."""

import cocotb
from cocotb.clock import Clock

from icache_programs import IRQ_COUNT, LATENCIES, RESULT, SWEEP_RUN, assemble, build_latency, check_finished, run_image
from support import build_directory, nop_image, peek, run_top


SWEEP_LATENCY = 2


@cocotb.test()
async def test_interrupt_at_every_cycle_of_cold_code(dut):
    if build_latency() != SWEEP_LATENCY:
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
        if peek(dut, RESULT) != SWEEP_RUN:
            failures.append(f"interrupt at cycle {inject}: counted {peek(dut, RESULT)}, expected {SWEEP_RUN}")
    dut._log.info(f"swept {reference + 1} cycles, {taken} interrupts taken, {len(failures)} failures")
    assert taken, "no interrupt was taken, so the sweep proves nothing"
    assert not failures, f"{len(failures)} failures; first: {failures[0]}"


def runCocotbTests():
    build_dir = build_directory("test_icache_interrupt_sweep")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_interrupt_sweep",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
