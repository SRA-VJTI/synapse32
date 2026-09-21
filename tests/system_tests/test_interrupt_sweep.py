"""Interrupt transparency sweep.

Each scenario runs once without an interrupt as the reference, then once per cycle with an interrupt
raised at that cycle. Stores and final memory must match the reference.

Vectored variants set MODE 1 in mtvec and stvec. Every vector-table entry checks that it matches the
trap it was reached by, so a wrong entry hangs the reference run instead of being absorbed by the
common handler.

Svade variants start every trial with A and D clear in the megapages, so page faults go to the M-mode
handler, which sets A (and D for a store/AMO fault) and retries. Interrupts land in and around them.
"""

import os
import shutil
import struct
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
DATA_MEM_BASE = 0x1000_0000

CONFIG = 0x1000_0100
RESULT_LO = 0x1000_0200
RESULT_WORDS = 64
RESULT_HI = RESULT_LO + 4 * RESULT_WORDS
DONE_ADDR = 0x1000_0300
DONE_VALUE = 0x444F_4E45
ACK_ADDR = 0x1000_0400
TRIGGER_COUNT = 0x1000_0500
M_SCRATCH = 0x1000_0800
S_SCRATCH = 0x1000_0900
PAGE_TABLE = 0x1001_0000
SATP_SV32 = 0x8000_0000 | (PAGE_TABLE >> 12)
MTIMECMP_LO = 0x0200_4000
UNMAPPED_VA = 0x4000_0000

# Sv32 identity megapages
MEGAPAGES = {
    INSTR_MEM_BASE: 0xCF,
    DATA_MEM_BASE: 0xCF,
    0x0200_0000: 0xC7,
}
PTE_A_D = 0xC0

SCENARIOS = ["control", "memory", "csr", "atomic", "muldiv", "exceptions", "fence"]
# Label of each scenario's loop, used as the address of the execute trigger in trigger variants.
SCENARIO_LOOP = {"control": "c_loop", "memory": "m_loop", "csr": "k_loop", "atomic": "a_loop",
                 "muldiv": "d_loop", "exceptions": "e_loop", "fence": "f_loop"}
CSR_TSELECT, CSR_TDATA1, CSR_TDATA2 = 0x7A0, 0x7A1, 0x7A2
# mcontrol type 2, fires in M, S and U on execute.
TDATA1_EXECUTE_ANY_MODE = (2 << 28) | (1 << 6) | (1 << 4) | (1 << 3) | (1 << 2)

# name, privilege (3 = M, 1 = S), MMU on, source, mideleg, vectored mtvec/stvec, Svade (A/D clear),
# execute trigger armed on the scenario loop
VARIANTS = [
    ("m_software", 3, 0, "software", 0x000, 0, 0, 0),
    ("m_external", 3, 0, "external", 0x000, 0, 0, 0),
    ("m_timer", 3, 0, "timer", 0x000, 0, 0, 0),
    ("s_software_delegated", 1, 0, "software", 0x002, 0, 0, 0),
    ("s_timer_delegated", 1, 0, "timer", 0x020, 0, 0, 0),
    ("s_mmu_external_delegated", 1, 1, "external", 0x200, 0, 0, 0),
    ("s_mmu_software_to_m", 1, 1, "software", 0x000, 0, 0, 0),
    ("m_timer_vectored", 3, 0, "timer", 0x000, 1, 0, 0),
    ("s_mmu_external_delegated_vectored", 1, 1, "external", 0x200, 1, 0, 0),
    ("s_mmu_timer_delegated_svade", 1, 1, "timer", 0x020, 0, 1, 0),
    ("s_mmu_software_to_m_svade", 1, 1, "software", 0x000, 0, 1, 0),
    ("m_software_trigger", 3, 0, "software", 0x000, 0, 0, 1),
    ("s_mmu_external_delegated_trigger", 1, 1, "external", 0x200, 0, 0, 1),
]

TRIAL_SLACK_CYCLES = 400


def _vector_table(mode: str) -> str:
    """16 entries; entry i saves t0, checks i against the trap, then joins the direct handler."""
    lines = [f"        .align  2\n{mode}_vec:"]
    lines += [f"        j       {mode}_vec_{i}" for i in range(16)]
    for i in range(16):
        lines.append(
            f"{mode}_vec_{i}:\n"
            f"        csrrw   sp, {mode}scratch, sp\n"
            f"        sw      t0, 0(sp)\n"
            f"        li      t0, {i}\n"
            f"        j       {mode}_vec_check"
        )
    lines.append(
        f"{mode}_vec_check:\n"
        f"        sw      t1, 4(sp)\n"
        f"        csrr    t1, {mode}cause\n"
        f"        bltz    t1, 1f\n"
        f"        li      t1, 0\n"
        f"1:\n"
        f"        andi    t1, t1, 0x3f\n"
        f"        bne     t0, t1, vector_mismatch\n"
        f"        lw      t1, 4(sp)\n"
        f"        j       {mode}_trap_saved"
    )
    return "\n".join(lines)
MIN_DISTINCT_INTERRUPT_PCS = 10

PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {CONFIG:#x}
        lw      t3, 20(t0)
        la      t1, m_trap
        beqz    t3, 3f
        la      t1, m_vec
        ori     t1, t1, 1
3:
        csrw    mtvec, t1
        la      t1, s_trap
        beqz    t3, 4f
        la      t1, s_vec
        ori     t1, t1, 1
4:
        csrw    stvec, t1
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        li      t0, {S_SCRATCH:#x}
        csrw    sscratch, t0
        li      t0, {CONFIG:#x}
        lw      t1, 16(t0)
        csrw    mideleg, t1
        lw      t1, 12(t0)
        beqz    t1, 1f
        li      t2, {MTIMECMP_LO:#x}
        sw      t1, 0(t2)
        sw      zero, 4(t2)
1:
        li      t1, 0xAAA
        csrw    mie, t1
        lw      t1, 8(t0)
        beqz    t1, 2f
        li      t2, {SATP_SV32:#x}
        csrw    satp, t2
2:
        lw      t1, 28(t0)
        beqz    t1, 5f
        csrw    {CSR_TSELECT:#x}, zero
        csrw    {CSR_TDATA2:#x}, t1
        li      t2, {TDATA1_EXECUTE_ANY_MODE:#x}
        csrw    {CSR_TDATA1:#x}, t2
5:
        lw      t1, 0(t0)
        slli    t1, t1, 2
        la      t2, scenario_table
        add     t2, t2, t1
        lw      t2, 0(t2)
        lw      t3, 4(t0)
        li      t4, 3
        beq     t3, t4, run_m
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
        csrsi   mstatus, 0x2
        csrw    mepc, t2
        mret
run_m:
        csrsi   mstatus, 0x8
        jr      t2

        .align  2
scenario_table:
        .word   sc_control, sc_memory, sc_csr, sc_atomic, sc_muldiv, sc_exceptions, sc_fence

# ---- Machine-mode trap handler
# In Svade variants a page fault on a mapped megapage sets A (and D for cause 15) and retries.
        .align  2
m_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
m_trap_saved:
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        csrr    t0, mcause
        bltz    t0, m_irq
        li      t1, 3
        bne     t0, t1, m_not_breakpoint
        # An armed execute trigger fires once; count it, disable it, retry the instruction.
        li      t1, {TRIGGER_COUNT:#x}
        lw      t2, 0(t1)
        addi    t2, t2, 1
        sw      t2, 0(t1)
        csrw    {CSR_TDATA1:#x}, zero
        j       m_ret
m_not_breakpoint:
        li      t1, {CONFIG:#x}
        lw      t1, 24(t1)
        beqz    t1, m_skip
        li      t1, 12
        beq     t0, t1, m_ad
        li      t1, 13
        beq     t0, t1, m_ad
        li      t1, 15
        bne     t0, t1, m_skip
m_ad:
        csrr    t1, mtval
        srli    t1, t1, 22
        slli    t1, t1, 2
        li      t2, {PAGE_TABLE:#x}
        add     t1, t1, t2
        lw      t2, 0(t1)
        beqz    t2, m_skip
        ori     t2, t2, 0x40
        addi    t0, t0, -15
        bnez    t0, 1f
        ori     t2, t2, 0x80
1:
        sw      t2, 0(t1)
        sfence.vma
        j       m_ret
m_skip:
        csrr    t0, mepc
        addi    t0, t0, 4
        csrw    mepc, t0
        j       m_ret
m_irq:
        andi    t0, t0, 0x3f
        li      t1, 7
        beq     t0, t1, m_timer
        li      t0, {ACK_ADDR:#x}
        sw      t0, 0(t0)
        j       m_ret
m_timer:
        li      t0, {MTIMECMP_LO + 4:#x}
        li      t1, -1
        sw      t1, 0(t0)
m_ret:
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret

# ---- Supervisor-mode trap handler
        .align  2
s_trap:
        csrrw   sp, sscratch, sp
        sw      t0, 0(sp)
s_trap_saved:
        sw      t1, 4(sp)
        csrr    t0, scause
        bltz    t0, s_irq
        csrr    t0, sepc
        addi    t0, t0, 4
        csrw    sepc, t0
        j       s_ret
s_irq:
        andi    t0, t0, 0x3f
        li      t1, 5
        beq     t0, t1, s_timer
        li      t0, {ACK_ADDR:#x}
        sw      t0, 0(t0)
        j       s_ret
s_timer:
        li      t0, {MTIMECMP_LO + 4:#x}
        li      t1, -1
        sw      t1, 0(t0)
s_ret:
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, sscratch, sp
        sret

{_vector_table("m")}
{_vector_table("s")}

vector_mismatch:
        j       vector_mismatch

# ---- Scenarios (t6 = result area)
sc_control:
        li      t6, {RESULT_LO:#x}
        li      s0, 0
        li      s1, 0
        li      s2, 12
c_loop:
        addi    s0, s0, 3
        andi    t0, s1, 1
        beqz    t0, c_even
        addi    s0, s0, 5
        j       c_join
c_even:
        jal     ra, c_func
c_join:
        addi    s1, s1, 1
        sw      s0, 0(t6)
        blt     s1, s2, c_loop
        la      t0, c_func2
        jalr    ra, 0(t0)
        sw      s0, 4(t6)
        j       finish
c_func:
        addi    s0, s0, 7
        xori    s0, s0, 0x55
        ret
c_func2:
        addi    s0, s0, -1
        ret

sc_memory:
        li      t6, {RESULT_LO:#x}
        li      s0, 0x12345678
        li      s1, 8
m_loop:
        sw      s0, 8(t6)
        lw      t0, 8(t6)
        addi    t0, t0, 1
        sw      t0, 12(t6)
        lb      t1, 12(t6)
        add     s0, s0, t1
        lhu     t2, 14(t6)
        xor     s0, s0, t2
        sh      s0, 16(t6)
        lh      t3, 16(t6)
        sub     s0, s0, t3
        sb      s0, 20(t6)
        addi    s1, s1, -1
        bnez    s1, m_loop
        sw      s0, 24(t6)
        j       finish

sc_csr:
        li      t6, {RESULT_LO:#x}
        li      s0, 0
        li      s1, 6
k_loop:
        csrrw   t0, scounteren, s1
        add     s0, s0, t0
        csrrsi  t1, scounteren, 1
        add     s0, s0, t1
        csrrci  t2, scounteren, 2
        add     s0, s0, t2
        li      t3, 0x40000
        csrrs   t4, sstatus, t3
        csrrc   t5, sstatus, t3
        srli    t4, t4, 18
        andi    t4, t4, 1
        add     s0, s0, t4
        sw      s0, 28(t6)
        addi    s1, s1, -1
        bnez    s1, k_loop
        csrr    t0, scounteren
        sw      t0, 32(t6)
        j       finish

sc_atomic:
        li      t6, {RESULT_LO:#x}
        addi    a0, t6, 40
        li      s0, 10
        sw      s0, 0(a0)
        li      s1, 6
a_loop:
        lr.w    t0, (a0)
        addi    t1, t0, 3
        sc.w    t2, t1, (a0)
        bnez    t2, a_loop
        li      t3, 5
        amoadd.w t4, t3, (a0)
        amoxor.w t5, s1, (a0)
        addi    s1, s1, -1
        bnez    s1, a_loop
        lw      t0, 0(a0)
        sw      t0, 44(t6)
        j       finish

sc_muldiv:
        li      t6, {RESULT_LO:#x}
        li      s0, 0x12345
        li      s1, -7
        li      s2, 10
d_loop:
        mul     t0, s0, s1
        mulh    t1, s0, s1
        mulhu   t2, s0, s1
        div     t3, t0, s2
        rem     t4, t0, s2
        divu    t5, s0, s2
        add     s0, t3, t4
        xor     s0, s0, t1
        add     s0, s0, t2
        add     s0, s0, t5
        sw      s0, 48(t6)
        addi    s2, s2, -1
        bnez    s2, d_loop
        j       finish

sc_exceptions:
        li      t6, {RESULT_LO:#x}
        li      s0, 1
        li      s1, 5
        li      t0, {CONFIG:#x}
        lw      s2, 8(t0)
e_loop:
        addi    s0, s0, 2
        ecall
        addi    s0, s0, 3
        .word   0x00000000
        slli    s0, s0, 1
        beqz    s2, e_no_mmu
        li      t2, {UNMAPPED_VA:#x}
        lw      t3, 0(t2)
        addi    s0, s0, 1
e_no_mmu:
        sw      s0, 52(t6)
        addi    s1, s1, -1
        bnez    s1, e_loop
        j       finish

sc_fence:
        li      t6, {RESULT_LO:#x}
        li      s0, 0
        li      s1, 8
f_loop:
        addi    s0, s0, 9
        fence.i
        addi    s0, s0, -2
        sw      s0, 56(t6)
        addi    s1, s1, -1
        bnez    s1, f_loop
        j       finish

finish:
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text*) *(.rodata*) }}
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
    return Path(os.environ.get("INTERRUPT_SWEEP_BUILD", Path.cwd() / "build" / "interrupt_sweep"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "sweep.S"
    lds = build_dir / "sweep.ld"
    elf = build_dir / "sweep.elf"
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
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(build_dir / "image.bin")], check=True)
    symbols = _elf32_symbols(elf.read_bytes())
    (build_dir / "symbols.txt").write_text("".join(f"{value:08x} {name}\n" for name, value in sorted(symbols.items())))
    (build_dir / "nop.hex").write_text("@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128)


def _elf32_symbols(elf: bytes) -> dict:
    assert elf[:4] == b"\x7fELF" and elf[4] == 1 and elf[5] == 1, "expected a little-endian ELF32 file"
    e_shoff, = struct.unpack_from("<I", elf, 32)
    e_shentsize, e_shnum = struct.unpack_from("<HH", elf, 46)
    sections = [struct.unpack_from("<IIIIIIIIII", elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    table = {}
    for _, sh_type, _, _, offset, size, link, _, _, entsize in sections:
        if sh_type != 2:  # SHT_SYMTAB
            continue
        strtab_offset = sections[link][4]
        for pos in range(offset, offset + size, entsize):
            st_name, st_value = struct.unpack_from("<II", elf, pos)
            if st_name:
                end = elf.index(b"\x00", strtab_offset + st_name)
                table[elf[strtab_offset + st_name:end].decode()] = st_value
    return table


def _load_symbols(build_dir: Path) -> dict:
    table = {}
    for line in (build_dir / "symbols.txt").read_text().splitlines():
        value, name = line.split()
        table[name] = int(value, 16)
    return table


def _phys_word_index(addr: int) -> int:
    if INSTR_MEM_BASE <= addr < INSTR_MEM_BASE + INSTR_MEM_SIZE:
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address 0x{addr:08x}")


def _poke(dut, addr: int, value: int) -> None:
    dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value = value & 0xFFFF_FFFF


def _peek(dut, addr: int) -> int:
    return int(dut.unified_mem_inst.instr_ram[_phys_word_index(addr)].value) & 0xFFFF_FFFF


def _load_image(dut, build_dir: Path) -> None:
    data = (build_dir / "image.bin").read_bytes()
    data += b"\x00" * (-len(data) % 4)
    for offset in range(0, len(data), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(data[offset:offset + 4], "little"))
    for va, flags in MEGAPAGES.items():
        _poke(dut, PAGE_TABLE + 4 * (va >> 22), ((va >> 12) << 10) | flags)


class Trial:
    def __init__(self):
        self.stores = []
        self.memory = []
        self.done_cycle = None
        self.entry_cycle = None
        self.interrupt_pcs = []
        self.bubble_interrupts = 0
        self.pte_writes = 0
        self.trigger_hits = 0


async def run_trial(dut, scenario_index, variant, entry_addr, inject_cycle, limit, want_entry=False,
                    trigger_addr=0):
    _, privilege, mmu, source, mideleg, vectored, svade, _trigger = variant
    pin = {"software": dut.software_interrupt, "external": dut.external_interrupt}.get(source)

    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    timer_target = inject_cycle if (source == "timer" and inject_cycle is not None) else 0
    _poke(dut, CONFIG, scenario_index)
    _poke(dut, CONFIG + 4, privilege)
    _poke(dut, CONFIG + 8, mmu)
    _poke(dut, CONFIG + 12, timer_target)
    _poke(dut, CONFIG + 16, mideleg)
    _poke(dut, CONFIG + 20, vectored)
    _poke(dut, CONFIG + 24, svade)
    _poke(dut, CONFIG + 28, trigger_addr)
    for va, flags in MEGAPAGES.items():
        _poke(dut, PAGE_TABLE + 4 * (va >> 22), ((va >> 12) << 10) | (flags & ~PTE_A_D if svade else flags))
    for index in range(RESULT_WORDS):
        _poke(dut, RESULT_LO + 4 * index, 0)
    _poke(dut, DONE_ADDR, 0)
    _poke(dut, ACK_ADDR, 0)
    _poke(dut, TRIGGER_COUNT, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    trial = Trial()
    pin_high = False
    lower_pin = False
    watch_taken = source == "timer" and inject_cycle is not None
    for cycle in range(limit):
        await RisingEdge(dut.clk)
        if pin is not None and inject_cycle is not None and cycle == inject_cycle:
            pin.value = 1
            pin_high = True
            watch_taken = True
        if lower_pin:
            pin.value = 0
            pin_high = False
            lower_pin = False
        await ReadOnly()
        if want_entry and trial.entry_cycle is None and int(dut.pc_debug.value) == entry_addr:
            trial.entry_cycle = cycle
        # Count a store once, when memory accepts it; a page-faulting store is not committed.
        if int(dut.data_write_fire.value) and not int(dut.cpu_store_page_fault.value):
            addr = int(dut.cpu_mem_write_addr.value)
            if RESULT_LO <= addr < RESULT_HI:
                trial.stores.append((addr, int(dut.cpu_mem_write_data.value), int(dut.cpu_write_byte_enable.value)))
            elif addr == ACK_ADDR and pin_high:
                lower_pin = True
            elif addr == DONE_ADDR and int(dut.cpu_mem_write_data.value) == DONE_VALUE:
                trial.done_cycle = cycle
            elif PAGE_TABLE <= addr < PAGE_TABLE + 0x1000:
                trial.pte_writes += 1
        if watch_taken and int(dut.cpu_inst.interrupt_taken_qualified.value):
            trial.interrupt_pcs.append(int(dut.cpu_inst.interrupt_pc.value))
            if not int(dut.cpu_inst.id_ex_inst0_instr_valid_out.value) and int(dut.cpu_inst.if_id_instr_valid_out.value):
                trial.bubble_interrupts += 1
        if trial.done_cycle is not None:
            break
    await RisingEdge(dut.clk)
    trial.memory = [_peek(dut, RESULT_LO + 4 * index) for index in range(RESULT_WORDS)]
    trial.trigger_hits = _peek(dut, TRIGGER_COUNT)
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    return trial


def _expected_absolute(scenario: str, mmu: int):
    if scenario == "fence":
        return {56: 8 * 7}
    if scenario == "atomic":
        value = 10
        for s1 in range(6, 0, -1):
            value = (value + 3 + 5) ^ s1
        return {44: value}
    if scenario == "exceptions":
        s0 = 1
        for _ in range(5):
            s0 = ((s0 + 2 + 3) << 1) + (1 if mmu else 0)
        return {52: s0 & 0xFFFF_FFFF}
    return {}


async def sweep_variant(dut, variant):
    name = variant[0]
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    _load_image(dut, build_dir)

    failures = []
    taken_trials = 0
    bubble_trials = 0
    distinct_pcs = set()
    trial_count = 0
    for scenario_index, scenario in enumerate(SCENARIOS):
        entry = symbols[f"sc_{scenario}"]
        trigger_addr = symbols[SCENARIO_LOOP[scenario]] if variant[7] else 0
        reference = await run_trial(dut, scenario_index, variant, entry, None, 20000, want_entry=True,
                                    trigger_addr=trigger_addr)
        assert reference.done_cycle is not None, f"{name}/{scenario}: reference run did not finish"
        assert reference.stores, f"{name}/{scenario}: reference run made no result stores"
        if variant[6]:
            assert reference.pte_writes > 0, f"{name}/{scenario}: no A/D page fault was taken with A/D clear"
        if variant[7]:
            assert reference.trigger_hits > 0, f"{name}/{scenario}: the armed execute trigger never fired"
        for offset, expected in _expected_absolute(scenario, variant[2]).items():
            actual = reference.memory[offset // 4]
            assert actual == expected, f"{name}/{scenario}: reference result @+{offset} = {actual:#x}, expected {expected:#x}"

        first = max(0, (reference.entry_cycle or 0) - 4)
        limit = reference.done_cycle + TRIAL_SLACK_CYCLES
        for inject in range(first, reference.done_cycle + 1):
            trial = await run_trial(dut, scenario_index, variant, entry, inject, limit,
                                    trigger_addr=trigger_addr)
            trial_count += 1
            if trial.interrupt_pcs:
                taken_trials += 1
                distinct_pcs.update(trial.interrupt_pcs)
            if trial.bubble_interrupts:
                bubble_trials += 1
            problem = None
            if trial.done_cycle is None:
                problem = "did not finish"
            elif trial.stores != reference.stores:
                diverge = next(
                    (i for i, pair in enumerate(zip(trial.stores, reference.stores)) if pair[0] != pair[1]),
                    min(len(trial.stores), len(reference.stores)),
                )
                got = trial.stores[diverge] if diverge < len(trial.stores) else None
                want = reference.stores[diverge] if diverge < len(reference.stores) else None
                problem = f"store #{diverge} differs: got {_fmt(got)}, expected {_fmt(want)}"
            elif trial.memory != reference.memory:
                problem = "final result memory differs"
            if problem:
                pcs = ", ".join(f"0x{pc:08x}" for pc in trial.interrupt_pcs) or "none"
                failures.append(f"{name}/{scenario} interrupt at cycle {inject}: {problem} (interrupt pc {pcs})")
        dut._log.info(
            f"{name}/{scenario}: reference {reference.done_cycle} cycles, "
            f"swept cycles {first}..{reference.done_cycle}"
        )

    dut._log.info(
        f"{name}: {trial_count} trials, {taken_trials} took the interrupt, "
        f"{bubble_trials} took it on an EX bubble with IF/ID valid, {len(distinct_pcs)} distinct interrupt pcs, "
        f"{len(failures)} failures"
    )
    for line in failures[:40]:
        dut._log.error(line)
    assert not failures, f"{name}: {len(failures)} of {trial_count} trials not transparent; first: {failures[0]}"
    assert bubble_trials > 0, f"{name}: no trial took the interrupt on an EX bubble; coverage lost"
    assert len(distinct_pcs) >= MIN_DISTINCT_INTERRUPT_PCS, f"{name}: only {len(distinct_pcs)} distinct interrupt pcs"


def _fmt(store):
    if store is None:
        return "no store"
    addr, data, byte_enable = store
    return f"0x{data:08x}@0x{addr:08x}/be{byte_enable:x}"


def _make_test(variant):
    async def test(dut):
        await sweep_variant(dut, variant)

    test.__name__ = f"test_sweep_{variant[0]}"
    test.__qualname__ = test.__name__
    return cocotb.test()(test)


# INTERRUPT_SWEEP_FILTER=name[,name] runs only those variants.
_FILTER = {name for name in os.environ.get("INTERRUPT_SWEEP_FILTER", "").split(",") if name}
for _variant in VARIANTS:
    if not _FILTER or _variant[0] in _FILTER:
        globals()[f"test_sweep_{_variant[0]}"] = _make_test(_variant)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_interrupt_sweep"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    extra_env = {
        "TOPLEVEL": "top",
        "MODULE": "test_interrupt_sweep",
        "COCOTB_TOPLEVEL": "top",
        "COCOTB_TEST_MODULES": "test_interrupt_sweep",
        "INTERRUPT_SWEEP_FILTER": os.environ.get("INTERRUPT_SWEEP_FILTER", ""),
        "INTERRUPT_SWEEP_BUILD": str(build_dir.resolve()),
    }
    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_interrupt_sweep",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env=extra_env,
    )


if __name__ == "__main__":
    runCocotbTests()
