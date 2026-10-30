"""Each mip bit follows its own source whatever mideleg says (privileged spec 3.1.9), as OpenSBI expects."""

import os
import shutil
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from cocotb_test.simulator import run
from memory_view import read_word

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000
MTIMECMP_LO = 0x0200_4000
PLIC_PRIORITY_2 = 0x0C00_0008
PLIC_ENABLE_S = 0x0C00_2080
PLIC_CLAIM_S = 0x0C20_1004
PLIC_SOURCE_PIN = 2

RESULT = 0x1000_0200
RESULT_WORDS = 8
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
TRAP_CAUSE = 0x1000_0304
TRAP_EPC = 0x1000_030C
IRQ_COUNT = 0x1000_0310
ACK_ADDR = 0x1000_0404
READY_ADDR = 0x1000_0408
UNTOUCHED = 0xDEAD_BEEF

LATENCIES = [0, 2]  # MEM_LATENCY and FETCH_LATENCY
POLL = 64
MIP_STIP = 0x20
MIP_SEIP = 0x200
OPENSBI_MIDELEG = 0x222
MIE_MTIE_STIE = 0xA0


def _poll_mip_seip(slot: int, until_set: bool) -> str:
    """Read mip.SEIP until it is set (or clear), at most POLL times, and store the last value at slot(a7)."""
    branch = "bnez" if until_set else "beqz"
    return f"""
        li      t2, {POLL}
        li      t3, {MIP_SEIP:#x}
1:
        csrr    t0, mip
        and     t0, t0, t3
        {branch}    t0, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
        sw      t0, {slot}(a7)
"""


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        la      t0, m_trap
        csrw    mtvec, t0
        la      t0, s_trap
        csrw    stvec, t0
        li      a7, {RESULT:#x}
        li      t0, {OPENSBI_MIDELEG:#x}
        csrw    mideleg, t0

        # SEIP from PLIC context 1. OpenSBI sets and clears mip.STIP on every timer tick; with csrrs and
        # csrrc that must not copy the PLIC line into the software SEIP bit, or SEIP never clears.
        li      t0, {PLIC_PRIORITY_2:#x}
        li      t1, 1
        sw      t1, 0(t0)
        li      t0, {PLIC_ENABLE_S:#x}
        li      t1, {1 << PLIC_SOURCE_PIN}
        sw      t1, 0(t0)
        li      t0, {READY_ADDR:#x}
        sw      t0, 0(t0)
{_poll_mip_seip(0, True)}
        li      t1, {MIP_STIP:#x}
        csrs    mip, t1
        csrc    mip, t1
        li      t0, {PLIC_CLAIM_S:#x}
        lw      t1, 0(t0)
        sw      t1, 4(a7)
        li      t2, {ACK_ADDR:#x}
        sw      t2, 0(t2)
        fence   w, w
        sw      t1, 0(t0)
{_poll_mip_seip(8, False)}

        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        la      t0, s_code
        csrw    mepc, t0
        li      t0, {MIE_MTIE_STIE:#x}
        csrw    mie, t0
        mret

s_code:
        # sip.STIP and sip.SEIP are read-only in S-mode.
        li      t0, {MIP_STIP | MIP_SEIP:#x}
        csrs    sip, t0
        csrr    t1, sip
        and     t1, t1, t0
        sw      t1, 12(a7)

        # MTIP is a machine interrupt even with STIP delegated: it traps to M-mode, not S-mode.
        csrsi   sstatus, 2
        li      t0, {MTIMECMP_LO:#x}
        sw      zero, 4(t0)
        sw      zero, 0(t0)
        li      s1, {IRQ_COUNT:#x}
        li      t2, {POLL}
1:
        lw      t0, 0(s1)
        bnez    t0, 2f
        addi    t2, t2, -1
        bnez    t2, 1b
2:
        ecall
3:
        j       3b

        .align  2
m_trap:
        csrr    t3, mcause
        bltz    t3, m_irq
        li      t4, 9
        beq     t3, t4, finish
        li      t4, {TRAP_CAUSE:#x}
        sw      t3, 0(t4)
        csrr    t3, mepc
        sw      t3, 8(t4)
finish:
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
1:
        j       1b
m_irq:
        sw      t3, 16(a7)
        li      t4, {MTIMECMP_LO + 4:#x}
        li      t5, -1
        sw      t5, 0(t4)
        li      t4, {IRQ_COUNT:#x}
        lw      t5, 0(t4)
        addi    t5, t5, 1
        sw      t5, 0(t4)
        mret

        .align  2
s_trap:
        csrr    t3, scause
        sw      t3, 20(a7)
        li      t4, {MTIMECMP_LO + 4:#x}
        li      t5, -1
        sw      t5, 0(t4)
        li      t4, {IRQ_COUNT:#x}
        lw      t5, 0(t4)
        addi    t5, t5, 1
        sw      t5, 0(t4)
        sret
"""

# Slot -> (what it is, expected value)
EXPECTED = {
    0: ("mip.SEIP with the pin raised and PLIC context 1 enabled", MIP_SEIP),
    4: ("PLIC context 1 claim", PLIC_SOURCE_PIN),
    8: ("mip.SEIP after csrs/csrc of mip.STIP, claim and complete", 0),
    12: ("sip.STIP and sip.SEIP after S-mode set them", 0),
    16: ("mcause of the timer interrupt taken from S-mode", 0x8000_0007),
    20: ("scause slot (no S-mode trap)", UNTOUCHED),
}

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) }}
}}
"""


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _build_dir() -> Path:
    return Path(os.environ.get("ROUTING_BUILD", Path.cwd() / "build" / "interrupt_routing"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "routing.S"
    lds = build_dir / "routing.ld"
    elf = build_dir / "routing.elf"
    src.write_text(PROGRAM)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr_zifencei", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "routing.bin")],
                   check=True)
    (build_dir / "nop.hex").write_text("@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128)


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < INSTR_MEM_BASE + INSTR_MEM_SIZE:
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address 0x{addr:08x}")


def _poke(dut, addr: int, value: int) -> None:
    dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value & 0xFFFF_FFFF


def _peek(dut, addr: int) -> int:
    """What the program sees at addr."""
    return read_word(dut, _phys_word_index(addr))


def _name() -> str:
    return f"latency {os.environ['ROUTING_LATENCY']}"


@cocotb.test()
async def test_each_mip_bit_follows_its_own_source(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    data = (_build_dir() / "routing.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for offset in range(0, 4 * RESULT_WORDS, 4):
        _poke(dut, RESULT + offset, UNTOUCHED)
    for addr in (DONE_ADDR, TRAP_CAUSE, TRAP_EPC, IRQ_COUNT):
        _poke(dut, addr, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    # The pin is a level interrupt: raised when the program is ready, lowered on its acknowledge.
    raise_pin = lower_pin = done = False
    for _ in range(20000):
        await RisingEdge(dut.clk)
        if raise_pin:
            dut.external_interrupt.value = 1
            raise_pin = False
        if lower_pin:
            dut.external_interrupt.value = 0
            lower_pin = False
        await ReadOnly()
        if int(dut.cpu_mem_write_en.value):
            addr = int(dut.cpu_mem_write_addr.value)
            raise_pin = raise_pin or addr == READY_ADDR
            lower_pin = lower_pin or addr == ACK_ADDR
        if _peek(dut, DONE_ADDR) == DONE_VALUE:
            done = True
            break
    await RisingEdge(dut.clk)
    dut.external_interrupt.value = 0

    wrong = [f"{what}: 0x{_peek(dut, RESULT + slot):08x}, expected 0x{value:08x}"
             for slot, (what, value) in EXPECTED.items() if _peek(dut, RESULT + slot) != value]
    assert done, f"{_name()}: the program did not finish; so far: " + ("; ".join(wrong) or "all checks match")
    cause = _peek(dut, TRAP_CAUSE)
    assert cause == 0, f"{_name()}: unexpected trap, mcause 0x{cause:08x} at 0x{_peek(dut, TRAP_EPC):08x}"
    assert not wrong, f"{_name()}: " + "; ".join(wrong)
    count = _peek(dut, IRQ_COUNT)
    assert count == 1, f"{_name()}: {count} timer interrupts taken, expected one"


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    for latency in LATENCIES:
        sim_build = Path.cwd() / "sim_build" / f"sim_build_interrupt_routing_lat{latency}"
        if sim_build.exists():
            shutil.rmtree(sim_build)
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_interrupt_routing",
            parameters={"MEM_LATENCY": latency, "FETCH_LATENCY": latency},
            includes=[str(rtl_dir / "include")],
            simulator="verilator",
            timescale="1ns/1ps",
            defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
            sim_build=str(sim_build),
            force_compile=True,
            extra_env={
                "TOPLEVEL": "top",
                "MODULE": "test_interrupt_routing",
                "COCOTB_TOPLEVEL": "top",
                "COCOTB_TEST_MODULES": "test_interrupt_routing",
                "ROUTING_BUILD": str(build_dir.resolve()),
                "ROUTING_LATENCY": str(latency),
            },
        )


if __name__ == "__main__":
    runCocotbTests()
