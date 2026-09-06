import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

UART_IDLE_CYCLES = int(os.getenv("UART_IDLE_CYCLES", "200000"))
BOOT_TIMEOUT_CYCLES = int(os.getenv("BOOT_TIMEOUT_CYCLES", "5000000"))
STATUS_INTERVAL_CYCLES = int(os.getenv("STATUS_INTERVAL_CYCLES", "250000"))
CLOCK_PERIOD_NS = int(os.getenv("CLOCK_PERIOD_NS", "20"))


class UartConsole:
    def __init__(self, dut):
        self.dut = dut
        self.prev_busy = 0
        self.received = bytearray()

    def _format_byte(self, value: int) -> str:
        if value == 0x0D:
            return ""
        if value == 0x0A:
            return "\n"
        if value == 0x09 or 32 <= value <= 126:
            return chr(value)
        return f"\\x{value:02x}"

    def poll(self):
        busy = int(self.dut.uart_inst.tx_busy.value)
        emitted = None

        if busy and not self.prev_busy:
            emitted = int(self.dut.uart_inst.tx_data.value) & 0xFF
            self.received.append(emitted)
            sys.stdout.write(self._format_byte(emitted))
            sys.stdout.flush()

        self.prev_busy = busy
        return emitted


def _read_value(handle, default=None):
    try:
        return int(handle.value)
    except Exception:
        return default


def _dump_status(dut, cycle):
    csr = dut.cpu_inst.csr_file_inst
    rf = dut.cpu_inst.rf_inst0.register_file
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
        "stvec": _read_value(csr.stvec, 0),
        "sepc": _read_value(csr.sepc, 0),
        "scause": _read_value(csr.scause, 0),
        "satp": _read_value(csr.satp, 0),
        "mie": _read_value(csr.mie, 0),
        "mip": _read_value(csr.mip, 0),
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
        "mepc=0x%(mepc)08x mcause=0x%(mcause)08x stvec=0x%(stvec)08x "
        "sepc=0x%(sepc)08x scause=0x%(scause)08x satp=0x%(satp)08x "
        "mie=0x%(mie)08x mip=0x%(mip)08x a0=0x%(a0)08x a1=0x%(a1)08x "
        "a2=0x%(a2)08x a3=0x%(a3)08x a4=0x%(a4)08x a5=0x%(a5)08x s1=0x%(s1)08x",
        values,
    )


@cocotb.test()
async def boot_opensbi(dut):
    cocotb.log.info(
        "Booting OpenSBI with clock=%dns, boot-timeout=%d cycles, idle-timeout=%d cycles",
        CLOCK_PERIOD_NS,
        BOOT_TIMEOUT_CYCLES,
        UART_IDLE_CYCLES,
    )

    clock = Clock(dut.clk, CLOCK_PERIOD_NS, units="ns")
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst.value = 0

    console = UartConsole(dut)
    last_uart_cycle = None

    print("\n=== OpenSBI UART ===\n")
    sys.stdout.flush()

    for cycle in range(BOOT_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)

        emitted = console.poll()
        if emitted is not None:
            last_uart_cycle = cycle

        if last_uart_cycle is not None and (cycle - last_uart_cycle) >= UART_IDLE_CYCLES:
            print("\n\n=== UART idle, stopping simulation ===")
            cocotb.log.info("Captured %d UART bytes", len(console.received))
            return

        if cycle and cycle % STATUS_INTERVAL_CYCLES == 0 and last_uart_cycle is None:
            _dump_status(dut, cycle)

    if last_uart_cycle is None:
        raise AssertionError(
            f"No UART output after {BOOT_TIMEOUT_CYCLES} cycles "
            f"(pc=0x{int(dut.pc_debug.value):08x})"
        )

    raise AssertionError(
        f"Timed out {UART_IDLE_CYCLES} cycles after last UART byte "
        f"(captured {len(console.received)} bytes, pc=0x{int(dut.pc_debug.value):08x})"
    )
