"""Programs and helpers shared by the UART tests that run on the core."""

import logging

from cocotb.triggers import RisingEdge, Timer
from cocotb.utils import get_sim_time
logging.basicConfig(level=logging.DEBUG)


log = logging.getLogger(__name__)


class UartMonitor:
    """Monitor the UART TX line and decode transmitted bytes"""
    def __init__(self, uart_tx, clk, baud_rate=3125000):
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
            
            await Timer(self.baud_period_cycles * 3 // 2 * 20, units="ns")
            
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
                    await Timer(self.baud_period_cycles * 20, units="ns")
            
            # Wait one full bit period to the center of the stop bit
            await Timer(self.baud_period_cycles * 20, units="ns")
            current_time = get_sim_time(units="ns")
            print(f"Stop bit received at time: {current_time}, RX byte: 0x{rx_byte:02x}")
            
            # Store received byte
            self.received_bytes.append(rx_byte)
            char = chr(rx_byte) if 32 <= rx_byte <= 126 else f'\\x{rx_byte:02x}'
            log.info(f"UART received: 0x{rx_byte:02x} ('{char}')")
            
    def get_received_string(self):
        """Get the received bytes as a string"""
        return ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in self.received_bytes)


async def monitor_cpu_execution(dut, test_name, max_cycles=1000):
    """Monitor CPU execution and return memory writes"""
    mem_writes = {}
    
    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        
        # Monitor memory writes to data memory
        try:
            if hasattr(dut.cpu_inst, 'module_mem_wr_en') and int(dut.cpu_inst.module_mem_wr_en.value):
                addr = int(dut.cpu_inst.module_write_addr.value)
                data = int(dut.cpu_inst.module_wr_data_out.value)
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
            if cycle > 3000:
                break
    
    return mem_writes
