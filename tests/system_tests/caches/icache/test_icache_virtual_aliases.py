"""Two virtual pages mapped to one physical page share its cache lines."""

import cocotb
from cocotb.clock import Clock

from icache_programs import (
    LATENCIES,
    PA_MAIN,
    PA_SHARED,
    ROOT_TABLE,
    TRAP_CAUSE,
    TRAP_EPC,
    TRAP_TVAL,
    VA1,
    VA2,
    VA3,
    VA_MAIN,
    assemble,
    build_name,
    check_finished,
    run_image,
    slots,
)
from support import DATA_MEM_BASE, INSTR_MEM_BASE, build_directory, nop_image, peek, poke, pte, run_top


L0_TABLE = 0x1001_1000

V, R, W, X, A_BIT, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80

INSTR_PAGE_FAULT = 12

PAGING_SETUP = [
    (ROOT_TABLE + 4 * (DATA_MEM_BASE >> 22), pte(DATA_MEM_BASE, V | R | W | A_BIT | D)),
    (ROOT_TABLE + 4 * (INSTR_MEM_BASE >> 22), pte(INSTR_MEM_BASE, V | R | W | A_BIT | D)),
    (ROOT_TABLE + 4 * (VA1 >> 22), pte(L0_TABLE, V)),
    (L0_TABLE + 4 * ((VA1 >> 12) & 0x3FF), pte(PA_SHARED, V | R | X | A_BIT)),
    (L0_TABLE + 4 * ((VA2 >> 12) & 0x3FF), pte(PA_SHARED, V | R | X | A_BIT)),
    (L0_TABLE + 4 * ((VA3 >> 12) & 0x3FF), pte(PA_SHARED, V | R | A_BIT)),
    (L0_TABLE + 4 * ((VA_MAIN >> 12) & 0x3FF), pte(PA_MAIN, V | R | X | A_BIT)),
]


@cocotb.test()
async def test_virtual_pages_share_a_physical_line(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for offset in range(0, 0x1000, 4):
        poke(dut, ROOT_TABLE + offset, 0)
        poke(dut, L0_TABLE + offset, 0)
    done = await run_image(dut, "paging.bin", setup=PAGING_SETUP)
    check_finished(dut, done, expect_trap=True)
    times, values = slots(dut, 5)
    cause, tval, epc = peek(dut, TRAP_CAUSE), peek(dut, TRAP_TVAL), peek(dut, TRAP_EPC)
    assert values[1:] == [1, 1, 2, 2], (
        f"{build_name()}: VA1, VA2, then after the patch VA2, VA1 returned {values[1:]}, expected [1, 1, 2, 2] "
        f"(trap: mcause {cause}, mtval 0x{tval:08x}, mepc 0x{epc:08x})")
    assert times[2] < times[1], (
        f"{build_name()}: the first call through VA2 took {times[2]} cycles, through VA1 {times[1]}: VA2 did not "
        "hit the line VA1 filled")
    assert (cause, tval, epc) == (INSTR_PAGE_FAULT, VA3, VA3), (
        f"{build_name()}: fetch through VA3 (no execute permission) gave mcause {cause}, mtval 0x{tval:08x}, "
        f"mepc 0x{epc:08x}; expected an instruction page fault at 0x{VA3:08x}")


def runCocotbTests():
    build_dir = build_directory("test_icache_virtual_aliases")
    assemble(build_dir)

    for latency in LATENCIES:
        run_top(
            "test_icache_virtual_aliases",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            boot_image=nop_image(),
            extra_env={"ICACHE_BUILD": str(build_dir.resolve()), "ICACHE_LATENCY": str(latency)},
        )


if __name__ == "__main__":
    runCocotbTests()
