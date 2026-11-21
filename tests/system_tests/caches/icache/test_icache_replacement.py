"""A set holds its ways and replaces them round robin."""

import cocotb
from cocotb.clock import Clock

from icache_programs import EVICT_ORDER, LATENCIES, MARKS, WAYS, assemble, build_name, check_finished, run_image, slots
from support import build_directory, nop_image, run_top


@cocotb.test()
async def test_a_set_holds_its_ways_and_replaces_round_robin(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "evict.bin")
    check_finished(dut, done)
    times, values = slots(dut, 1 + len(EVICT_ORDER))
    expected = [MARKS[i] for i in EVICT_ORDER]
    assert values[1:] == expected, (
        f"{build_name()}: blocks returned {[hex(v) for v in values[1:]]}, expected {[hex(v) for v in expected]}")
    cold, warm = times[1:1 + WAYS], times[1 + WAYS:1 + 2 * WAYS]
    assert all(w < c for c, w in zip(cold, warm)), (
        f"{build_name()}: {WAYS} blocks in one set took {cold} cycles cold and {warm} warm: the set did not hold "
        "them all")
    hit = warm[0]
    _, first_again, fifth_again, second_again, fourth_again = times[1 + 2 * WAYS:]
    got = {"block 0 after the fifth": first_again, "the fifth again": fifth_again,
           "block 1 after block 0": second_again, "block 3": fourth_again}
    want = {"block 0 after the fifth": "miss", "the fifth again": "hit", "block 1 after block 0": "miss",
            "block 3": "hit"}
    wrong = {k: f"{v} cycles" for k, v in got.items() if (v == hit) != (want[k] == "hit")}
    assert not wrong, (
        f"{build_name()}: a hit takes {hit} cycles; round-robin expects {want}, got {wrong}")


def runCocotbTests():
    build_dir = build_directory("test_icache_replacement")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_replacement",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
