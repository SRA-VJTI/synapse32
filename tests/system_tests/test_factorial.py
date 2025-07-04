import cocotb
from cocotb.triggers import RisingEdge, ClockCycles
from cocotb.clock import Clock
import logging
from pathlib import Path
import subprocess
import os

data_mem_base = 0x10000000
cpu_done_addr = data_mem_base + 0xFF
factorial_addr = data_mem_base + 0x20

# Configure logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

def compile_factorial():
    """Compile factorial.c to RISC-V binary and prepare hex file for instruction memory"""
    log.info("Compiling factorial.c to RISC-V binary...")
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    sim_dir = os.path.join(root_dir, "sim")
    curr_dir = Path.cwd()
    build_dir = curr_dir / "build"
    build_dir.mkdir(exist_ok=True)
    sim_dir = Path(sim_dir).resolve()
    factorial_c = sim_dir / "factorial.c"
    start_s = sim_dir / "start.S"
    link_ld = sim_dir / "link.ld"
    elf_file = build_dir / "factorial.elf"
    bin_file = build_dir / "factorial.bin"
    hex_file = build_dir / "instr_mem.hex"
    try:
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32im",
            "-mabi=ilp32",
            "-nostdlib",
            "-ffreestanding",
            "-O1",
            "-g3",
            "-Wall",
            "-c",
            str(factorial_c),
            "-o", str(build_dir / "factorial.o")
        ], check=True)
        log.info("Compiled factorial.c to object file.")
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32im",
            "-mabi=ilp32",
            "-nostdlib",
            "-ffreestanding",
            "-O3",
            "-g3",
            "-Wall",
            "-c",
            str(start_s),
            "-o", str(build_dir / "start.o")
        ], check=True)
        log.info("Compiled start.S to object file.")
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32im",
            "-mabi=ilp32",
            "-nostdlib",
            "-Wl,--no-relax",
            "-Wl,-m,elf32lriscv",
            "-T", str(link_ld),
            str(build_dir / "factorial.o"),
            str(build_dir / "start.o"),
            "-o", str(elf_file)
        ], check=True)
        log.info("Linked object files to create ELF binary.")
        subprocess.run([
            "riscv64-unknown-elf-objcopy",
            "-O", "binary",
            str(elf_file),
            str(bin_file)
        ], check=True)
        log.info("Converted ELF binary to raw binary format.")
        subprocess.run([
            "truncate",
            "-s", "2048",
            str(bin_file)
        ], check=True)
        subprocess.run([
            "riscv64-unknown-elf-objcopy",
            "-I", "binary",
            "-O", "verilog",
            "--verilog-data-width=4",
            "--reverse-bytes=4",
            str(bin_file),
            str(hex_file)
        ], check=True)
        subprocess.run([
            "riscv64-unknown-elf-objdump",
            "-D",
            "--visualize-jumps",
            "-t",
            "-S",
            "--source-comment=//",
            "-M", "no-aliases,numeric",
            str(elf_file)
        ], stdout=open(build_dir / "factorial.lss", "w"), check=True)
        return hex_file
    except subprocess.CalledProcessError as e:
        log.error(f"Compilation failed: {e}")
        raise

@cocotb.test()
async def test_factorial_program(dut):
    """Test the Factorial program execution and M extension ops on the RISC-V CPU"""
    cocotb.log.info("Starting cocotb test: test_factorial_program")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    cocotb.log.info("Clock started")
    dut.rst.value = 1
    cocotb.log.info("Reset asserted")
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    cocotb.log.info("Reset deasserted")
    max_cycles = 10000
    cpu_done = False
    result = None
    dummy = None
    mem_accesses = {}
    cocotb.log.info("Entering simulation loop")
    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        if cycle % 1000 == 0:
            cocotb.log.info(f"Cycle {cycle}...")
        if dut.cpu_mem_write_en.value:
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value)
            mem_accesses[addr] = data
            cocotb.log.info(f"Cycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
            if addr == cpu_done_addr and (data & 0xFF) == 1:
                cpu_done = True
                cocotb.log.info("CPU_DONE flag set - program finished execution")
            if addr == factorial_addr:
                result = data
                cocotb.log.info(f"Factorial result written: {result}")
            if addr == factorial_addr + 4:
                dummy = data
                cocotb.log.info(f"Dummy value written: {dummy}")
                # Print out each step of the M extension tests
                cocotb.log.info("--- M Extension Step Results ---")
                cocotb.log.info(f"Factorial (MUL) result: {result}")
                cocotb.log.info(f"Dummy (MULH, MULHSU, MULHU, DIV, DIVU, REM, REMU sum): {dummy}")
        if cpu_done and result is not None and dummy is not None:
            cocotb.log.info(f"Exiting simulation loop at cycle {cycle}")
            break
    cocotb.log.info(f"Program execution complete after {cycle+1} cycles")
    cocotb.log.info(f"Factorial result: {result}")
    cocotb.log.info(f"Dummy value: {dummy}")
    print("Memory accesses:")
    for addr, data in sorted(mem_accesses.items()):
        print(f"  0x{addr:08x}: 0x{data:08x}")
    assert cpu_done, "CPU_DONE flag was not set - program did not complete"
    assert result == 720, f"Factorial result mismatch: got {result}, expected 720"
    cocotb.log.info("Factorial and M extension test successful!")

def runCocotbTests():
    from cocotb_test.simulator import run
    import os
    hex_file = compile_factorial()
    curr_dir = os.getcwd()
    root_dir = curr_dir
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    incl_dir = os.path.join(rtl_dir, "include")
    sources = []
    rtl_dir = Path(rtl_dir)
    for file in rtl_dir.glob("**/*.v"):
        sources.append(str(file))
    curr_dir = Path(curr_dir)
    waveform_dir = curr_dir / "waveforms"
    waveform_dir.mkdir(exist_ok=True)
    waveform_path = waveform_dir / "factorial_test.vcd"
    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_factorial",
        testcase="test_factorial_program",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        plus_args=[f"+dumpfile={waveform_path}"],
        defines=[f"INSTR_HEX_FILE=\"{hex_file}\""]
    )

if __name__ == "__main__":
    runCocotbTests()
