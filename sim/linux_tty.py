import errno
import os
import pty
import queue
import select
import sys
import termios
import threading
import tty
from collections import deque

import cocotb
from cocotb.triggers import RisingEdge

from opensbi_uart import (
    BOOT_TIMEOUT_CYCLES,
    CLOCK_PERIOD_NS,
    STATUS_INTERVAL_CYCLES,
    UART_IDLE_CYCLES,
    UartConsole,
    dump_status,
    start_dut,
    uart_send_byte,
)

LINUX_BOOT_BANNER = "Synapse32 Linux userspace is up."
LINUX_UNAME_PREFIX = "uname: Linux"
STUCK_DEBUG_START_CYCLES = 5_000_000
STUCK_DEBUG_INTERVAL_CYCLES = 5_000_000
INTERACTIVE_TTY = os.getenv("INTERACTIVE_TTY", "0") == "1"
UART_PTY_LINK = os.getenv("UART_PTY_LINK", "")
UART_PTY_ENABLE = os.getenv("UART_PTY", "0") == "1" or bool(UART_PTY_LINK)
UART_PTY_BUFFER_LIMIT = int(os.getenv("UART_PTY_BUFFER_LIMIT", "65536"))
UART_PTY_WAIT_FOR_ATTACH = os.getenv("UART_PTY_WAIT_FOR_ATTACH", "1") == "1"
UART_PTY_TRANSCRIPT = os.getenv("UART_PTY_TRANSCRIPT", "")
UART_PTY_RX_TRANSCRIPT = os.getenv("UART_PTY_RX_TRANSCRIPT", "")
# Host keystrokes arrive in wall-clock time while the guest advances in much
# slower simulated time.  Keep interactive input to one outstanding RX byte by
# default so typing or pasting cannot overrun the modeled UART before Linux has
# serviced its interrupt.  The host-side queue retains all later bytes.
UART_INPUT_MAX_PENDING = min(
    16, max(1, int(os.getenv("UART_INPUT_MAX_PENDING", "1")))
)
TTY_EXIT_BYTE = 0x1D


class StdinBridge:
    def __init__(self):
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._fd = None
        self._saved_attrs = None
        self._thread = None

    @property
    def stop_requested(self):
        return self._stop.is_set()

    def start(self):
        if not sys.stdin.isatty():
            return False

        self._fd = sys.stdin.fileno()
        self._saved_attrs = termios.tcgetattr(self._fd)
        # Put the host terminal in true raw mode so the guest shell, not the
        # local terminal, owns echoing and line editing.
        tty.setraw(self._fd, when=termios.TCSADRAIN)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return True

    def _reader(self):
        while not self._stop.is_set():
            try:
                data = os.read(self._fd, 1)
            except OSError:
                self._stop.set()
                return
            if not data:
                self._stop.set()
                return
            self._queue.put(data[0])

    def poll(self):
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def request_stop(self):
        self._stop.set()

    def close(self):
        self._stop.set()
        if self._saved_attrs is not None and self._fd is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)


class PtyBridge:
    def __init__(self, link_path: str, transcript_path: str, rx_transcript_path: str):
        self._stop = threading.Event()
        self._thread = None
        self._queue = queue.Queue()
        self._tx_backlog = deque(maxlen=UART_PTY_BUFFER_LIMIT)
        self._master_fd = None
        self._slave_fd = None
        self._slave_path = None
        self._link_path = link_path
        self._transcript_path = transcript_path
        self._transcript = None
        self._rx_transcript_path = rx_transcript_path
        self._rx_transcript = None

    @property
    def stop_requested(self):
        return self._stop.is_set()

    @property
    def slave_path(self):
        return self._slave_path

    @property
    def link_path(self):
        return self._link_path

    @property
    def transcript_path(self):
        return self._transcript_path

    @property
    def rx_transcript_path(self):
        return self._rx_transcript_path

    def start(self):
        self._master_fd, self._slave_fd = pty.openpty()
        self._slave_path = os.ttyname(self._slave_fd)
        tty.setraw(self._slave_fd, when=termios.TCSANOW)
        os.set_blocking(self._master_fd, False)
        if self._transcript_path:
            transcript_dir = os.path.dirname(self._transcript_path)
            if transcript_dir:
                os.makedirs(transcript_dir, exist_ok=True)
            self._transcript = open(self._transcript_path, "wb")
        if self._rx_transcript_path:
            rx_dir = os.path.dirname(self._rx_transcript_path)
            if rx_dir:
                os.makedirs(rx_dir, exist_ok=True)
            self._rx_transcript = open(self._rx_transcript_path, "wb")

        if self._link_path:
            link_dir = os.path.dirname(self._link_path)
            if link_dir:
                os.makedirs(link_dir, exist_ok=True)
            try:
                os.unlink(self._link_path)
            except FileNotFoundError:
                pass
            os.symlink(self._slave_path, self._link_path)

        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return True

    def _reader(self):
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select([self._master_fd], [], [], 0.05)
            except OSError as exc:
                if exc.errno == errno.EBADF:
                    return
                self._stop.set()
                return
            if not readable:
                continue
            try:
                data = os.read(self._master_fd, 256)
            except BlockingIOError:
                continue
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):
                    continue
                self._stop.set()
                return
            if not data:
                continue
            if self._rx_transcript is not None:
                self._rx_transcript.write(data)
                self._rx_transcript.flush()
            for byte in data:
                self._queue.put(byte)

    def poll(self):
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def request_stop(self):
        self._stop.set()

    def write_byte(self, byte: int):
        if self._transcript is not None:
            self._transcript.write(bytes([byte]))
            self._transcript.flush()
        if self._master_fd is None:
            return
        self._flush_backlog()
        try:
            os.write(self._master_fd, bytes([byte]))
        except BlockingIOError:
            # No PTY client is attached or it is not draining quickly enough.
            # Keep a bounded backlog so late attaches still see recent boot logs.
            self._tx_backlog.append(byte)
            return
        except OSError as exc:
            if exc.errno not in (errno.EIO, errno.EBADF):
                raise
            self._tx_backlog.append(byte)

    def _flush_backlog(self):
        while self._tx_backlog and self._master_fd is not None:
            try:
                os.write(self._master_fd, bytes([self._tx_backlog[0]]))
            except BlockingIOError:
                return
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):
                    return
                raise
            self._tx_backlog.popleft()

    def flush_backlog(self):
        self._flush_backlog()

    def wait_for_attach_byte(self):
        while not self._stop.is_set():
            byte = self.poll()
            if byte is not None:
                return byte
            threading.Event().wait(0.05)
        return None

    def close(self):
        self._stop.set()
        if self._transcript is not None:
            self._transcript.close()
            self._transcript = None
        if self._rx_transcript is not None:
            self._rx_transcript.close()
            self._rx_transcript = None
        if self._master_fd is not None:
            os.close(self._master_fd)
            self._master_fd = None
        if self._slave_fd is not None:
            os.close(self._slave_fd)
            self._slave_fd = None
        if self._link_path:
            try:
                if os.path.islink(self._link_path):
                    os.unlink(self._link_path)
            except FileNotFoundError:
                pass


async def drive_bridge_to_uart(dut, bridge):
    while not bridge.stop_requested:
        byte = bridge.poll()
        if byte is None:
            await RisingEdge(dut.clk)
            continue

        if os.getenv("DEBUG_UART_INPUT", "0") == "1":
            cocotb.log.info("UART input byte dequeued: 0x%02x", byte)

        if byte == TTY_EXIT_BYTE:
            bridge.request_stop()
            return

        # A real terminal and CPU progress concurrently.  In simulation, a
        # human can type many characters while only a handful of DUT cycles
        # elapse, so line-rate serialization alone is not sufficient flow
        # control.  Do not dequeue another byte into the UART until Linux has
        # consumed enough of the receive FIFO.
        while (
            not bridge.stop_requested
            and int(dut.uart_inst.rx_fifo_count.value) >= UART_INPUT_MAX_PENDING
        ):
            await RisingEdge(dut.clk)

        if bridge.stop_requested:
            return

        if byte in (0x0A, 0x0D):
            if os.getenv("DEBUG_UART_INPUT", "0") == "1":
                cocotb.log.info("UART sending CR for line ending")
            await uart_send_byte(dut, 0x0D)
            continue

        if os.getenv("DEBUG_UART_INPUT", "0") == "1":
            cocotb.log.info("UART sending data byte: 0x%02x", byte)
        await uart_send_byte(dut, byte)


@cocotb.test()
async def boot_linux(dut):
    cocotb.log.info(
        "Booting Linux with clock=%dns, boot-timeout=%d cycles, idle-timeout=%d cycles",
        CLOCK_PERIOD_NS,
        BOOT_TIMEOUT_CYCLES,
        UART_IDLE_CYCLES,
    )

    console = UartConsole(dut, stream_output=not UART_PTY_ENABLE)
    last_uart_cycle = None
    last_pc = None
    last_pc_change_cycle = 0
    decoded_uart = ""
    saw_banner = False
    saw_uname = False
    next_stuck_debug_cycle = None
    stdin_bridge = None
    pty_bridge = None
    interactive_mode = INTERACTIVE_TTY or UART_PTY_ENABLE

    print("\n=== Linux UART ===\n")
    if INTERACTIVE_TTY:
        print("Interactive UART session. Press Ctrl-] to exit.\n")
    elif UART_PTY_ENABLE:
        print("PTY-backed UART session.\n")
    sys.stdout.flush()

    try:
        if INTERACTIVE_TTY:
            stdin_bridge = StdinBridge()
            if stdin_bridge.start():
                cocotb.start_soon(drive_bridge_to_uart(dut, stdin_bridge))
            else:
                cocotb.log.warning("stdin is not a TTY; interactive UART input is disabled")
        elif UART_PTY_ENABLE:
            pty_bridge = PtyBridge(UART_PTY_LINK, UART_PTY_TRANSCRIPT, UART_PTY_RX_TRANSCRIPT)
            pty_bridge.start()
            print(f"UART PTY slave: {pty_bridge.slave_path}")
            if pty_bridge.link_path:
                print(f"UART PTY link:  {pty_bridge.link_path}")
            if pty_bridge.transcript_path:
                print(f"UART log file:  {pty_bridge.transcript_path}")
            if pty_bridge.rx_transcript_path:
                print(f"UART input log: {pty_bridge.rx_transcript_path}")
            print("Attach with: picocom -q -b 115200 <path>")
            if UART_PTY_WAIT_FOR_ATTACH:
                print("Press Enter in the serial client to start boot.\n")
            else:
                print("")
            sys.stdout.flush()
            if UART_PTY_WAIT_FOR_ATTACH:
                attach_byte = pty_bridge.wait_for_attach_byte()
                if attach_byte is None:
                    raise AssertionError("PTY attach wait ended before a client connected")
            cocotb.start_soon(drive_bridge_to_uart(dut, pty_bridge))

        await start_dut(dut)

        cycle = 0
        while True:
            emitted = await console.next_byte(dut)
            current_pc = int(dut.pc_debug.value)

            if last_pc is None or current_pc != last_pc:
                last_pc = current_pc
                last_pc_change_cycle = cycle

            if emitted is not None:
                last_uart_cycle = cycle
                next_stuck_debug_cycle = cycle + STUCK_DEBUG_START_CYCLES
                decoded_uart = console.received.decode("latin-1", errors="ignore")
                saw_banner = saw_banner or (LINUX_BOOT_BANNER in decoded_uart)
                saw_uname = saw_uname or (LINUX_UNAME_PREFIX in decoded_uart)
                if pty_bridge is not None:
                    pty_bridge.write_byte(emitted)
            elif pty_bridge is not None:
                pty_bridge.flush_backlog()

            if saw_banner and saw_uname and not interactive_mode:
                print("\n\n=== Linux boot banner observed ===")
                cocotb.log.info("Captured %d UART bytes", len(console.received))
                dump_status(dut, cycle)
                return

            if INTERACTIVE_TTY and stdin_bridge is not None and stdin_bridge.stop_requested:
                cocotb.log.info("Interactive UART session closed after %d cycles", cycle)
                return
            if UART_PTY_ENABLE and pty_bridge is not None and pty_bridge.stop_requested:
                cocotb.log.info("PTY UART session closed after %d cycles", cycle)
                return

            if not interactive_mode:
                if (
                    last_uart_cycle is not None
                    and (cycle - last_uart_cycle) >= UART_IDLE_CYCLES
                    and (cycle - last_pc_change_cycle) >= UART_IDLE_CYCLES
                ):
                    raise AssertionError(
                        "Linux UART and PC both went idle before the expected boot banner appeared "
                        f"(banner={saw_banner}, uname={saw_uname}, bytes={len(console.received)}, "
                        f"pc=0x{current_pc:08x})"
                    )

            if (
                last_uart_cycle is not None
                and next_stuck_debug_cycle is not None
                and cycle >= next_stuck_debug_cycle
            ):
                cocotb.log.warning(
                    "Linux boot appears stuck: no UART for %d cycles (bytes=%d, banner=%s, uname=%s)",
                    cycle - last_uart_cycle,
                    len(console.received),
                    saw_banner,
                    saw_uname,
                )
                dump_status(dut, cycle, force=True)
                next_stuck_debug_cycle += STUCK_DEBUG_INTERVAL_CYCLES

            if cycle and cycle % STATUS_INTERVAL_CYCLES == 0:
                dump_status(dut, cycle)

            cycle += 1
            if not interactive_mode and cycle >= BOOT_TIMEOUT_CYCLES:
                break

        if last_uart_cycle is None:
            raise AssertionError(
                f"No UART output after {BOOT_TIMEOUT_CYCLES} cycles "
                f"(pc=0x{int(dut.pc_debug.value):08x})"
            )

        raise AssertionError(
            "Timed out waiting for Linux boot banner "
            f"(banner={saw_banner}, uname={saw_uname}, bytes={len(console.received)}, "
            f"pc=0x{int(dut.pc_debug.value):08x})"
        )
    finally:
        if stdin_bridge is not None:
            stdin_bridge.close()
        if pty_bridge is not None:
            pty_bridge.close()
