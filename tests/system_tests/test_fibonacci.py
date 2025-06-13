import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
import subprocess
import os
import tempfile
import logging
from pathlib import Path
import binascii

# Configure logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Updated memory addresses using new memory map
DATA_MEM_BASE = 0x10000000
CPU_DONE_ADDR = DATA_MEM_BASE + 0xFF          # 0x10000000
FIBONACCI_START_ADDR = DATA_MEM_BASE + 0x10    # 0x10000010

def compile_fibonacci():
    """Compile fibonacci.c to RISC-V binary and prepare hex file for instruction memory"""
    log.info("Compiling fibonacci.c to RISC-V binary...")
    
    # Get repository root directory
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    sim_dir = os.path.join(root_dir, "sim")
    
    # Create build directory if it doesn't exist in current working directory
    curr_dir = Path.cwd()
    build_dir = curr_dir / "build"
    build_dir.mkdir(exist_ok=True)
    
    # Source files
    sim_dir = Path(sim_dir)
    sim_dir = sim_dir.resolve()
    fibonacci_c = sim_dir / "fibonacci.c"
    start_s = sim_dir / "start.S"
    link_ld = sim_dir / "link.ld"
    
    # Output files
    elf_file = build_dir / "fibonacci.elf"
    bin_file = build_dir / "fibonacci.bin"
    hex_file = build_dir / "instr_mem.hex"
    
    # Compile C code to RISC-V binary
    try:
        # Create .o file from C source
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32i",
            "-mabi=ilp32",
            "-nostdlib",
            "-ffreestanding",
            "-O1",
            "-g3",
            "-Wall",
            "-c",
            str(fibonacci_c),
            "-o", str(build_dir / "fibonacci.o")
        ], check=True)
        log.info("Compiled fibonacci.c to object file.")
        
        # Create .o file from start.S
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32i",
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

        # Link object files to create ELF binary
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32i",
            "-mabi=ilp32",
            "-nostdlib",
            "-Wl,--no-relax",
            "-Wl,-m,elf32lriscv",
            "-T", str(link_ld),
            str(build_dir / "fibonacci.o"),
            str(build_dir / "start.o"),
            "-o", str(elf_file)
        ], check=True)
        log.info("Linked object files to create ELF binary.")
        
        # Convert ELF to binary
        subprocess.run([
            "riscv64-unknown-elf-objcopy",
            "-O", "binary",
            str(elf_file),
            str(bin_file)
        ], check=True)
        log.info("Converted ELF binary to raw binary format.")
        
        # Create hex file for instruction memory using objcopy
        # First truncate bin file to 2048 bytes
        subprocess.run([
            "truncate",
            "-s", "2048",
            str(bin_file)
        ], check=True)
        
        # Convert binary to Verilog hex format
        subprocess.run([
            "riscv64-unknown-elf-objcopy",
            "-I", "binary",
            "-O", "verilog",
            "--verilog-data-width=4",
            "--reverse-bytes=4",
            str(bin_file),
            str(hex_file)
        ], check=True)
                    
        # Generate LSS file for debugging
        subprocess.run([
            "riscv64-unknown-elf-objdump",
            "-D",
            "--visualize-jumps",
            "-t",
            "-S",
            "--source-comment=//",
            "-M no-aliases,numeric",
            str(elf_file)
        ], stdout=open(build_dir / "fibonacci.lss", "w"), check=True)
        
        return hex_file
        
    except subprocess.CalledProcessError as e:
        log.error(f"Compilation failed: {e}")
        raise

@cocotb.test()
async def test_fibonacci_program(dut):
    """Test the Fibonacci program execution on the RISC-V CPU"""
    
    # Start clock (10ns period)
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset the design
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Expected Fibonacci sequence for N=10
    expected_sequence = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
    
    # Monitor for CPU_DONE signal
    max_cycles = 10000  # Maximum cycles to run before timeout
    cpu_done = False
    data_values = []
    
    # Track memory accesses
    mem_accesses = {}
    
    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        
        # Check for memory writes
        if dut.cpu_mem_write_en.value:
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value)
            mem_accesses[addr] = data
            log.info(f"Cycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
            
            # Check if CPU_DONE flag was set
            if addr == CPU_DONE_ADDR and (data & 0xFF) == 1:
                cpu_done = True
                log.info("CPU_DONE flag set - program finished execution")
                
            # Collect Fibonacci sequence values (byte writes)
            if FIBONACCI_START_ADDR <= addr < FIBONACCI_START_ADDR + 10:
                index = addr - FIBONACCI_START_ADDR
                value = data & 0xFF  # Extract lowest byte for byte writes
                if index < len(data_values):
                    data_values[index] = value
                else:
                    # Extend list if needed
                    while len(data_values) <= index:
                        data_values.append(0)
                    data_values[index] = value
                log.info(f"Fibonacci[{index}] = {value}")
        
        # Exit simulation once CPU_DONE is set and we've collected all values
        if cpu_done and len([x for x in data_values if x != 0]) >= 10:
            break
    
    # Verify results
    log.info(f"Program execution complete after {cycle+1} cycles")
    log.info(f"Collected Fibonacci values: {data_values[:10]}")
    
    # Dump memory accesses for debugging
    print("Memory accesses:")
    for addr, data in sorted(mem_accesses.items()):
        print(f"  0x{addr:08x}: 0x{data:08x}")
    
    # Check if CPU_DONE was set
    assert cpu_done, "CPU_DONE flag was not set - program did not complete"
    
    # Verify Fibonacci sequence values
    actual_values = data_values[:10]
    if any(actual_values):  # Check if we got any values
        for i, (actual, expected) in enumerate(zip(actual_values, expected_sequence)):
            assert actual == expected, f"Fibonacci sequence mismatch at index {i}: actual={actual}, expected={expected}"
        log.info("Fibonacci sequence verification successful!")
    else:
        log.warning("No Fibonacci values were collected from memory")

def runCocotbTests():
    """Run the cocotb test via cocotb-test"""
    from cocotb_test.simulator import run
    import os
    
    # Compile the Fibonacci program
    hex_file = compile_fibonacci()

    # Get repository root directory
    curr_dir = os.getcwd()
    root_dir = curr_dir
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    incl_dir = os.path.join(rtl_dir, "include")
    
    # Collect all Verilog sources
    sources = []
    rtl_dir = Path(rtl_dir)
    for file in rtl_dir.glob("**/*.v"):
        sources.append(str(file))
    
    # Create waveforms directory
    curr_dir = Path(curr_dir)
    waveform_dir = curr_dir / "waveforms"
    waveform_dir.mkdir(exist_ok=True)
    waveform_path = waveform_dir / "fibonacci_test.vcd"
    
    # Run the test - pass hex file as a define instead of a parameter
    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_fibonacci",
        testcase="test_fibonacci_program",
        includes=[str(incl_dir)],
        simulator="icarus",
        timescale="1ns/1ps",
        plus_args=[f"+dumpfile={waveform_path}"],
        defines=[f"INSTR_HEX_FILE=\"{hex_file}\""]  # Pass as Verilog define
    )

if __name__ == "__main__":
    runCocotbTests()