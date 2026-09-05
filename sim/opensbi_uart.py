import os
import sys
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

UART_IDLE_CYCLES = int(os.getenv("UART_IDLE_CYCLES", "200000"))
BOOT_TIMEOUT_CYCLES = int(os.getenv("BOOT_TIMEOUT_CYCLES", "5000000"))
STATUS_INTERVAL_CYCLES = int(os.getenv("STATUS_INTERVAL_CYCLES", "250000"))
CLOCK_PERIOD_NS = int(os.getenv("CLOCK_PERIOD_NS", "20"))
DEBUG_BOOT_LOGS = os.getenv("DEBUG_BOOT_LOGS", "0") == "1"


class UartConsole:
    def __init__(self, dut, stream_output=True):
        self.dut = dut
        self.stream_output = stream_output
        self.prev_tx_state = 0
        self.received = bytearray()
        self.pending_cr = False

    def _format_byte(self, value: int) -> str:
        if self.pending_cr:
            self.pending_cr = False
            if value == 0x0A:
                return "\r\n"
            return "\r" + self._format_byte(value)
        if value == 0x0D:
            self.pending_cr = True
            return ""
        if value == 0x0A:
            return "\r\n"
        if value == 0x09 or 32 <= value <= 126:
            return chr(value)
        return f"\\x{value:02x}"

    def poll(self):
        tx_state = int(self.dut.uart_inst.tx_state.value)
        emitted = None

        # A new byte is ready whenever the UART enters TX_START.
        if tx_state == 1 and self.prev_tx_state != 1:
            emitted = int(self.dut.uart_inst.tx_data.value) & 0xFF
            self.received.append(emitted)
            if self.stream_output:
                sys.stdout.write(self._format_byte(emitted))
                sys.stdout.flush()

        self.prev_tx_state = tx_state
        return emitted

    async def next_byte(self, dut):
        await RisingEdge(dut.clk)
        return self.poll()


def _uart_baud_cycles(dut, baud_cycles=None):
    if baud_cycles is not None:
        return baud_cycles
    # The RTL reloads baud_counter with baud_div and advances on the next zero hit,
    # so one bit spans baud_div + 1 clock cycles.
    try:
        return int(dut.uart_inst.baud_div.value) + 1
    except Exception:
        return 11


async def uart_send_byte(dut, byte, baud_cycles=None):
    """Drive one byte into uart_rx using the UART's current programmed baud divisor."""
    bit_cycles = _uart_baud_cycles(dut, baud_cycles)
    dut.uart_rx.value = 0  # start bit
    await ClockCycles(dut.clk, bit_cycles)
    for i in range(8):
        dut.uart_rx.value = (byte >> i) & 1
        await ClockCycles(dut.clk, bit_cycles)
    dut.uart_rx.value = 1  # stop bit
    await ClockCycles(dut.clk, bit_cycles)


async def uart_send_str(dut, s, baud_cycles=None):
    for ch in s:
        await uart_send_byte(dut, ord(ch), baud_cycles)


def _read_value(handle, default=None):
    try:
        return int(handle.value)
    except Exception:
        return default


def dump_status(dut, cycle, force=False):
    if not DEBUG_BOOT_LOGS and not force:
        return
    csr = dut.cpu_inst.csr_file_inst
    rf = dut.cpu_inst.rf_inst0.register_file
    uart = dut.uart_inst
    plic = getattr(dut, "plic_inst", None)
    values = {
        "cycle": cycle,
        "pc": _read_value(dut.pc_debug, 0),
        "instr": _read_value(dut.instr_debug, 0),
        "priv": _read_value(csr.privilege_mode, 0),
        "misa": _read_value(csr.misa, 0),
        "mstatus": _read_value(csr.mstatus, 0),
        "mtvec": _read_value(csr.mtvec, 0),
        "mepc": _read_value(csr.mepc, 0),
        "mcause": _read_value(csr.mcause, 0),
        "mtval": _read_value(csr.mtval, 0),
        "stvec": _read_value(csr.stvec, 0),
        "sepc": _read_value(csr.sepc, 0),
        "scause": _read_value(csr.scause, 0),
        "stval": _read_value(csr.stval, 0),
        "satp": _read_value(csr.satp, 0),
        "mie": _read_value(csr.mie, 0),
        "mip": _read_value(csr.mip, 0),
        "ifault": _read_value(dut.cpu_instr_page_fault, 0),
        "lfault": _read_value(dut.cpu_load_page_fault, 0),
        "sfault": _read_value(dut.cpu_store_page_fault, 0),
        "fault_addr": _read_value(dut.cpu_page_fault_addr, 0),
        "data_vaddr": _read_value(dut.data_mem_addr, 0),
        "data_paddr": _read_value(dut.phys_data_addr, 0),
        "instr_paddr": _read_value(dut.phys_instr_addr, 0),
        "store_buf_valid": _read_value(dut.cpu_inst.store_buf_valid, 0),
        "store_buf_addr": _read_value(dut.cpu_inst.store_buf_addr, 0),
        "store_buf_commit": _read_value(dut.cpu_inst.store_buf_commit_fire, 0),
        "pipeline_stall": _read_value(dut.cpu_inst.pipeline_stall, 0),
        "hazard_stall": _read_value(dut.cpu_inst.hazard_stall, 0),
        "uart_rx_state": _read_value(uart.rx_state, 0),
        "uart_rx_dr": _read_value(uart.rx_dr, 0),
        "uart_rx_oe": _read_value(uart.rx_oe, 0),
        "uart_rbr": _read_value(uart.rbr, 0),
        "uart_irq": _read_value(uart.interrupt, 0),
        "plic_pending": _read_value(plic.pending_1, 0) if plic is not None else 0,
        "plic_gateway_busy": _read_value(plic.gateway_busy_1, 0) if plic is not None else 0,
        "plic_enable_m": _read_value(plic.enable_m_1, 0) if plic is not None else 0,
        "plic_enable_s": _read_value(plic.enable_s_1, 0) if plic is not None else 0,
        "plic_ext_irq": _read_value(plic.external_interrupt, 0) if plic is not None else 0,
        "a0": _read_value(rf[10], 0),
        "a1": _read_value(rf[11], 0),
        "a2": _read_value(rf[12], 0),
        "a3": _read_value(rf[13], 0),
        "a4": _read_value(rf[14], 0),
        "a5": _read_value(rf[15], 0),
        "s1": _read_value(rf[9], 0),
    }
    cocotb.log.info(
        "Still booting... cycle=%(cycle)d pc=0x%(pc)08x instr=0x%(instr)08x "
        "priv=%(priv)d misa=0x%(misa)08x mstatus=0x%(mstatus)08x mtvec=0x%(mtvec)08x "
        "mepc=0x%(mepc)08x mcause=0x%(mcause)08x mtval=0x%(mtval)08x "
        "stvec=0x%(stvec)08x sepc=0x%(sepc)08x scause=0x%(scause)08x "
        "stval=0x%(stval)08x satp=0x%(satp)08x mie=0x%(mie)08x mip=0x%(mip)08x "
        "ifault=%(ifault)d lfault=%(lfault)d sfault=%(sfault)d fault_addr=0x%(fault_addr)08x "
        "dvaddr=0x%(data_vaddr)08x dpaddr=0x%(data_paddr)08x ipaddr=0x%(instr_paddr)08x "
        "sbuf=%(store_buf_valid)d sbuf_addr=0x%(store_buf_addr)08x sbuf_commit=%(store_buf_commit)d "
        "stall=%(pipeline_stall)d hazard=%(hazard_stall)d "
        "rx_state=%(uart_rx_state)d rx_dr=%(uart_rx_dr)d rx_oe=%(uart_rx_oe)d "
        "rbr=0x%(uart_rbr)02x uart_irq=%(uart_irq)d "
        "plic_pending=%(plic_pending)d plic_gateway_busy=%(plic_gateway_busy)d "
        "plic_en_m=%(plic_enable_m)d plic_en_s=%(plic_enable_s)d plic_irq=%(plic_ext_irq)d "
        "a0=0x%(a0)08x a1=0x%(a1)08x "
        "a2=0x%(a2)08x a3=0x%(a3)08x a4=0x%(a4)08x a5=0x%(a5)08x s1=0x%(s1)08x",
        values,
    )


async def monitor_traps(dut):
    if not DEBUG_BOOT_LOGS:
        return

    prev_mem_pf = 0
    prev_instr_pf = 0
    prev_scause = None
    prev_sepc = None
    prev_stval = None
    reg_trace = deque(maxlen=32)

    while True:
        await RisingEdge(dut.clk)

        mem_pf = _read_value(dut.cpu_inst.mem_stage_page_fault_taken, 0) or 0
        instr_pf = _read_value(dut.cpu_inst.instr_stage_page_fault_taken, 0) or 0
        scause = _read_value(dut.cpu_inst.csr_file_inst.scause, 0)
        sepc = _read_value(dut.cpu_inst.csr_file_inst.sepc, 0)
        stval = _read_value(dut.cpu_inst.csr_file_inst.stval, 0)
        wb_en = _read_value(dut.cpu_inst.rf_inst0_wr_en, 0) or 0
        wb_rd = _read_value(dut.cpu_inst.rf_inst0_rd_in, 0) or 0
        wb_val = _read_value(dut.cpu_inst.rf_inst0_rd_value_in, 0) or 0

        if wb_en and wb_rd in (1, 2, 8):
            reg_trace.append(
                (
                    wb_rd,
                    wb_val,
                    _read_value(dut.pc_debug, 0),
                    _read_value(dut.instr_debug, 0),
                )
            )

        if mem_pf and not prev_mem_pf:
            cocotb.log.info(
                "MEM trap: pc=0x%08x ex_mem_addr=0x%08x read_req=%d mem_wr_en=%d "
                "load_pf=%d store_pf=%d fault_addr=0x%08x read_addr=0x%08x write_addr=0x%08x "
                "priv=%d scause=0x%08x stval=0x%08x",
                _read_value(dut.cpu_inst.ex_mem_inst0_pc_out, 0),
                _read_value(dut.cpu_inst.ex_mem_inst0_mem_addr_out, 0),
                _read_value(dut.cpu_inst.ex_mem_read_req, 0),
                _read_value(dut.cpu_inst.module_mem_wr_en, 0),
                _read_value(dut.cpu_inst.mem_stage_load_page_fault, 0),
                _read_value(dut.cpu_inst.mem_stage_store_page_fault, 0),
                _read_value(dut.cpu_inst.module_page_fault_addr_in, 0),
                _read_value(dut.cpu_inst.module_read_addr, 0),
                _read_value(dut.cpu_inst.module_write_addr, 0),
                _read_value(dut.cpu_inst.csr_file_inst.privilege_mode, 0),
                _read_value(dut.cpu_inst.csr_file_inst.scause, 0),
                _read_value(dut.cpu_inst.csr_file_inst.stval, 0),
            )
            if reg_trace:
                cocotb.log.info(
                    "Recent fp/sp/ra writes: %s",
                    ", ".join(
                        f"x{rd}=0x{val:08x}@pc=0x{pc:08x}/insn=0x{insn:08x}"
                        for rd, val, pc, insn in reg_trace
                    ),
                )

        if instr_pf and not prev_instr_pf:
            cocotb.log.info(
                "IF trap: pc=0x%08x id_ex_pc=0x%08x instr=0x%08x priv=%d scause=0x%08x stval=0x%08x",
                _read_value(dut.pc_debug, 0),
                _read_value(dut.cpu_inst.id_ex_inst0_pc_out, 0),
                _read_value(dut.instr_debug, 0),
                _read_value(dut.cpu_inst.csr_file_inst.privilege_mode, 0),
                _read_value(dut.cpu_inst.csr_file_inst.scause, 0),
                _read_value(dut.cpu_inst.csr_file_inst.stval, 0),
            )

        if (scause in (0x0000000C, 0x0000000D, 0x0000000F) and
                (scause != prev_scause or sepc != prev_sepc or stval != prev_stval)):
            cocotb.log.info(
                "CSR trap: scause=0x%08x sepc=0x%08x stval=0x%08x mepc=0x%08x "
                "pc=0x%08x ex_mem_pc=0x%08x ex_mem_addr=0x%08x read_req=%d mem_wr_en=%d "
                "load_pf=%d store_pf=%d fault_addr=0x%08x read_addr=0x%08x write_addr=0x%08x "
                "priv=%d",
                scause,
                sepc,
                stval,
                _read_value(dut.cpu_inst.csr_file_inst.mepc, 0),
                _read_value(dut.pc_debug, 0),
                _read_value(dut.cpu_inst.ex_mem_inst0_pc_out, 0),
                _read_value(dut.cpu_inst.ex_mem_inst0_mem_addr_out, 0),
                _read_value(dut.cpu_inst.ex_mem_read_req, 0),
                _read_value(dut.cpu_inst.module_mem_wr_en, 0),
                _read_value(dut.cpu_inst.mem_stage_load_page_fault, 0),
                _read_value(dut.cpu_inst.mem_stage_store_page_fault, 0),
                _read_value(dut.cpu_inst.module_page_fault_addr_in, 0),
                _read_value(dut.cpu_inst.module_read_addr, 0),
                _read_value(dut.cpu_inst.module_write_addr, 0),
                _read_value(dut.cpu_inst.csr_file_inst.privilege_mode, 0),
            )
            if reg_trace:
                cocotb.log.info(
                    "Recent fp/sp/ra writes: %s",
                    ", ".join(
                        f"x{rd}=0x{val:08x}@pc=0x{pc:08x}/insn=0x{insn:08x}"
                        for rd, val, pc, insn in reg_trace
                    ),
                )

        prev_mem_pf = mem_pf
        prev_instr_pf = instr_pf
        prev_scause = scause
        prev_sepc = sepc
        prev_stval = stval


@cocotb.test()
async def boot_opensbi(dut):
    cocotb.log.info(
        "Booting OpenSBI with clock=%dns, boot-timeout=%d cycles, idle-timeout=%d cycles",
        CLOCK_PERIOD_NS,
        BOOT_TIMEOUT_CYCLES,
        UART_IDLE_CYCLES,
    )

    await start_dut(dut)

    console = UartConsole(dut)
    last_uart_cycle = None

    print("\n=== OpenSBI UART ===\n")
    sys.stdout.flush()

    for cycle in range(BOOT_TIMEOUT_CYCLES):
        emitted = await console.next_byte(dut)
        if emitted is not None:
            last_uart_cycle = cycle

        if last_uart_cycle is not None and (cycle - last_uart_cycle) >= UART_IDLE_CYCLES:
            print("\n\n=== UART idle, stopping simulation ===")
            cocotb.log.info("Captured %d UART bytes", len(console.received))
            dump_status(dut, cycle)
            return

        if cycle and cycle % STATUS_INTERVAL_CYCLES == 0:
            dump_status(dut, cycle)

    if last_uart_cycle is None:
        raise AssertionError(
            f"No UART output after {BOOT_TIMEOUT_CYCLES} cycles "
            f"(pc=0x{int(dut.pc_debug.value):08x})"
        )

    raise AssertionError(
        f"Timed out {UART_IDLE_CYCLES} cycles after last UART byte "
        f"(captured {len(console.received)} bytes, pc=0x{int(dut.pc_debug.value):08x})"
    )


async def start_dut(dut):
    clock = Clock(dut.clk, CLOCK_PERIOD_NS, units="ns")
    cocotb.start_soon(clock.start())
    if DEBUG_BOOT_LOGS:
        cocotb.start_soon(monitor_traps(dut))

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 10)
    dut.rst.value = 0
