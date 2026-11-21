"""The page-table walker sees a PTE that is still in the store buffer."""

import cocotb
from cocotb.clock import Clock

from store_buffer_programs import (
    A,
    D,
    DEFAULT_DEPTH,
    FAST_FETCH,
    FAST_FETCH_DEPTHS,
    L0_ENTRY_B,
    L0_TABLE,
    LATENCIES,
    NEW_MARKER,
    OLD_MARKER,
    PAGE_A_PA,
    PAGE_A_VA,
    PAGE_B_OLD_PA,
    R,
    RESULT,
    ROOT_TABLE,
    SWEEP_LATENCY,
    TRAP_CAUSE,
    V,
    W,
    X,
    assemble,
    build_latency,
    run_image,
)
from support import DATA_MEM_BASE, build_directory, nop_image, peek, poke, pte, run_top


L0_ENTRY_A = L0_TABLE + 4 * ((PAGE_A_VA >> 12) & 0x3FF)


@cocotb.test()
async def test_page_walk_sees_buffered_pte(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    setup = [
        (ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, V | R | W | A | D)),
        (ROOT_TABLE + 4 * (PAGE_A_VA >> 22), pte(L0_TABLE, V)),
        (L0_ENTRY_A, pte(PAGE_A_PA, V | R | X | A)),
        (L0_ENTRY_B, pte(PAGE_B_OLD_PA, V | R | X | A)),
    ]
    for offset in range(0, 0x1000, 4):
        poke(dut, ROOT_TABLE + offset, 0)
        poke(dut, L0_TABLE + offset, 0)
    done = await run_image(dut, "paging.bin", setup=setup)
    name = f"latency {build_latency()}{' fast fetch' if FAST_FETCH else ''}"
    assert done is not None, f"{name}: the program did not finish"
    assert peek(dut, TRAP_CAUSE) == 0, f"{name}: unexpected trap, mcause 0x{peek(dut, TRAP_CAUSE):08x}"
    marker = peek(dut, RESULT)
    assert marker == NEW_MARKER, (
        f"{name}: page B ran the code at 0x{PAGE_B_OLD_PA if marker == OLD_MARKER else 0:08x} "
        f"(marker 0x{marker:08x}): the walk after SFENCE.VMA did not see the entry written before it")


def runCocotbTests():
    build_dir = build_directory("test_store_buffer_walker")
    assemble(build_dir)

    builds = [(f"lat{latency}", latency, latency, DEFAULT_DEPTH) for latency in LATENCIES]
    builds += [(f"fast_fetch_depth{depth}", SWEEP_LATENCY, 0, depth) for depth in FAST_FETCH_DEPTHS]
    for name, latency, fetch_latency, depth in builds:
        run_top(
            "test_store_buffer_walker",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": fetch_latency,
                        "STORE_BUFFER_DEPTH": depth},
            boot_image=nop_image(),
            extra_env={"STORE_BUFFER_BUILD": str(build_dir.resolve()), "STORE_BUFFER_LATENCY": str(latency), "STORE_BUFFER_DEPTH": str(depth), "STORE_BUFFER_FAST_FETCH": "1" if fetch_latency != latency else "0"},
        )


if __name__ == "__main__":
    runCocotbTests()
