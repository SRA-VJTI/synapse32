"""Compile and run a self-modifying code program to validate FENCE.I behavior."""
import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


BASE = 0x10000000
DONE_ADDR = BASE + 0xFF
RESULT_ADDR = BASE + 0x270


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def compile_fence_i_asm(build_dir: Path, sim_dir: Path) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)

    src = build_dir / "fence_i_smoke.S"
    src.write_text(
        """
        .section .text
        .global main
        .type main, @function
main:
        # Patch the next instruction at patch_target from "addi a0, x0, 0"
        # to "addi a0, x0, 1" and use fence.i before executing it.
        la t0, patch_target
        li t1, 0x00100513
        sw t1, 0(t0)
        fence.i
patch_target:
        addi a0, x0, 0

        li t2, 0x10000000
        sw a0, 0x270(t2)
        li t3, 1
        sb t3, 0xff(t2)
1:
        j 1b
""",
        encoding="ascii",
    )

    start_s = sim_dir / "start.S"
    link_ld = sim_dir / "link.ld"

    common_flags = [
        "-march=rv32ima_zicsr_zifencei",
        "-mabi=ilp32",
        "-nostdlib",
        "-ffreestanding",
    ]

    objects = []
    for in_src in (start_s, src):
        obj = build_dir / f"{in_src.stem}.o"
        subprocess.run(
            ["riscv64-unknown-elf-gcc", *common_flags, "-c", str(in_src), "-o", str(obj)],
            check=True,
        )
        objects.append(obj)

    elf = build_dir / "fence_i_smoke.elf"
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc",
            *common_flags,
            "-Wl,--no-relax",
            "-Wl,-m,elf32lriscv",
            "-T",
            str(link_ld),
            *[str(o) for o in objects],
            "-o",
            str(elf),
        ],
        check=True,
    )

    bin_file = build_dir / "fence_i_smoke.bin"
    subprocess.run(
        ["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(bin_file)],
        check=True,
    )
    subprocess.run(["truncate", "-s", "2048", str(bin_file)], check=True)

    hex_file = build_dir / "fence_i_smoke.hex"
    subprocess.run(
        [
            "riscv64-unknown-elf-objcopy",
            "-I",
            "binary",
            "-O",
            "verilog",
            "--verilog-data-width=4",
            "--reverse-bytes=4",
            str(bin_file),
            str(hex_file),
        ],
        check=True,
    )
    return hex_file


@cocotb.test()
async def test_fence_i_self_modifying_code(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    done_seen = False

    for _cycle in range(20_000):
        await RisingEdge(dut.clk)
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value) & 0xFFFFFFFF
            mem_writes[addr] = data
            if addr == DONE_ADDR and (data & 0xFF) == 1:
                done_seen = True
                break

    assert done_seen, "FENCE.I test program did not finish"
    got = mem_writes.get(RESULT_ADDR)
    assert got == 1, f"Expected patched instruction result 1 at 0x{RESULT_ADDR:08x}, got {got}"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sim_dir = repo_root / "sim"
    incl_dir = rtl_dir / "include"

    sources = []
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith((".v", ".sv")):
                sources.append(os.path.join(root, file))

    build_dir = Path.cwd() / "build"
    hex_file = compile_fence_i_asm(build_dir, sim_dir)
    print(f"Compiled hex: {hex_file}")

    sim_build = Path.cwd() / "sim_build" / "sim_build_fence_i"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_fence_i_behavior",
        testcase="test_fence_i_self_modifying_code",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{hex_file}"'],
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
