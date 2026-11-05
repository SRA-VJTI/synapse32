"""An interrupt taken while EX holds a bubble must not lose the instruction in IF/ID."""
import shutil
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly, NextTimeStep
from cocotb_test.simulator import run

DATA_BASE = 0x10000000


def lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x37


def auipc(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x17


def addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x13


def lw(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x03


def sw(rs2, rs1, imm):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | ((imm & 0x1F) << 7) | 0x23


def csrrw(rd, csr, rs1):
    return (csr << 20) | (rs1 << 15) | (1 << 12) | (rd << 7) | 0x73


def csrrs(rd, csr, rs1):
    return (csr << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x73


def jal(rd, off):
    imm = off & 0x1FFFFF
    return (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) | (((imm >> 11) & 1) << 20) | \
           (((imm >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F


MRET = 0x30200073
A0, T0, T1, T2, T3, T4, T5 = 10, 5, 6, 7, 28, 29, 30

PROGRAM = [
    lui(A0, 0x10000),
    auipc(T3, 0),
    addi(T3, T3, 0x40 - 4),
    csrrw(0, 0x305, T3),
    addi(T4, 0, 8),
    csrrs(0, 0x304, T4),
    csrrs(0, 0x300, T4),
    addi(T2, 0, 5),
    sw(T2, A0, 0),
    lw(T0, A0, 0),
    addi(T1, T0, 1),
    sw(T1, A0, 4),
    addi(T5, 0, 1),
    sw(T5, A0, 8),
    jal(0, 0),
]
assert len(PROGRAM) < 16
PROGRAM += [0x13] * (16 - len(PROGRAM))
PROGRAM.append(MRET)  # 0x40


def write_hex(path):
    words = list(PROGRAM)
    while len(words) < 512:
        words.append(0x13)
    with open(path, "w") as f:
        f.write("@00000000\n")
        for i in range(0, len(words), 4):
            f.write(" ".join(f"{w:08x}" for w in words[i:i + 4]) + "\n")


async def trial(dut, k):
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    stored = {}
    mepc = None
    bubble = False
    for cycle in range(k + 60):
        if cycle == k:
            dut.software_interrupt.value = 1
        elif cycle == k + 1:
            dut.software_interrupt.value = 0
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.cpu_inst.module_mem_wr_en.value):
            stored[int(dut.cpu_inst.module_write_addr.value)] = int(dut.cpu_inst.module_wr_data_out.value)
        if mepc is None and int(dut.cpu_inst.interrupt_taken_qualified.value):
            mepc = int(dut.cpu_inst.interrupt_pc.value)
            ex_valid = int(dut.cpu_inst.id_ex_inst0_instr_valid_out.value)
            ex_pc = int(dut.cpu_inst.id_ex_inst0_pc_out.value)
            ifid_valid = int(dut.cpu_inst.if_id_instr_valid_out.value)
            ifid_pc = int(dut.cpu_inst.if_id_pc_out.value)
            hazard = int(dut.cpu_inst.hazard_stall.value)
            bubble = not ex_valid and bool(ifid_valid)
            info = f"ex_valid={ex_valid} ex_pc=0x{ex_pc:08x} ifid_valid={ifid_valid} ifid_pc=0x{ifid_pc:08x} hazard={hazard}"
        await NextTimeStep()
    return stored, mepc, bubble, (info if mepc is not None else "")


@cocotb.test()
async def sweep(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    bad = []
    taken = 0
    bubble_trials = 0
    for k in range(4, 40):
        stored, mepc, bubble, info = await trial(dut, k)
        taken += mepc is not None
        bubble_trials += bubble
        val = stored.get(DATA_BASE + 4)
        done = stored.get(DATA_BASE + 8)
        ok = (val == 6) and (done == 1)
        dut._log.info(f"k={k:2d} mepc={'-' if mepc is None else f'0x{mepc:08x}'} mem[4]={val} done={done} {'OK' if ok else 'BAD'} {info}")
        if mepc is not None and not ok:
            bad.append((k, mepc, val, done, info))
    assert not bad, f"instruction skipped for {len(bad)} interrupt timings: {bad}"
    assert taken > 0, "no trial took the interrupt"
    assert bubble_trials > 0, "no trial took the interrupt on an EX bubble with IF/ID valid; coverage lost"


def runCocotbTests():
    root = Path(__file__).resolve().parents[2]
    rtl = root / "rtl"
    sources = [str(p) for p in rtl.rglob("*.v")]
    build = Path.cwd() / "build"
    build.mkdir(exist_ok=True)
    hex_file = build / "interrupt_bubble_pc.hex"
    write_hex(hex_file)
    sim_build = Path.cwd() / "sim_build_interrupt_bubble_pc"
    if sim_build.exists():
        shutil.rmtree(sim_build)
    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_interrupt_bubble_pc",
        includes=[str(rtl / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{hex_file}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_interrupt_bubble_pc",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_interrupt_bubble_pc",
        },
    )


if __name__ == "__main__":
    runCocotbTests()
