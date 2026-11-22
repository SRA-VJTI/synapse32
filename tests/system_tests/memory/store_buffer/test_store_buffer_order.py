"""Buffered writes reach memory in program order."""

import cocotb
from cocotb.clock import Clock

from store_buffer_programs import (
    DEFAULT_DEPTH,
    FAST_FETCH,
    FAST_FETCH_DEPTHS,
    LATENCIES,
    RESULT,
    SCRATCH,
    SWEEP_LATENCY,
    TRAP_CAUSE,
    UNRELATED_VALUE,
    assemble,
    build_latency,
    run_image,
)
from support import build_directory, nop_image, peek, run_top


UART_DEFAULT_DLL = 1

ORDERING_EXPECTED = {
    2: 0xA1B2C3D4,
    3: 0xA1B25AD4,
    4: 0xBEEF,
    5: 0x12,
    6: UNRELATED_VALUE,
    7: 0xCAFE,
    8: 5,
    9: 8,
    10: 7,
    11: 0,
    12: 9,
    13: UART_DEFAULT_DLL,
    14: 42,
}


@cocotb.test()
async def test_buffered_writes_keep_program_order(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    done = await run_image(dut, "ordering.bin", setup=[(SCRATCH + 0x40, UNRELATED_VALUE)])
    name = f"latency {build_latency()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{peek(dut, TRAP_CAUSE):08x}"
    got = {i: peek(dut, RESULT + 4 * i) for i in ORDERING_EXPECTED}
    wrong = {i: (f"0x{got[i]:x}", f"0x{v:x}") for i, v in ORDERING_EXPECTED.items() if got[i] != v}
    assert not wrong, f"{name}: result words (got, expected): {wrong}"


def runCocotbTests():
    build_dir = build_directory("test_store_buffer_order")
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        run_top(
            "test_store_buffer_order",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            boot_image=nop_image(),
            extra_env={"STORE_BUFFER_BUILD": str(build_dir.resolve()), "STORE_BUFFER_LATENCY": str(latency), "STORE_BUFFER_DEPTH": str(depth), "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0"},
        )


if __name__ == "__main__":
    runCocotbTests()
