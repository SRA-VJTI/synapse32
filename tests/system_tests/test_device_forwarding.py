"""A buffered store outside RAM is a device write, also through a page table: never forwarded to a later load.

The program runs in M-mode with MPRV set and MPP = S, so its loads and stores are translated (megapages mapping
RAM and the peripheral window to themselves) while its fetches are not. 0x2000_1000 is in the peripheral window
but is none of the core's devices, standing in for one a system adds there.
"""

import os
import shutil
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb_test.simulator import run

from cpu_program import run_program
from memory_view import dcache

RAM = 0x1000_0000
DEVICE = 0x2000_1000
UART_SCR = 0x2000_001C
ROOT_TABLE = 0x1001_0000
SATP = 0x8000_0000 | (ROOT_TABLE >> 12)
CSR_SATP = 0x180
CSR_MSTATUS = 0x300
MSTATUS_MPP = 0x1800
MSTATUS_MPP_S = 0x0800
MSTATUS_MPRV = 0x2_0000
LEAF = 0xC7  # V R W A D


def _megapage_pte(base):
    return ((base >> 12) << 10) | LEAF


def _lui(rd, value):
    return (value & 0xFFFF_F000) | (rd << 7) | 0x37


def _addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def _li(rd, value):
    low = ((value & 0xFFF) ^ 0x800) - 0x800
    return [_lui(rd, (value - low) & 0xFFFF_FFFF), _addi(rd, rd, low)]


def _sw(rs2, rs1, imm=0):
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | ((imm & 0x1F) << 7) | 0x23


def _lw(rd, rs1, imm=0):
    return (imm << 20) | (rs1 << 15) | (0b010 << 12) | (rd << 7) | 0x03


def _csr(funct3, csr, rs1):
    return (csr << 20) | (rs1 << 15) | (funct3 << 12) | 0x73


SFENCE_VMA = 0x1200_0073


async def _watch(dut, counts):
    """Count translated accesses, dcache lookups and store-to-load forwards by word address."""
    cpu = dut.cpu_inst
    cache = dcache(dut)
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        word = int(cpu.phys_data_addr.value) & ~3
        if int(cpu.translated_data_access.value):
            counts["translated", word] = counts.get(("translated", word), 0) + 1
        if int(cpu.store_buf_forward_go.value):
            counts["forward", word] = counts.get(("forward", word), 0) + 1
        if int(cache.lookup.value):
            line_word = int(cache.addr.value) & ~3
            counts["lookup", line_word] = counts.get(("lookup", line_word), 0) + 1


@cocotb.test()
async def test_translated_store_outside_ram_is_not_forwarded(dut):
    """A store queued behind a UART write, then a load of its word: only the RAM word may be forwarded."""
    instr_mem = [
        *_li(10, ROOT_TABLE),
        *_li(11, _megapage_pte(RAM)),
        _sw(11, 10, 4 * (RAM >> 22)),
        *_li(11, _megapage_pte(DEVICE & 0xFFC0_0000)),
        _sw(11, 10, 4 * (DEVICE >> 22)),
        *_li(11, SATP),
        _csr(0b001, CSR_SATP, 11),  # csrrw
        SFENCE_VMA,
        *_li(11, MSTATUS_MPP),
        _csr(0b011, CSR_MSTATUS, 11),  # csrrc
        *_li(11, MSTATUS_MPP_S | MSTATUS_MPRV),
        _csr(0b010, CSR_MSTATUS, 11),  # csrrs: data accesses from here on are translated
        _lui(1, DEVICE),
        _lui(2, RAM),
        _lui(7, UART_SCR),
        _addi(3, 0, 0x5A),
        _addi(5, 0, 0x3C),
        _lw(8, 7, UART_SCR & 0xFFF),  # both megapages in the TLB, so no walk drains the buffer below
        _lw(9, 2),
        _sw(3, 7, UART_SCR & 0xFFF),  # holds the data port, so the next store waits in the buffer
        _sw(3, 1),
        _lw(4, 1),
        _sw(5, 7, UART_SCR & 0xFFF),
        _sw(5, 2),
        _lw(6, 2),
    ]
    counts = {}
    cocotb.start_soon(_watch(dut, counts))
    await run_program(dut, instr_mem)

    regs = dut.cpu_inst.rf_inst0.register_file
    assert int(regs[6].value) == 0x3C, f"RAM load returned {int(regs[6].value):#x}"
    assert counts.get(("translated", DEVICE), 0), "the device word was not accessed translated, so the check proves nothing"
    assert counts.get(("forward", RAM), 0), "the RAM word was not forwarded, so the check proves nothing"
    assert not counts.get(("lookup", DEVICE), 0), f"the dcache looked up the device word {DEVICE:#x}"
    assert not counts.get(("forward", DEVICE), 0), f"a buffered store was forwarded from the device word {DEVICE:#x}"


def runCocotbTests():
    root = Path.cwd()
    while not (root / "rtl").exists():
        if root.parent == root:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root = root.parent
    rtl_dir = root / "rtl"
    module = "test_device_forwarding"
    sim_build = Path.cwd() / "sim_build" / f"sim_build_{module}"
    if sim_build.exists():
        shutil.rmtree(sim_build)
    run(
        verilog_sources=[str(p) for p in sorted(rtl_dir.rglob("*.v"))],
        toplevel="top",
        module=module,
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(sim_build),
        waves=os.getenv("WAVES", "0") == "1",
        # Memory latency keeps the UART write on the data port long enough for the next store to wait in the buffer.
        parameters={"MEM_LATENCY": 2},
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": module,
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": module,
        },
    )


if __name__ == "__main__":
    runCocotbTests()
