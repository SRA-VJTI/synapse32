"""Compile sim/timer_irq.S, run it on the core in Verilator, and verify the
machine-mode timer interrupt handler fires and mret returns cleanly.
"""
import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb_test.simulator import run


HANDLER_MARKER_ADDR = 0x10000000
HANDLER_COUNT_ADDR  = 0x10000004
POLL_RESULT_ADDR    = 0x10000008
CPU_DONE_ADDR       = 0x100000FF
SENTINEL            = 0xDEADBEEF


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def compile_asm(s_file: Path, build_dir: Path, sim_dir: Path) -> Path:
    """Assemble + link s_file (plus sim/start.S) through the RISC-V toolchain
    and return the path to the verilog-hex image for instr_mem.
    """
    build_dir.mkdir(parents=True, exist_ok=True)

    start_s = sim_dir / "start.S"
    link_ld = sim_dir / "link.ld"
    for required in (start_s, link_ld, s_file):
        if not required.exists():
            raise FileNotFoundError(f"Required file missing: {required}")

    common_flags = [
        "-march=rv32i_zicsr_zifencei",
        "-mabi=ilp32",
        "-nostdlib",
        "-ffreestanding",
    ]

    objects = []
    for src in (start_s, s_file):
        obj = build_dir / f"{src.stem}.o"
        subprocess.run(
            ["riscv64-unknown-elf-gcc", *common_flags, "-c", str(src), "-o", str(obj)],
            check=True,
        )
        objects.append(obj)

    elf = build_dir / f"{s_file.stem}.elf"
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", *common_flags,
            "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(link_ld),
            *[str(o) for o in objects],
            "-o", str(elf),
        ],
        check=True,
    )

    bin_file = build_dir / f"{s_file.stem}.bin"
    subprocess.run(
        ["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(bin_file)],
        check=True,
    )

    # Pad to a fixed size so $readmemh sees a stable image.
    subprocess.run(["truncate", "-s", "2048", str(bin_file)], check=True)

    hex_file = build_dir / f"{s_file.stem}.hex"
    subprocess.run(
        [
            "riscv64-unknown-elf-objcopy",
            "-I", "binary", "-O", "verilog",
            "--verilog-data-width=4", "--reverse-bytes=4",
            str(bin_file), str(hex_file),
        ],
        check=True,
    )

    # Disassembly for when this inevitably needs debugging.
    lss_file = build_dir / f"{s_file.stem}.lss"
    with open(lss_file, "w") as f:
        subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", "-S", str(elf)],
            stdout=f, check=True,
        )

    return hex_file


@cocotb.test()
async def test_timer_irq(dut):
    """Run timer_irq.S and verify the handler fires + program signals done."""
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    handler_fired_cycle = None
    done_cycle = None
    max_cycles = 50_000

    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value)
            mem_writes[addr] = data

            if addr == HANDLER_MARKER_ADDR and data == SENTINEL and handler_fired_cycle is None:
                handler_fired_cycle = cycle
                print(f"Cycle {cycle}: timer handler wrote sentinel to 0x{addr:08x}")

            if addr == CPU_DONE_ADDR and (data & 0xFF) == 1:
                done_cycle = cycle
                print(f"Cycle {cycle}: CPU_DONE asserted")
                break

    assert handler_fired_cycle is not None, (
        "Timer interrupt handler never wrote the sentinel - "
        "check mtvec dispatch, mtimecmp, MTIE/MIE enable."
    )
    assert done_cycle is not None, (
        "Program never asserted CPU_DONE - mret likely did not return to the "
        "instruction after the poll loop."
    )

    handler_count = mem_writes.get(HANDLER_COUNT_ADDR, 0)
    print(f"Handler fired {handler_count} time(s). Done at cycle {done_cycle}.")
    assert handler_count >= 1, f"handler count counter = {handler_count}"
    assert mem_writes.get(POLL_RESULT_ADDR) == SENTINEL, (
        "Polling loop did not retain its registers across the timer handler"
    )


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
    hex_file = compile_asm(sim_dir / "timer_irq.S", build_dir, sim_dir)
    print(f"Compiled hex: {hex_file}")

    enable_waves = os.getenv("WAVES", "0") == "1"
    plus_args = []
    if enable_waves:
        waveform_dir = Path.cwd() / "waveforms"
        waveform_dir.mkdir(exist_ok=True)
        plus_args = [f"+dumpfile={waveform_dir / 'timer_irq.vcd'}"]

    sim_build = Path.cwd() / "sim_build" / "sim_build_timer_irq"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_timer_irq",
        testcase="test_timer_irq",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{hex_file}"'],
        plus_args=plus_args,
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
