import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
import subprocess
import os
import logging
from pathlib import Path
from cocotb.utils import get_sim_time
from decimal import Decimal

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

DATA_MEM_BASE = 0x10000000
CPU_DONE_ADDR = DATA_MEM_BASE + 0xFF          # 0x100000FF

class UartMonitor:
    """Monitor the UART TX line and decode transmitted bytes"""
    def __init__(self, uart_tx, clk, cpu_clock_freq=100_000_000):
        self.tx = uart_tx
        self.clk = clk
        # Your C code sets baud divisor to 5208 for 50MHz clock -> 9600 baud
        # But we're running at 100MHz, so effective baud rate is different
        # Baud rate = cpu_clock_freq / 5208
        actual_baud_rate = cpu_clock_freq / 5208
        self.baud_period_cycles = int(cpu_clock_freq / actual_baud_rate)
        self.received_bytes = []
        self.monitoring = True
        log.debug(f"UART Monitor initialized:")
        log.debug(f"  CPU clock: {cpu_clock_freq} Hz")
        log.debug(f"  Baud divisor: 5208 (from C code)")
        log.debug(f"  Actual baud rate: {actual_baud_rate:.1f} Hz")
        log.debug(f"  Bit period: {self.baud_period_cycles} cycles")
        
    async def start_monitoring(self):
        """Start monitoring the UART TX line"""
        while self.monitoring:
            # Wait for TX line to go low (start bit)
            while self.tx.value != 0:
                await RisingEdge(self.clk)
                if not self.monitoring:
                    return
            current_time = get_sim_time(units="ns")
            log.debug(f"Start bit detected at time: {current_time}")
            
            # Wait to center of first data bit (1.5 bit periods from start bit edge)
            await Timer(Decimal(self.baud_period_cycles * 1.5 * 10), units="ns")
            
            # Sample data bits (LSB first)
            rx_byte = 0
            for bit_num in range(8):
                bit_value = int(self.tx.value)
                rx_byte |= (bit_value << bit_num)
                current_time = get_sim_time(units="ns")
                log.debug(f"Bit {bit_num}: {bit_value} (byte so far: 0x{rx_byte:02x}) at time: {current_time}")
                
                # Wait one full bit period to get to the center of the next bit
                if bit_num < 7:
                    await Timer(Decimal(self.baud_period_cycles * 10), units="ns")
            
            # Wait for stop bit
            await Timer(Decimal(self.baud_period_cycles * 10), units="ns")
            current_time = get_sim_time(units="ns")
            log.debug(f"Stop bit received at time: {current_time}, RX byte: 0x{rx_byte:02x}")
            
            # Store received byte
            self.received_bytes.append(rx_byte)
            char = chr(rx_byte) if 32 <= rx_byte <= 126 else f'\\x{rx_byte:02x}'
            log.debug(f"UART received: 0x{rx_byte:02x} ('{char}')")
            
    def get_received_string(self) -> str:
        """Decode all received bytes as ASCII, so CR/LF come through as real chars."""
        # build a bytes object then decode
        return bytes(self.received_bytes).decode('ascii', errors='replace')

    def stop_monitoring(self):
        """Stop the UART monitoring"""
        self.monitoring = False

def compile_c_files(c_files):
    log.info("Compiling input C files into one binary")

    curr_dir = Path.cwd()
    build_dir = curr_dir / "build"
    build_dir.mkdir(exist_ok=True)

    sim_dir = curr_dir
    sim_dir = sim_dir.resolve()
    start_s = sim_dir / "start.S"
    if not start_s.exists():
        raise FileNotFoundError(f"start.s not found in {sim_dir}. Please ensure it exists.")
    link_ld = sim_dir / "link.ld"
    if not link_ld.exists():
        raise FileNotFoundError(f"link.ld not found in {sim_dir}. Please ensure it exists.")
    
    #compile all C files into a single binary
    object_files = []
    for c_file in c_files:
        if not c_file.exists():
            raise FileNotFoundError(f"C file {c_file} does not exist.")
        object_file = build_dir / f"{c_file.stem}.o"
        subprocess.run([
            "riscv64-unknown-elf-gcc",
            "-march=rv32i_zicsr_zifencei",
            "-mabi=ilp32",
            "-nostdlib",
            "-ffreestanding",
            "-O1",
            "-g3",
            "-Wall",
            "-c",
            str(c_file),
            "-o", str(object_file)
        ], check=True)
        log.info(f"Compiled {c_file} to {object_file}")
        object_files.append(object_file)

    # Create .o file from start.s
    start_o = build_dir / "start.o"
    subprocess.run([
        "riscv64-unknown-elf-gcc",
        "-march=rv32i_zicsr_zifencei",
        "-mabi=ilp32",
        "-nostdlib",
        "-ffreestanding",
        "-O3",
        "-g3",
        "-Wall",
        "-c",
        str(start_s),
        "-o", str(start_o)
    ], check=True)
    log.info(f"Compiled {start_s} to {start_o}")
    object_files.append(start_o)

    # Link object files to create ELF binary
    elf_file = build_dir / "output.elf"
    subprocess.run([
        "riscv64-unknown-elf-gcc",
        "-march=rv32i_zicsr_zifencei",
        "-mabi=ilp32",
        "-nostdlib",
        "-Wl,--no-relax",
        "-Wl,-m,elf32lriscv",
        "-T", str(link_ld),
        *[str(obj) for obj in object_files],
        "-o", str(elf_file)
    ], check=True)
    log.info(f"Linked object files to create ELF binary: {elf_file}")

    # Convert ELF to binary
    bin_file = build_dir / "output.bin"
    subprocess.run([
        "riscv64-unknown-elf-objcopy",
        "-O", "binary",
        str(elf_file),
        str(bin_file)
    ], check=True)
    log.info(f"Converted ELF to binary: {bin_file}")

    # Truncate bin file to 2048 bytes
    subprocess.run([
        "truncate",
        "-s", "2048",
        str(bin_file)
    ], check=True)
    log.info(f"Truncated binary file to 2048 bytes: {bin_file}")

    # Create hex file for instruction memory using objcopy
    hex_file = build_dir / "output.hex"
    subprocess.run([
        "riscv64-unknown-elf-objcopy",
        "-I", "binary",
        "-O", "verilog",
        "--verilog-data-width=4",
        "--reverse-bytes=4",
        str(bin_file),
        str(hex_file)
    ], check=True)
    log.info(f"Converted binary to Verilog hex format: {hex_file}")

    # Generate LSS file for debugging
    lss_file = build_dir / "output.lss"
    subprocess.run([
        "riscv64-unknown-elf-objdump",
        "-D",
        "--visualize-jumps",
        "-t",
        "-S",
        "--source-comment=//",
        "-M no-aliases,numeric",
        str(elf_file)
    ], stdout=open(lss_file, "w"), check=True)
    log.info(f"Generated LSS file for debugging: {lss_file}")
    return bin_file, hex_file, lss_file

@cocotb.test
async def run_c_code(dut):
    """Run the C code in the DUT and monitor UART output"""
    #configure logging since cocotb does not automatically configure it
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)
    log.info("Cocotb test started")
    log.info("Starting C code simulation")

    # Set up clock
    clk = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clk.start())

    # Reset the DUT
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, cpu_clock_freq=100_000_000)
    monitor_task = cocotb.start_soon(uart_monitor.start_monitoring())

    log.info("UART monitor started")

    # Monitor for CPU_DONE signal
    max_cycles = 5000000  # Maximum cycles to run before timeout
    cpu_done = False
    
    # Track memory accesses
    mem_accesses = {}

    spinner = ['|', '/', '-', '\\']
    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        
        # Check for memory writes
        if dut.cpu_mem_write_en.value:
            addr = int(dut.cpu_mem_write_addr.value)
            data = int(dut.cpu_mem_write_data.value)
            mem_accesses[addr] = data
            
            # Only log important memory writes to reduce noise
            if addr == CPU_DONE_ADDR or (addr >= DATA_MEM_BASE and addr < DATA_MEM_BASE + 0x20):
                log.info(f"\nCycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
            
            # Check if CPU_DONE flag was set
            if addr == CPU_DONE_ADDR and (data & 0xFF) == 1:
                cpu_done = True
                log.info("\nCPU_DONE flag set - program finished execution")
                break
        
        if cycle % 10000 == 0:
            print(f"\rSimulating... {spinner[(cycle // 10000) % len(spinner)]} (cycle {cycle})", end='', flush=True)
    print()
    
    if cpu_done:
        log.info("C code execution completed successfully")
        log.info("Waiting for UART monitor to finish...")
        uart_monitor.stop_monitoring()
        await monitor_task  # Ensure UART monitoring task completes
        log.info("UART monitoring completed")
    elif cycle >= max_cycles - 1:
        log.warning("Maximum cycle limit reached without CPU_DONE signal. Simulation may be incomplete.")
    else:        log.error("Unexpected termination of simulation. CPU_DONE signal not detected.")
    
    received_string = uart_monitor.get_received_string()

    log.info("Program Execution Summary:")
    log.info(f"Total cycles executed: {cycle + 1}")
    log.info("Received UART output:")
    log.info("=" * 40)
    log.info("\n%s", received_string)
    log.info("=" * 40)
    log.debug(f"Memory accesses: {len(mem_accesses)} unique addresses")
    for addr, data in mem_accesses.items():
        log.debug(f"  Address 0x{addr:08x}: Data 0x{data:08x}")
    log.info("Simulation completed")

def runMakefile():
    """Run the Makefile to start the simulation"""
    log.info("Running Makefile to start simulation")
    makefile_path = Path.cwd() / "c_runner.mk"
    # delete sim_build directory if it exists by running cocotb-clean
    sim_build_dir = Path.cwd() / "sim_build"
    if sim_build_dir.exists():
        log.info(f"Deleting existing sim_build directory: {sim_build_dir}")
        subprocess.run(["cocotb-clean"], check=True)
    if not makefile_path.exists():
        raise FileNotFoundError(f"Makefile not found at {makefile_path}. Please ensure it exists.")
    
    subprocess.run(["make", "-f", str(makefile_path)], check=True)
    log.info("Makefile executed successfully")

if __name__ == "__main__":
    # Read C files from command line arguments
    import sys
    if len(sys.argv) < 2:
        log.error("No C files provided. Usage: python run_c_code.py <c_file1> <c_file2> ...")
        sys.exit(1)
    c_files = [Path(arg) for arg in sys.argv[1:]]
    if not all(c_file.exists() for c_file in c_files):
        log.error("One or more C files do not exist. Please check the paths.")
        sys.exit(1)
    try:
        bin_file, hex_file, lss_file = compile_c_files(c_files)
        log.info(f"Compiled binary: {bin_file}")
        log.info(f"Hex file for instruction memory: {hex_file}")
        log.info(f"LSS file for debugging: {lss_file}")
        
        # Set environment variable for hex file
        os.environ["INSTRUCTION_MEMORY_HEX"] = str(hex_file)
        log.info(f"Set INSTRUCTION_MEMORY_HEX environment variable to {hex_file}")
        runMakefile()
    except subprocess.CalledProcessError as e:
        log.error(f"Error during compilation or simulation: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        sys.exit(1)