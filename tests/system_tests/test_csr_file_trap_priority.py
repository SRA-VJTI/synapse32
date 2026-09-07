"""CSR-file regressions for trap ordering and unimplemented PMP behavior."""

import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_test.simulator import run


def _repo_root() -> Path:
    root = Path.cwd()
    while not (root / "rtl").is_dir():
        if root.parent == root:
            raise FileNotFoundError("rtl directory not found")
        root = root.parent
    return root


def _clear_inputs(dut):
    for name in (
        "write_enable", "read_enable", "interrupt_pending", "interrupt_taken",
        "mret_instruction", "sret_instruction", "interrupt_to_supervisor",
        "trap_to_supervisor", "ecall_exception", "ebreak_exception",
        "illegal_instruction_exception", "instruction_address_misaligned_exception",
        "load_address_misaligned_exception", "store_address_misaligned_exception",
        "instr_page_fault_exception", "load_page_fault_exception",
        "store_page_fault_exception", "instret_increment", "timer_interrupt",
        "software_interrupt", "external_interrupt",
    ):
        getattr(dut, name).value = 0
    dut.csr_addr.value = 0
    dut.write_data.value = 0
    dut.interrupt_cause_in.value = 0
    dut.interrupt_pc_in.value = 0
    dut.exception_pc_in.value = 0
    dut.exception_tval_in.value = 0


@cocotb.test()
async def test_page_fault_wins_and_pmp_is_hardwired_off(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _clear_inputs(dut)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0

    # Model an older faulting load in MEM while a younger invalid instruction
    # reaches EX in the same cycle.
    dut.exception_pc_in.value = 0x8000_0100
    dut.exception_tval_in.value = 0xDEAD_BEEF
    dut.load_page_fault_exception.value = 1
    dut.illegal_instruction_exception.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.mcause.value) == 13
    assert int(dut.mepc.value) == 0x8000_0100
    assert int(dut.mtval.value) == 0xDEAD_BEEF

    dut.load_page_fault_exception.value = 0
    dut.illegal_instruction_exception.value = 0

    # PMP is not enforced by this core, so probing must observe no entries.
    dut.csr_addr.value = 0x3B0
    dut.write_data.value = 0xFFFF_FFFF
    dut.write_enable.value = 1
    await RisingEdge(dut.clk)
    dut.write_enable.value = 0
    dut.read_enable.value = 1
    await Timer(1, units="ns")
    assert int(dut.read_data.value) == 0


def runCocotbTests():
    root = _repo_root()
    build = Path.cwd() / "sim_build_csr_file_trap_priority"
    if build.exists():
        shutil.rmtree(build)
    run(
        verilog_sources=[str(root / "rtl" / "core_modules" / "csr_file.v")],
        toplevel="csr_file",
        module="test_csr_file_trap_priority",
        testcase="test_page_fault_wins_and_pmp_is_hardwired_off",
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
