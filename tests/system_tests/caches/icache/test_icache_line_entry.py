"""A jump into any word of a line fetches from that word."""

import cocotb
from cocotb.clock import Clock

from icache_programs import ENTRY_OFFSETS, LATENCIES, RESULT, VALUES, assemble, build_name, check_finished, run_image
from support import build_directory, nop_image, peek, run_top


@cocotb.test()
async def test_entry_into_any_word_of_a_line(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "entry.bin")
    check_finished(dut, done)
    got = [peek(dut, RESULT + off) for off in ENTRY_OFFSETS]
    expected = [0x41 + off for off in ENTRY_OFFSETS]
    assert got == expected, f"{build_name()}: entries returned {[hex(v) for v in got]}, expected {[hex(v) for v in expected]}"
    wrong_path = peek(dut, RESULT + VALUES)
    assert wrong_path == 0, f"{build_name()}: {wrong_path} instructions before a jump target ran"


def runCocotbTests():
    build_dir = build_directory("test_icache_line_entry")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_line_entry",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
