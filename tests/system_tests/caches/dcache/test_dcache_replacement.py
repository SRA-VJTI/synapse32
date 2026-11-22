"""Replacement: a full set evicts its PLRU way, and a store to the victim as it is chosen is kept."""

import os

import cocotb
from cocotb.clock import Clock

from dcache_programs import (
    BUILDS,
    DEFAULT_MSHRS,
    PLRU_LINES,
    PLRU_NEW,
    RACE_GAPS,
    WAYS,
    assemble,
    build_name,
    check_finished,
    Coverage,
    require_cache,
    results,
    run_image,
)
from support import build_directory, nop_image, peek, run_top, word_index


PLRU_OLD = [0x0B0B_0000 + i for i in range(WAYS + 2)]

PLRU_WRITTEN_BACK = [1, 2]

def _ram(dut, addr: int) -> int:
    """What the backing RAM holds at addr, whatever the cache holds."""
    return int(dut.unified_mem_inst.instr_ram[word_index(addr)].value) & 0xFFFF_FFFF


@cocotb.test()
async def test_a_full_set_replaces_its_plru_way(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    setup = list(zip(PLRU_LINES, PLRU_OLD))
    done = await run_image(dut, "plru.bin", setup=setup)
    check_finished(dut, done)
    seen = [peek(dut, addr) for addr in PLRU_LINES]
    assert seen == PLRU_NEW, f"{build_name()}: the lines read {[hex(v) for v in seen]}, expected {[hex(v) for v in PLRU_NEW]}"
    in_ram = [i for i, addr in enumerate(PLRU_LINES) if _ram(dut, addr) == PLRU_NEW[i]]
    assert in_ram == PLRU_WRITTEN_BACK, (
        f"{build_name()}: lines {in_ram} reached RAM; pseudo-LRU writes back lines {PLRU_WRITTEN_BACK} and keeps "
        "the others dirty in the cache")


@cocotb.test()
async def test_a_store_to_the_victim_as_it_is_chosen(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    coverage = Coverage()
    done = await run_image(dut, "race.bin", coverage=coverage)
    check_finished(dut, done)
    got = results(dut, 4 * len(RACE_GAPS))
    expected = [0xA5, 0x5A] * (2 * len(RACE_GAPS))
    assert got == expected, (
        f"{build_name()}: (first line, fifth line) per gap read {[hex(v) for v in got]}, expected 0xa5, 0x5a each: a "
        "store to the line being replaced was lost")
    require_cache(dut)
    assert coverage.stores_at_victim > 0, f"{build_name()}: no store arrived while a victim was chosen"


def runCocotbTests():
    build_dir = build_directory("test_dcache_replacement")
    assemble(build_dir)

    builds = BUILDS
    if os.environ.get("DCACHE_BUILDS"):
        builds = [tuple(int(v) for v in b.split(":")) for b in os.environ["DCACHE_BUILDS"].split(",")]
    for latency, mshrs in builds:
        parameters = {"MEM_LATENCY": latency, "FETCH_LATENCY": latency}
        if mshrs != DEFAULT_MSHRS:
            parameters["NUM_MSHR"] = mshrs
        run_top(
            "test_dcache_replacement",
            parameters=parameters,
            boot_image=nop_image(),
            extra_env={"DCACHE_BUILD": str(build_dir.resolve()), "DCACHE_LATENCY": str(latency), "DCACHE_MSHRS": str(mshrs)},
        )


if __name__ == "__main__":
    runCocotbTests()
