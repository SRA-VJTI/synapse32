"""Regression tests for misaligned RV32A operations.

LR.W, SC.W, and AMO.W must trap with causes 4, 6, and 6 respectively and
must not modify their destination registers or memory before entering the
handler.
"""
import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


BASE = 0x10000000
CAUSE_ADDR = BASE + 0x40
DEST_ADDR = BASE + 0x44
MEPC_ADDR = BASE + 0x48
MTVAL_ADDR = BASE + 0x4C
EXPECTED_PC_ADDR = BASE + 0x50
DONE_ADDR = BASE + 0xFF
DEST_SENTINEL = 0x55


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root")
        cur = cur.parent
    return cur


def compile_misaligned_asm(build_dir: Path, sim_dir: Path, operation: str) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / f"misaligned_{operation}.S"
    atomic = {
        "lr": "lr.w t3, (t1)",
        "sc": "sc.w t3, t2, (t1)",
        "amo": "amoadd.w t3, t2, (t1)",
    }[operation]
    src.write_text(
        f"""
        .section .text
        .global main
        .type main, @function
main:
        la    t0, trap_handler
        csrw  mtvec, t0
        li    t1, 0x10000001
        li    t2, {DEST_SENTINEL}
        li    t3, {DEST_SENTINEL}
        la    t4, faulting_atomic
        li    t5, {BASE}
        sw    t4, 0x50(t5)
faulting_atomic:
        {atomic}
        j     .

        .align 2
trap_handler:
        li    t0, {BASE}
        csrr  t1, mcause
        sw    t1, 0x40(t0)
        sw    t3, 0x44(t0)
        csrr  t1, mepc
        sw    t1, 0x48(t0)
        csrr  t1, mtval
        sw    t1, 0x4c(t0)
        li    t1, 1
        sb    t1, 0xff(t0)
        j     .
""",
        encoding="ascii",
    )

    common_flags = [
        "-march=rv32ima_zicsr_zifencei",
        "-mabi=ilp32",
        "-nostdlib",
        "-ffreestanding",
    ]
    objects = []
    for in_src in (sim_dir / "start.S", src):
        obj = build_dir / f"{in_src.stem}_{operation}.o"
        subprocess.run(
            ["riscv64-unknown-elf-gcc", *common_flags, "-c", str(in_src), "-o", str(obj)],
            check=True,
        )
        objects.append(obj)

    elf = build_dir / f"misaligned_{operation}.elf"
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", *common_flags,
            "-Wl,--no-relax", "-Wl,-m,elf32lriscv", "-T", str(sim_dir / "link.ld"),
            *[str(obj) for obj in objects], "-o", str(elf),
        ],
        check=True,
    )
    binary = build_dir / f"misaligned_{operation}.bin"
    hex_file = build_dir / f"misaligned_{operation}.hex"
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(binary)], check=True)
    subprocess.run(["truncate", "-s", "2048", str(binary)], check=True)
    subprocess.run(
        [
            "riscv64-unknown-elf-objcopy", "-I", "binary", "-O", "verilog",
            "--verilog-data-width=4", "--reverse-bytes=4", str(binary), str(hex_file),
        ],
        check=True,
    )
    return hex_file


async def _run_misaligned_test(dut, expected_cause: int):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    writes = {}
    for _ in range(300):
        await RisingEdge(dut.clk)
        if int(dut.cpu_mem_write_en.value):
            writes[int(dut.cpu_mem_write_addr.value)] = int(dut.cpu_mem_write_data.value)
        if writes.get(DONE_ADDR) == 1:
            break

    assert writes.get(DONE_ADDR) == 1, "Misaligned atomic did not enter its trap handler"
    assert writes.get(CAUSE_ADDR) == expected_cause
    assert writes.get(DEST_ADDR) == DEST_SENTINEL, (
        "Misaligned atomic modified its destination before trapping"
    )
    assert BASE + 1 not in writes, (
        "Misaligned atomic performed a memory write before trapping"
    )
    assert writes.get(MEPC_ADDR) == writes.get(EXPECTED_PC_ADDR), (
        "Trap mepc does not identify the faulting atomic instruction"
    )
    assert writes.get(MTVAL_ADDR) == BASE + 1, (
        "Trap mtval does not contain the misaligned effective address"
    )


@cocotb.test()
async def test_misaligned_lr(dut):
    await _run_misaligned_test(dut, expected_cause=4)


@cocotb.test()
async def test_misaligned_sc(dut):
    await _run_misaligned_test(dut, expected_cause=6)


@cocotb.test()
async def test_misaligned_amo(dut):
    await _run_misaligned_test(dut, expected_cause=6)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sim_dir = repo_root / "sim"
    includes = [str(rtl_dir / "include")]
    sources = [
        str(Path(root) / file)
        for root, _, files in os.walk(rtl_dir)
        for file in files
        if file.endswith((".v", ".sv"))
    ]

    build_dir = Path.cwd() / "build"
    for operation in ("lr", "sc", "amo"):
        hex_file = compile_misaligned_asm(build_dir, sim_dir, operation)
        sim_build = Path.cwd() / "sim_build" / f"sim_build_misaligned_{operation}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_misaligned_atomic",
            testcase=f"test_misaligned_{operation}",
            includes=includes,
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{hex_file}"'],
            sim_build=str(sim_build),
            force_compile=True,
        )


if __name__ == "__main__":
    runCocotbTests()
