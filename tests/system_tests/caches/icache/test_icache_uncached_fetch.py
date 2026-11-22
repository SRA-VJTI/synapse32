"""A fetch outside RAM bypasses the cache."""

import cocotb
from cocotb.clock import Clock

from icache_programs import (
    LATENCIES,
    SSIP_CAUSE,
    TRAP_CAUSE,
    TRAP_EPC,
    UNCACHED,
    UNCACHED_CYCLES,
    assemble,
    build_latency,
    build_name,
    check_finished,
    run_image,
)
from support import build_directory, nop_image, peek, run_top


UNCACHED_SLACK = 6  # instructions in flight when the interrupt is taken, plus margin


@cocotb.test()
async def test_fetch_outside_ram_bypasses(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "uncached.bin", inject_uncached=True)
    check_finished(dut, done, expect_trap=True)
    cause, epc = peek(dut, TRAP_CAUSE), peek(dut, TRAP_EPC)
    assert cause == SSIP_CAUSE, f"{build_name()}: expected the software interrupt, got mcause 0x{cause:08x}"
    assert UNCACHED < epc < UNCACHED + 0x1000, (
        f"{build_name()}: interrupted at 0x{epc:08x}, expected inside the NOPs at 0x{UNCACHED:08x}")
    # Uncached, each NOP takes one fetch; filling lines there would take longer.
    ran, uncached_rate = (epc - UNCACHED) // 4, UNCACHED_CYCLES // (build_latency() + 1)
    assert ran >= uncached_rate - UNCACHED_SLACK, (
        f"{build_name()}: {ran} NOPs ran in the {UNCACHED_CYCLES} cycles before the interrupt, uncached fetch gives "
        f"about {uncached_rate}: fetches outside RAM were cached")


def runCocotbTests():
    build_dir = build_directory("test_icache_uncached_fetch")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_uncached_fetch",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
