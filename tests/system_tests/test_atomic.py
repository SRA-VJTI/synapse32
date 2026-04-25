"""Compile and run an RV32A program that exercises all atomic ops.

Coverage:
- LR/SC success path
- LR/SC failure path
- AMOSWAP/AMOADD/AMOAND/AMOOR/AMOXOR/AMOMAX/AMOMIN/AMOMAXU/AMOMINU
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
DONE_ADDR = BASE + 0xFF


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def compile_atomic_asm(build_dir: Path, sim_dir: Path) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)

    src = build_dir / "atomic_smoke.S"
    src.write_text(
        """
        .section .text
        .global main
        .type main, @function
main:
        li t0, 0x10000000
        # LR/SC success
        li t1, 5
        sw t1, 0(t0)
        lr.w t2, (t0)
        li t3, 9
        sc.w t4, t3, (t0)
        lr.w t5, (t0)
        sw t2, 0x200(t0)      # expected 5
        sw t4, 0x204(t0)      # expected 0 (success)
        sw t5, 0x208(t0)      # expected 9

        # LR/SC failure after reservation invalidation by normal store
        addi t6, t0, 0x10
        li t1, 0x33
        sw t1, 0(t6)
        lr.w t2, (t6)
        li t3, 0x44
        sw t3, 0(t6)          # should clear reservation
        li t1, 0x55
        sc.w t4, t1, (t6)
        lw t5, 0(t6)
        sw t4, 0x20c(t0)      # expected 1 (failure)
        sw t5, 0x210(t0)      # expected 0x44

        # AMOSWAP.W
        addi t6, t0, 0x20
        li t1, 0x11111111
        sw t1, 0(t6)
        li t2, 0x22222222
        amoswap.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x214(t0)      # old
        sw t4, 0x218(t0)      # new

        # AMOADD.W
        addi t6, t0, 0x24
        li t1, 10
        sw t1, 0(t6)
        li t2, 7
        amoadd.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x21c(t0)
        sw t4, 0x220(t0)

        # AMOAND.W
        addi t6, t0, 0x28
        li t1, 0xf0f0aa55
        sw t1, 0(t6)
        li t2, 0x0ff00f0f
        amoand.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x224(t0)
        sw t4, 0x228(t0)

        # AMOOR.W
        addi t6, t0, 0x2c
        li t1, 0x12340000
        sw t1, 0(t6)
        li t2, 0x0000abcd
        amoor.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x22c(t0)
        sw t4, 0x230(t0)

        # AMOXOR.W
        addi t6, t0, 0x30
        li t1, 0xffff0000
        sw t1, 0(t6)
        li t2, 0x00ff00ff
        amoxor.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x234(t0)
        sw t4, 0x238(t0)

        # AMOMAX.W (signed): max(-5, 3) -> 3
        addi t6, t0, 0x34
        li t1, -5
        sw t1, 0(t6)
        li t2, 3
        amomax.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x23c(t0)
        sw t4, 0x240(t0)

        # AMOMIN.W (signed): min(5, -3) -> -3
        addi t6, t0, 0x38
        li t1, 5
        sw t1, 0(t6)
        li t2, -3
        amomin.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x244(t0)
        sw t4, 0x248(t0)

        # AMOMAXU.W (unsigned): max(1, 0xffffffff) -> 0xffffffff
        addi t6, t0, 0x3c
        li t1, 1
        sw t1, 0(t6)
        li t2, -1
        amomaxu.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x24c(t0)
        sw t4, 0x250(t0)

        # AMOMINU.W (unsigned): min(0xfffffffe, 2) -> 2
        addi t6, t0, 0x40
        li t1, -2
        sw t1, 0(t6)
        li t2, 2
        amominu.w t3, t2, (t6)
        lw t4, 0(t6)
        sw t3, 0x254(t0)
        sw t4, 0x258(t0)

        li a1, 1
        sb a1, 0xff(t0)
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

    elf = build_dir / "atomic_smoke.elf"
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

    bin_file = build_dir / "atomic_smoke.bin"
    subprocess.run(
        ["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(bin_file)],
        check=True,
    )
    subprocess.run(["truncate", "-s", "2048", str(bin_file)], check=True)

    hex_file = build_dir / "atomic_smoke.hex"
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
async def test_atomic_smoke(dut):
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    done_seen = False
    max_cycles = 20_000

    prev_pc = None
    prev_instr = None
    atomic_stall_seen = False

    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)

        pc = int(dut.pc_debug.value)
        instr = int(dut.instr_debug.value)
        opcode = instr & 0x7F
        is_atomic_fetch = opcode == 0x2F
        if prev_pc is not None and pc == prev_pc and is_atomic_fetch and prev_instr == instr:
            atomic_stall_seen = True
        prev_pc = pc
        prev_instr = instr

        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value)
            mem_writes[addr] = data
            if addr == DONE_ADDR and (data & 0xFF) == 1:
                done_seen = True
                break

    assert done_seen, "Atomic test program did not finish"

    expected = {
        BASE + 0x200: 0x00000005,  # lr.w old value
        BASE + 0x204: 0x00000000,  # sc.w success code
        BASE + 0x208: 0x00000009,  # second lr.w sees new value
        BASE + 0x20C: 0x00000001,  # sc.w failure code
        BASE + 0x210: 0x00000044,  # failed sc must not update memory
        BASE + 0x214: 0x11111111,  # amoswap old
        BASE + 0x218: 0x22222222,  # amoswap new
        BASE + 0x21C: 0x0000000A,  # amoadd old
        BASE + 0x220: 0x00000011,  # amoadd new
        BASE + 0x224: 0xF0F0AA55,  # amoand old
        BASE + 0x228: 0x00F00A05,  # amoand new
        BASE + 0x22C: 0x12340000,  # amoor old
        BASE + 0x230: 0x1234ABCD,  # amoor new
        BASE + 0x234: 0xFFFF0000,  # amoxor old
        BASE + 0x238: 0xFF0000FF,  # amoxor new
        BASE + 0x23C: 0xFFFFFFFB,  # amomax old
        BASE + 0x240: 0x00000003,  # amomax new
        BASE + 0x244: 0x00000005,  # amomin old
        BASE + 0x248: 0xFFFFFFFD,  # amomin new
        BASE + 0x24C: 0x00000001,  # amomaxu old
        BASE + 0x250: 0xFFFFFFFF,  # amomaxu new
        BASE + 0x254: 0xFFFFFFFE,  # amominu old
        BASE + 0x258: 0x00000002,  # amominu new
    }

    for addr, exp in expected.items():
        got = mem_writes.get(addr)
        assert got == exp, f"Memory[0x{addr:08x}] expected 0x{exp:08x}, got {got}"

    if not atomic_stall_seen:
        print("Note: no observable fetch stall during atomic execution on this microarchitecture.")


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
    hex_file = compile_atomic_asm(build_dir, sim_dir)
    print(f"Compiled hex: {hex_file}")

    sim_build = Path.cwd() / "sim_build" / "sim_build_atomic"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_atomic",
        testcase="test_atomic_smoke",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{hex_file}"'],
        sim_build=str(sim_build),
        force_compile=True,
    )


if __name__ == "__main__":
    runCocotbTests()
