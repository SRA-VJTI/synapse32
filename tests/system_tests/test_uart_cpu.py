import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
import logging
import os
from pathlib import Path
from cocotb.utils import get_sim_time

# Configure logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


async def uart_send_byte(dut, byte, baud_cycles=None):
    """Drive one 8N1 byte using the divisor currently programmed in the DUT."""
    if baud_cycles is None:
        baud_cycles = int(dut.uart_inst.baud_div.value) + 1
    dut.uart_rx.value = 0
    await ClockCycles(dut.clk, baud_cycles)
    for bit in range(8):
        dut.uart_rx.value = (byte >> bit) & 1
        await ClockCycles(dut.clk, baud_cycles)
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, baud_cycles)

# NS16550 UART register addresses (reg_shift=2, 4-byte offsets)
UART_BASE    = 0x20000000
UART_THR     = UART_BASE + 0x00  # Transmit Holding Register (DLAB=0)
UART_IER     = UART_BASE + 0x04  # Interrupt Enable Register
UART_FCR     = UART_BASE + 0x08  # FIFO Control Register
UART_LCR     = UART_BASE + 0x0C  # Line Control Register (bit7=DLAB)
UART_MCR     = UART_BASE + 0x10  # Modem Control Register
UART_LSR     = UART_BASE + 0x14  # Line Status Register (bit5=THRE)
# Legacy aliases kept for any remaining references
UART_DATA    = UART_THR
UART_STATUS  = UART_LSR

class UartMonitor:
    """Monitor the UART TX line and decode transmitted bytes"""
    def __init__(self, uart_tx, clk, baud_rate=5000000):
        self.tx = uart_tx
        self.clk = clk
        self.baud_period_cycles = int(50_000_000 / baud_rate)  # Baud period in clock cycles
        self.received_bytes = []
        self.monitoring = True
        print(f"UART Monitor initialized with baud rate: {baud_rate} Hz, period cycles: {self.baud_period_cycles}")
        
    async def start_monitoring(self):
        """Start monitoring the UART TX line"""
        while self.monitoring:
            # Wait for TX line to go low (start bit)
            while self.tx.value != 0:
                await RisingEdge(self.clk)
                current_time = get_sim_time(units="ns")
                if not self.monitoring:
                    return
            current_time = get_sim_time(units="ns")
            print("Start bit detected at time:", current_time)
            
            await Timer((self.baud_period_cycles + 1) * 20, units="ns")
            
            # Sample data bits (LSB first) - we're now at the center of bit 0
            rx_byte = 0
            for bit_num in range(8):
                # Sample the bit (we should be in the center of the bit period)
                bit_value = int(self.tx.value)
                rx_byte |= (bit_value << bit_num)
                current_time = get_sim_time(units="ns")
                print(f"Bit {bit_num}: {bit_value} (0x{rx_byte:02x}) at time: {current_time}")
                
                # Wait one full bit period to get to the center of the next bit
                # (except for the last bit where we don't need to wait)
                if bit_num < 7:
                    await Timer((self.baud_period_cycles + 1) * 20, units="ns")
            
            # Wait one full bit period to get past the stop bit
            await Timer((self.baud_period_cycles + 1) * 20, units="ns")
            current_time = get_sim_time(units="ns")
            print(f"Stop bit received at time: {current_time}, RX byte: 0x{rx_byte:02x}")
            
            # Store received byte
            self.received_bytes.append(rx_byte)
            char = chr(rx_byte) if 32 <= rx_byte <= 126 else f'\\x{rx_byte:02x}'
            log.info(f"UART received: 0x{rx_byte:02x} ('{char}')")
            
    def get_received_string(self):
        """Get the received bytes as a string"""
        return ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in self.received_bytes)

def create_uart_test_hex(test_name, instr_mem):
    """Create a hex file for the UART test instructions"""
    curr_dir = Path.cwd()
    build_dir = curr_dir / "build"
    build_dir.mkdir(exist_ok=True)
    
    hex_file = build_dir / f"{test_name}.hex"
    
    with open(hex_file, 'w') as f:
        f.write("@00000000\n")  # Start address

        # Pad the instruction to ensure we have enough instructions
        padded_instr = list(instr_mem)
        while len(padded_instr) % 4 != 0:
            padded_instr.append(0x00000013)  # NOP instruction

        # Pad to atleast 256 instructions
        while len(padded_instr) < 256:
            padded_instr.append(0x00000013)
        
        # Write instructions as 4 per line
        for i in range(0, len(padded_instr), 4):
            line =  " ".join(f"{padded_instr[j]:08x}" for j in range(i, min(i + 4, len(padded_instr))))
            f.write(f"{line}\n")

    return str(hex_file.absolute())

def run_uart_hello_test():
    """Create assembly program that outputs 'Hello UART!' via UART"""
    
    # UART configuration for fast simulation
    # Baud divisor = 50,000,000 / 5,000,000 = 10 (5 MHz baud rate)
    BAUD_DIVISOR = 10
    
    instr_mem = []
    
    # Main program
    # NS16550 poll loop: lw x1,20(x2); andi x1,x1,32; beq x1,x0,-8
    # Reads LSR (+0x14), checks THRE (bit5=0x20), loops while not ready.
    POLL = [0x01412083, 0x0200f093, 0xfe008ce3]

    main_program = [
        # Initialize registers
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE (0x20000000)
        0x020001b7,  # lui x3, 0x2000        # x3 = 0x02000000 (data memory base)

        # NS16550 init: LCR=0x83 (DLAB=1, 8N1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)         # LCR = 0x83

        # DLL = 10 (baud divisor low byte)
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)          # DLL = 10

        # DLH = 0
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)          # DLH = 0

        # LCR = 0x03 (DLAB=0, 8N1)
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)         # LCR = 0x03

        # FCR = 0x07 (enable + clear FIFOs)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)          # FCR = 0x07

        # Send 'H' (0x48)
        0x04800093,  # addi x1, x0, 72
        0x00112023,  # sw x1, 0(x2)          # THR = 'H'
        *POLL,

        # Send 'e' (0x65)
        0x06500093,  # addi x1, x0, 101
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'l' (0x6C)
        0x06c00093,  # addi x1, x0, 108
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'l' (0x6C)
        0x06c00093,
        0x00112023,
        *POLL,

        # Send 'o' (0x6F)
        0x06f00093,  # addi x1, x0, 111
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send ' ' (0x20)
        0x02000093,  # addi x1, x0, 32
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'U' (0x55)
        0x05500093,  # addi x1, x0, 85
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'A' (0x41)
        0x04100093,  # addi x1, x0, 65
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'R' (0x52)
        0x05200093,  # addi x1, x0, 82
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send 'T' (0x54)
        0x05400093,  # addi x1, x0, 84
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send '!' (0x21)
        0x02100093,  # addi x1, x0, 33
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send '\r' (0x0D)
        0x00d00093,  # addi x1, x0, 13
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Send '\n' (0x0A)
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)
        *POLL,

        # Store completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a023,  # sw x1, 0(x3)

        # Infinite loop
        0x0000006f,  # jal x0, 0
    ]
    
    instr_mem = main_program
    test_name = "uart_hello"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_uart_status_test():
    """Create assembly program that tests UART status register"""
    
    # UART configuration - same baud rate as hello test
    # Baud divisor = 50,000,000 / 5,000,000 = 10 (5 MHz baud rate)
    BAUD_DIVISOR = 10
    
    # NS16550 poll: lw x1,20(x2); andi x1,x1,32; beq x1,x0,-8
    POLL = [0x01412083, 0x0200f093, 0xfe008ce3]

    instr_mem = [
        # Initialize registers
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)         # LCR

        # DLL=10, DLH=0
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)          # DLL
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)          # DLH

        # LCR=0x03 (DLAB=0)
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)         # LCR

        # Read LSR (initial — should show THRE=1, i.e. ready)
        0x01412083,  # lw x1, 20(x2)         # x1 = LSR
        0x0011a023,  # sw x1, 0(x3)          # store to memory[base+0]

        # Write 'A'
        0x04100093,  # addi x1, x0, 65
        0x00112023,  # sw x1, 0(x2)          # THR = 'A'

        # Read LSR immediately after write (THRE may be 0 = busy)
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)          # store to memory[base+4]

        # Wait until THRE=1
        *POLL,

        # Read final LSR (should show THRE=1 again)
        0x01412083,  # lw x1, 20(x2)
        0x0011a423,  # sw x1, 8(x3)          # store to memory[base+8]

        # Store completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a623,  # sw x1, 12(x3)         # memory[base+12] = 1

        # Infinite loop
        0x0000006f,
    ]
    
    test_name = "uart_status"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_uart_fifo_burst_test():
    """Create assembly that writes a burst through THR without per-byte polling."""

    message = "PANIC TRACE!\r\n"
    instr_mem = [
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)

        # DLL=10, DLH=0
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)

        # LCR=0x03 (DLAB=0), FCR=0x07
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)
    ]

    for ch in message:
        instr_mem.extend([
            0x00000093 | (ord(ch) << 20),  # addi x1, x0, imm
            0x00112023,                    # sw x1, 0(x2)
        ])

    # Poll until TEMT (LSR bit6) reports the transmitter is fully empty.
    instr_mem.extend([
        0x01412083,  # lw x1, 20(x2)
        0x0400f093,  # andi x1, x1, 64
        0xfe008ce3,  # beq x1, x0, -8

        # Store completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a023,  # sw x1, 0(x3)

        # Infinite loop
        0x0000006f,
    ])

    test_name = "uart_fifo_burst"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_uart_fifo_status_test():
    """Verify FIFO mode drives THRE/TEMT low once data is queued."""

    instr_mem = [
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)

        # DLL=10, DLH=0
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)

        # LCR=0x03 (DLAB=0), FCR=0x07
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)

        # Read initial LSR (expect THRE=1/TEMT=1)
        0x01412083,  # lw x1, 20(x2)
        0x0011a023,  # sw x1, 0(x3)

        # Queue one byte and immediately sample LSR again.
        0x04100093,  # addi x1, x0, 'A'
        0x00112023,  # sw x1, 0(x2)
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)

        # Wait until transmitter fully empties, then sample once more.
        0x01412083,  # lw x1, 20(x2)
        0x0400f093,  # andi x1, x1, 64
        0xfe008ce3,  # beq x1, x0, -8
        0x01412083,  # lw x1, 20(x2)
        0x0011a423,  # sw x1, 8(x3)

        # Completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a623,  # sw x1, 12(x3)
        0x0000006f,
    ]

    test_name = "uart_fifo_status"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_uart_fifo_group_burst_test():
    """Send multiple 16-byte FIFO bursts, waiting on THRE between groups."""

    poll_thre = [0x01412083, 0x0200f093, 0xfe008ce3]
    message = "ABCDEFGHIJKLMNOPabcdefghijklmnop"
    assert len(message) == 32

    instr_mem = [
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)

        # DLL=10, DLH=0
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)

        # LCR=0x03 (DLAB=0), FCR=0x07
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)
    ]

    for group_start in range(0, len(message), 16):
        instr_mem.extend(poll_thre)
        for ch in message[group_start:group_start + 16]:
            instr_mem.extend([
                0x00000093 | (ord(ch) << 20),  # addi x1, x0, imm
                0x00112023,                    # sw x1, 0(x2)
            ])

    instr_mem.extend([
        # Poll until TEMT reports the transmitter is fully empty.
        0x01412083,  # lw x1, 20(x2)
        0x0400f093,  # andi x1, x1, 64
        0xfe008ce3,  # beq x1, x0, -8

        0x00100093,  # addi x1, x0, 1
        0x0011a023,  # sw x1, 0(x3)
        0x0000006f,
    ])

    test_name = "uart_fifo_group_burst"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_uart_rx_test():
    """Create assembly that waits for one RX byte and stores it to memory."""

    instr_mem = [
        0x20000137,  # lui x2, 0x20000       # x2 = UART_BASE
        0x020001b7,  # lui x3, 0x2000        # x3 = data memory base

        # NS16550 init: LCR=0x83 (DLAB=1)
        0x08300093,  # addi x1, x0, 0x83
        0x00112623,  # sw x1, 12(x2)

        # DLL=10, DLH=0
        0x00a00093,  # addi x1, x0, 10
        0x00112023,  # sw x1, 0(x2)
        0x00000093,  # addi x1, x0, 0
        0x00112223,  # sw x1, 4(x2)

        # LCR=0x03 (DLAB=0), FCR=0x07
        0x00300093,  # addi x1, x0, 3
        0x00112623,  # sw x1, 12(x2)
        0x00700093,  # addi x1, x0, 7
        0x00112423,  # sw x1, 8(x2)

        # Poll LSR[0] (DR) until data ready
        0x01412083,  # lw x1, 20(x2)
        0x0010f093,  # andi x1, x1, 1
        0xfe008ce3,  # beq x1, x0, -8

        # Read RBR and store to memory
        0x00012083,  # lw x1, 0(x2)
        0x0011a023,  # sw x1, 0(x3)

        # Read LSR again and store to verify DR cleared
        0x01412083,  # lw x1, 20(x2)
        0x0011a223,  # sw x1, 4(x3)

        # Completion flag
        0x00100093,  # addi x1, x0, 1
        0x0011a423,  # sw x1, 8(x3)

        # Infinite loop
        0x0000006f,
    ]

    test_name = "uart_rx"
    hex_file = create_uart_test_hex(test_name, instr_mem)
    return test_name, hex_file

async def monitor_cpu_execution(dut, test_name, max_cycles=1000):
    """Monitor CPU execution and return memory writes"""
    mem_writes = {}
    
    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        
        # Monitor memory writes to data memory
        try:
            if hasattr(dut, 'cpu_mem_write_en') and int(dut.cpu_mem_write_en.value):
                addr = int(dut.cpu_mem_write_addr.value)
                data = int(dut.cpu_mem_write_data.value)
                mem_writes[addr] = data
                log.info(f"Cycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
        except Exception:
            pass
        
        # Monitor PC for debugging
        try:
            pc_val = int(dut.pc_debug.value)
            if cycle % 100 == 0:  # Print every 100 cycles
                log.debug(f"Cycle {cycle}: PC=0x{pc_val:08x}")
        except Exception:
            pass
        
        # Check for completion flag
        if 0x02000000 in mem_writes or 0x0200000C in mem_writes:
            # Give more cycles for UART transmission to complete
            if cycle > 2000:
                break
    
    return mem_writes

@cocotb.test()
async def test_uart_hello_output(dut):
    """Test UART by running code that outputs 'Hello UART!'"""
    log.info("Starting UART Hello World test...")
    
    # Start clock (50MHz as expected by baud rate calculation)
    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Start UART monitor with 5MHz (matching the test program)
    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=5000000)
    monitor_task = cocotb.start_soon(uart_monitor.start_monitoring())
    
    # Monitor execution (reduced cycles due to faster baud rate)
    mem_writes = await monitor_cpu_execution(dut, "uart_hello", max_cycles=2000)
    
    log.info("\nVerifying UART Hello World output:")
    log.info("Memory writes:", mem_writes)
    
    # Check for completion flag
    completion_found = 0x02000000 in mem_writes and mem_writes[0x02000000] == 1
    
    # Get received string from UART
    received_string = uart_monitor.get_received_string()
    log.info(f"UART received: '{received_string}'")
    
    # Verify the output
    expected_string = "Hello UART!\r\n"
    assert completion_found, "Program completion flag not found"
    
    # Check if we received the expected string (allow for some timing variations)
    expected_chars = list(expected_string)
    received_chars = [chr(b) for b in uart_monitor.received_bytes if 32 <= b <= 126 or b in [10, 13]]
    
    # At minimum, we should see "Hello UART!"
    essential_chars = "Hello UART!"
    received_essential = ''.join(c for c in received_chars if c in essential_chars or c.isalnum() or c == ' ')
    
    assert essential_chars in received_essential, f"Expected '{essential_chars}' in UART output, got '{received_essential}'"
    
    log.info("UART Hello World test passed!")

@cocotb.test()
async def test_uart_status_register(dut):
    """Test UART status register functionality"""
    log.info("Starting UART status register test...")
    
    # Start clock (50MHz)
    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Start UART monitor with 5MHz (same as hello test)
    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=5000000)
    monitor_task = cocotb.start_soon(uart_monitor.start_monitoring())
    
    # Monitor execution (reduced cycles due to faster baud rate)
    mem_writes = await monitor_cpu_execution(dut, "uart_status", max_cycles=1500)
    
    log.info("\nVerifying UART status register behavior:")
    log.info("Memory writes:", mem_writes)
    
    # Check for completion flag
    completion_found = 0x0200000C in mem_writes and mem_writes[0x0200000C] == 1
    assert completion_found, "Program completion flag not found"
    
    # Verify LSR values (NS16550: bit5=THRE=1 means TX ready)
    if 0x02000000 in mem_writes:
        initial_lsr = mem_writes[0x02000000]
        log.info(f"Initial LSR: 0x{initial_lsr:08x}")
        assert (initial_lsr & 0x20) != 0, "Initial LSR should show THRE=1 (TX ready)"

    if 0x02000004 in mem_writes:
        busy_lsr = mem_writes[0x02000004]
        log.info(f"LSR after write: 0x{busy_lsr:08x}")
        # May or may not be ready depending on timing

    if 0x02000008 in mem_writes:
        final_lsr = mem_writes[0x02000008]
        log.info(f"Final LSR: 0x{final_lsr:08x}")
        assert (final_lsr & 0x20) != 0, "Final LSR should show THRE=1 (TX ready)"
    
    # Verify we received the 'A' character
    received_string = uart_monitor.get_received_string()
    log.info(f"UART received: '{received_string}'")
    assert 'A' in received_string, f"Expected 'A' in UART output, got '{received_string}'"
    
    log.info("UART status register test passed!")

@cocotb.test()
async def test_uart_fifo_burst(dut):
    """Verify FIFO-enabled back-to-back THR writes are not dropped."""
    log.info("Starting UART FIFO burst test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=5000000)
    monitor_task = cocotb.start_soon(uart_monitor.start_monitoring())

    mem_writes = await monitor_cpu_execution(dut, "uart_fifo_burst", max_cycles=2000)
    await ClockCycles(dut.clk, 300)

    completion_found = 0x02000000 in mem_writes and mem_writes[0x02000000] == 1
    assert completion_found, "Program completion flag not found"

    received_string = uart_monitor.get_received_string()
    log.info(f"UART received: '{received_string}'")
    assert "PANIC TRACE!" in received_string, (
        f"Expected burst text in UART output, got '{received_string}'"
    )

    log.info("UART FIFO burst test passed!")

@cocotb.test()
async def test_uart_fifo_status(dut):
    """Verify FIFO mode clears THRE/TEMT while bytes remain queued."""
    log.info("Starting UART FIFO status test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = await monitor_cpu_execution(dut, "uart_fifo_status", max_cycles=2000)

    initial_lsr = mem_writes.get(0x02000000)
    queued_lsr = mem_writes.get(0x02000004)
    final_lsr = mem_writes.get(0x02000008)
    completion = mem_writes.get(0x0200000C)

    assert completion == 1, "Program completion flag not found"
    assert initial_lsr is not None and (initial_lsr & 0x60) == 0x60, (
        f"Expected THRE/TEMT high before FIFO write, got 0x{initial_lsr:02x}"
    )
    assert queued_lsr is not None and (queued_lsr & 0x60) == 0x00, (
        f"Expected THRE/TEMT low with queued FIFO data, got 0x{queued_lsr:02x}"
    )
    assert final_lsr is not None and (final_lsr & 0x60) == 0x60, (
        f"Expected THRE/TEMT high after drain, got 0x{final_lsr:02x}"
    )

    log.info("UART FIFO status test passed!")

@cocotb.test()
async def test_uart_fifo_group_burst(dut):
    """Verify FIFO bursts preserve data across multiple 16-byte groups."""
    log.info("Starting UART FIFO group burst test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    uart_monitor = UartMonitor(dut.uart_tx, dut.clk, baud_rate=5000000)
    cocotb.start_soon(uart_monitor.start_monitoring())

    mem_writes = await monitor_cpu_execution(dut, "uart_fifo_group_burst", max_cycles=6000)
    await ClockCycles(dut.clk, 500)

    completion_found = 0x02000000 in mem_writes and mem_writes[0x02000000] == 1
    assert completion_found, "Program completion flag not found"

    received_string = uart_monitor.get_received_string()
    expected = "ABCDEFGHIJKLMNOPabcdefghijklmnop"
    log.info(f"UART received: '{received_string}'")
    assert expected in received_string, (
        f"Expected exact FIFO group text '{expected}', got '{received_string}'"
    )

    log.info("UART FIFO group burst test passed!")

@cocotb.test()
async def test_uart_rx(dut):
    """Verify a byte driven on uart_rx sets DR and is readable through RBR."""
    log.info("Starting UART RX test...")

    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    async def inject_rx_byte():
        # Let the test program finish UART init and enter the DR poll loop.
        await ClockCycles(dut.clk, 200)
        await uart_send_byte(dut, ord('Z'))

    cocotb.start_soon(inject_rx_byte())

    mem_writes = await monitor_cpu_execution(dut, "uart_rx", max_cycles=2000)

    received = mem_writes.get(0x02000000)
    lsr_after = mem_writes.get(0x02000004)
    completion = mem_writes.get(0x02000008)

    assert completion == 1, "Program completion flag not found"
    assert received == ord('Z'), f"Expected received byte 0x5a, got {received!r}"
    assert lsr_after is not None and (lsr_after & 0x01) == 0, (
        f"Expected DR clear after RBR read, got LSR=0x{lsr_after:02x}"
    )

    log.info("UART RX test passed!")

def runCocotbTests():
    """Run the cocotb tests via cocotb-test"""
    from cocotb_test.simulator import run
    import shutil
    
    # Test configurations
    tests_config = [
        ("uart_hello_output", run_uart_hello_test),
        ("uart_status_register", run_uart_status_test),
        ("uart_fifo_burst", run_uart_fifo_burst_test),
        ("uart_fifo_status", run_uart_fifo_status_test),
        ("uart_fifo_group_burst", run_uart_fifo_group_burst_test),
        ("uart_rx", run_uart_rx_test),
    ]
    
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
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith(".v") or file.endswith(".sv"):
                sources.append(os.path.join(root, file))
    
    enable_waves = os.getenv("WAVES", "0") == "1"
    waveform_dir = None
    if enable_waves:
        waveform_dir = os.path.join(curr_dir, "waveforms")
        if not os.path.exists(waveform_dir):
            os.makedirs(waveform_dir)
    
    # Run each test
    for test_name, test_func in tests_config:
        print(f"\n=== Generating and running {test_name} ===")
        _, hex_file = test_func()
        print(f"Generated hex file: {hex_file}")
        plus_args = []
        if enable_waves:
            waveform_path = os.path.join(waveform_dir, f"{test_name}.vcd")
            plus_args = [f"+dumpfile={waveform_path}"]
        
        # Create unique sim_build directory for each test
        sim_build_dir = os.path.join(curr_dir, f"sim_build_{test_name}")
        
        # Clean up previous sim_build for this test
        if os.path.exists(sim_build_dir):
            shutil.rmtree(sim_build_dir)
        
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_uart_cpu",
            testcase=f"test_{test_name}",
            includes=[str(incl_dir)],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f"INSTR_HEX_FILE=\"{hex_file}\""],
            plus_args=plus_args,
            sim_build=sim_build_dir,
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_uart_cpu",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_uart_cpu",
            },
        )

if __name__ == "__main__":
    runCocotbTests()
