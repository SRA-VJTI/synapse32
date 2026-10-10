"""Svade: accessed and dirty bits are managed by software (privileged spec 4.3.1).

An access through a leaf PTE with A clear, or a write through one with D clear, raises the page fault
of that access (12 fetch, 13 load, 15 store/AMO), and hardware never writes the PTE. The M-mode
handler logs the trap and the leaf PTE as it was, sets the bits and returns to retry, which must then
succeed with the value preloaded into the page.
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

CONFIG = 0x1000_0000
LOG = 0x1000_0300
LOG_SLOTS = 12
LOG_COUNT = 0x1000_03FC
DONE_ADDR = 0x1000_0400
DONE_VALUE = 0x444F_4E45
M_SCRATCH = 0x1000_0800
PAGE_TABLE = 0x1001_0000
L0_TABLE = 0x1001_1000
SATP_SV32 = 0x8000_0000 | (PAGE_TABLE >> 12)

BODY_PA = 0x8000_2000
BODY_VA = 0x6000_0000
SUPER_VA = 0x4000_0000
STORE_VALUE = 0x1234
MSTATUS_MXR = 1 << 19

V, R, W, X, A, D = 0x01, 0x02, 0x04, 0x08, 0x40, 0x80

# L1 megapages: VA -> (PA, flags)
MEGAPAGES = {
    INSTR_MEM_BASE: (INSTR_MEM_BASE, V | R | W | X | A | D),
    DATA_MEM_BASE: (DATA_MEM_BASE, V | R | W | A | D),
    SUPER_VA: (DATA_MEM_BASE, V | R | W),
}
# L0 pages under VA 0x60000000: index -> (PA, flags, preloaded word)
PAGES = {
    0: (BODY_PA, V | R | X, None),
    1: (0x1000_1000, V | R | W, 0xA1A1_A1A1),
    2: (0x1000_2000, V | R | W | A, 0xB2B2_B2B2),
    3: (0x1000_3000, V | R | W | A | D, 0xC3C3_C3C3),
    4: (0x1000_4000, V | X, 0xD4D4_D4D4),
    5: (0x1000_5000, V | R | W, 0x0000_1000),
    6: (0x1000_6000, V | R | W | A, 0x0000_2000),
}
SUPER_OFFSET = 0x10
SUPER_VALUE = 0xE5E5_E5E5
RESULTS = 0x1000_3000 + 16


def _va(index: int, offset: int = 0) -> int:
    return BODY_VA + (index << 12) + offset


def _pte(pa: int, flags: int) -> int:
    return ((pa >> 12) << 10) | flags


PROGRAM = f"""
        .section .text.init, "ax"
        .option norelax
        .global _start
_start:
        li      t0, {M_SCRATCH:#x}
        csrw    mscratch, t0
        la      t0, m_trap
        csrw    mtvec, t0
        csrw    medeleg, zero
        li      t0, {SATP_SV32:#x}
        csrw    satp, t0
        li      t0, 0x1800
        csrc    mstatus, t0
        li      t0, 0x0800
        csrs    mstatus, t0
        li      t0, {CONFIG:#x}
        lw      t1, 0(t0)
        bnez    t1, 1f
        li      t0, {BODY_VA:#x}
        csrw    mepc, t0
        mret
1:
        li      t0, 0x20000
        csrs    mstatus, t0
        j       body_mprv

# ---- M-mode body with MPRV = 1, MPP = S
body_mprv:
        li      a1, {_va(1):#x}
        li      a2, {_va(2):#x}
        li      a3, {_va(3):#x}
        li      t1, {STORE_VALUE:#x}
bad_m_0:
        lw      t2, 0(a1)
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
bad_m_1:
        sw      t1, 0(a2)
        li      t4, 0x1800
        csrc    mstatus, t4
        li      t4, 0x0800
        csrs    mstatus, t4
        lw      t3, 0(a3)
        sw      t3, 20(a3)
        j       finish

finish:
        li      t0, {DONE_ADDR:#x}
        li      t1, {DONE_VALUE:#x}
        sw      t1, 0(t0)
spin:
        j       spin

# ---- M-mode handler (bare)
        .align  2
m_trap:
        csrrw   sp, mscratch, sp
        sw      t0, 0(sp)
        sw      t1, 4(sp)
        sw      t2, 8(sp)
        sw      t3, 12(sp)
        csrr    t0, mtval
        srli    t1, t0, 22
        slli    t1, t1, 2
        li      t2, {PAGE_TABLE:#x}
        add     t1, t1, t2
        lw      t2, 0(t1)
        andi    t3, t2, 0xE
        bnez    t3, 1f
        srli    t2, t2, 10
        slli    t2, t2, 12
        srli    t3, t0, 12
        andi    t3, t3, 0x3FF
        slli    t3, t3, 2
        add     t1, t2, t3
1:
        li      t3, {LOG_COUNT:#x}
        lw      t2, 0(t3)
        addi    t0, t2, 1
        sw      t0, 0(t3)
        slli    t2, t2, 4
        li      t3, {LOG:#x}
        add     t2, t2, t3
        csrr    t0, mcause
        sw      t0, 0(t2)
        csrr    t3, mtval
        sw      t3, 4(t2)
        csrr    t3, mepc
        sw      t3, 8(t2)
        lw      t3, 0(t1)
        sw      t3, 12(t2)
        li      t2, {CONFIG:#x}
        lw      t2, 0(t2)
        bnez    t2, m_skip
        ori     t3, t3, {A:#x}
        li      t2, 15
        bne     t0, t2, 2f
        ori     t3, t3, {D:#x}
2:
        sw      t3, 0(t1)
        # Software changed a PTE, so it must fence before the access is retried.
        sfence.vma
        j       m_ret
m_skip:
        csrr    t2, mepc
        addi    t2, t2, 4
        csrw    mepc, t2
m_ret:
        lw      t3, 12(sp)
        lw      t2, 8(sp)
        lw      t1, 4(sp)
        lw      t0, 0(sp)
        csrrw   sp, mscratch, sp
        mret

# ---- S-mode body, linked at PA {BODY_PA:#x} and run at VA {BODY_VA:#x}
        .section .text.body, "ax"
body_s:
        li      a1, {_va(1):#x}
        li      a2, {_va(2):#x}
        li      a3, {_va(3):#x}
        li      a4, {_va(4):#x}
        li      a5, {_va(5):#x}
        li      a6, {_va(6):#x}
        li      a7, {SUPER_VA + SUPER_OFFSET:#x}
        li      t1, {STORE_VALUE:#x}
s_load_a:
        lw      t2, 0(a1)
s_store_d:
        sw      t1, 4(a1)
s_store_a_set_d_clear:
        sw      t1, 0(a2)
        lw      t3, 0(a3)
        sw      t1, 4(a3)
s_amo:
        amoadd.w t4, t1, (a5)
        lr.w    t5, (a6)
s_sc:
        sc.w    t5, t1, (a6)
        li      t0, {MSTATUS_MXR:#x}
        csrs    sstatus, t0
s_mxr_load:
        lw      t6, 0(a4)
        csrc    sstatus, t0
s_super_load:
        lw      s1, 0(a7)
        sw      t2, 16(a3)
        sw      t3, 20(a3)
        sw      t4, 24(a3)
        sw      t5, 28(a3)
        sw      t6, 32(a3)
        sw      s1, 36(a3)
        lui     t0, %hi(finish)
        addi    t0, t0, %lo(finish)
        jr      t0
"""

LINKER_SCRIPT = f"""
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {{
    . = {INSTR_MEM_BASE:#x};
    .text : {{ *(.text.init) *(.text) }}
    . = {BODY_PA:#x};
    .body : {{ *(.text.body) }}
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
    return Path(os.environ.get("SVADE_BUILD", Path.cwd() / "build" / "svade"))


def assemble(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    src = build_dir / "svade.S"
    lds = build_dir / "svade.ld"
    elf = build_dir / "svade.elf"
    src.write_text(PROGRAM)
    lds.write_text(LINKER_SCRIPT)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", "-march=rv32ima_zicsr", "-mabi=ilp32",
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


def _load(dut, image: bytes) -> None:
    for offset in range(0, len(image), 4):
        _poke(dut, INSTR_MEM_BASE + offset, int.from_bytes(image[offset:offset + 4], "little"))


async def run_case(dut, config, limit=20000):
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    _poke(dut, CONFIG, config)
    for va, (pa, flags) in MEGAPAGES.items():
        _poke(dut, PAGE_TABLE + 4 * (va >> 22), _pte(pa, flags))
    _poke(dut, PAGE_TABLE + 4 * (BODY_VA >> 22), _pte(L0_TABLE, V))
    for index, (pa, flags, value) in PAGES.items():
        _poke(dut, L0_TABLE + 4 * index, _pte(pa, flags))
        if value is not None:
            for offset in range(0, 64, 4):
                _poke(dut, pa + offset, 0)
            _poke(dut, pa, value)
    _poke(dut, DATA_MEM_BASE + SUPER_OFFSET, SUPER_VALUE)
    for offset in range(0, 16 * LOG_SLOTS, 4):
        _poke(dut, LOG + offset, 0)
    _poke(dut, LOG_COUNT, 0)
    _poke(dut, DONE_ADDR, 0)
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    done = False
    for _ in range(limit):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.cpu_mem_write_en.value) and int(dut.cpu_mem_write_addr.value) == DONE_ADDR
                and int(dut.cpu_mem_write_data.value) == DONE_VALUE):
            done = True
            break
    await RisingEdge(dut.clk)
    count = _peek(dut, LOG_COUNT)
    log = [tuple(_peek(dut, LOG + 16 * i + 4 * k) for k in range(4)) for i in range(min(count, LOG_SLOTS))]
    return done, count, log


def _fmt(log):
    return [f"(cause {c}, tval {t:#010x}, epc {e:#010x}, pte {p:#010x})" for c, t, e, p in log]


async def _start(dut):
    build_dir = _build_dir()
    symbols = _load_symbols(build_dir)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    image = (build_dir / "image.bin").read_bytes()
    image += b"\x00" * (-len(image) % 4)
    _load(dut, image)
    return symbols


@cocotb.test()
async def test_svade_s_mode_fault_and_retry(dut):
    symbols = await _start(dut)

    def body_va(label):
        return BODY_VA + (symbols[label] - BODY_PA)

    def pte(index):
        return _pte(PAGES[index][0], PAGES[index][1])

    expected = [
        (12, BODY_VA, BODY_VA, pte(0)),
        (13, _va(1), body_va("s_load_a"), pte(1)),
        (15, _va(1, 4), body_va("s_store_d"), pte(1) | A),
        (15, _va(2), body_va("s_store_a_set_d_clear"), pte(2)),
        (15, _va(5), body_va("s_amo"), pte(5)),
        (15, _va(6), body_va("s_sc"), pte(6)),
        (13, _va(4), body_va("s_mxr_load"), pte(4)),
        (13, SUPER_VA + SUPER_OFFSET, body_va("s_super_load"), _pte(DATA_MEM_BASE, V | R | W)),
    ]
    done, count, log = await run_case(dut, 0)
    problems = []
    if not done:
        problems.append("did not finish")
    if count != len(expected) or log != expected:
        problems.append(f"trap log {_fmt(log)} (count {count}), expected {_fmt(expected)}")

    sc_result = _peek(dut, RESULTS + 12)
    sc_word = _peek(dut, PAGES[6][0])
    checks = {
        "load after A fault": (_peek(dut, RESULTS), PAGES[1][2]),
        "store after D fault": (_peek(dut, PAGES[1][0] + 4), STORE_VALUE),
        "store with A set, D clear": (_peek(dut, PAGES[2][0]), STORE_VALUE),
        "load from A/D-set page": (_peek(dut, RESULTS + 4), PAGES[3][2]),
        "store to A/D-set page": (_peek(dut, PAGES[3][0] + 4), STORE_VALUE),
        "AMO rd after retry": (_peek(dut, RESULTS + 8), PAGES[5][2]),
        "AMO memory after retry": (_peek(dut, PAGES[5][0]), PAGES[5][2] + STORE_VALUE),
        "MXR load after A fault": (_peek(dut, RESULTS + 16), PAGES[4][2]),
        "megapage load after A fault": (_peek(dut, RESULTS + 20), SUPER_VALUE),
        # SC may fail after a trap between LR and SC; it must be consistent either way.
        "SC result consistent with memory": (sc_word, STORE_VALUE if sc_result == 0 else PAGES[6][2]),
    }
    problems += [f"{name}: 0x{got:08x}, expected 0x{want:08x}" for name, (got, want) in checks.items() if got != want]
    final_ptes = {1: pte(1) | A | D, 2: pte(2) | D, 4: pte(4) | A, 5: pte(5) | A | D, 6: pte(6) | D}
    problems += [
        f"page {i} PTE 0x{_peek(dut, L0_TABLE + 4 * i):08x}, expected 0x{want:08x} (only software sets A/D)"
        for i, want in final_ptes.items() if _peek(dut, L0_TABLE + 4 * i) != want
    ]
    if _peek(dut, L0_TABLE + 12) != pte(3):
        problems.append(f"A/D-set page PTE changed to 0x{_peek(dut, L0_TABLE + 12):08x}")
    for line in problems:
        dut._log.error(line)
    assert not problems, "; ".join(problems)


@cocotb.test()
async def test_svade_mprv(dut):
    symbols = await _start(dut)
    expected = [
        (13, _va(1), symbols["bad_m_0"], _pte(*PAGES[1][:2])),
        (15, _va(2), symbols["bad_m_1"], _pte(*PAGES[2][:2])),
    ]
    done, count, log = await run_case(dut, 1)
    problems = []
    if not done:
        problems.append("did not finish")
    if count != len(expected) or log != expected:
        problems.append(f"trap log {_fmt(log)} (count {count}), expected {_fmt(expected)}")
    if _peek(dut, PAGES[2][0]) != PAGES[2][2]:
        problems.append(f"faulting MPRV store wrote 0x{_peek(dut, PAGES[2][0]):08x}")
    if _peek(dut, RESULTS + 4) != PAGES[3][2]:
        problems.append(f"MPRV load from A/D-set page gave 0x{_peek(dut, RESULTS + 4):08x}")
    for index in (1, 2):
        if _peek(dut, L0_TABLE + 4 * index) != _pte(*PAGES[index][:2]):
            problems.append(f"page {index} PTE changed by hardware: 0x{_peek(dut, L0_TABLE + 4 * index):08x}")
    assert not problems, "; ".join(problems)


def runCocotbTests():
    repo_root = _find_repo_root()
    rtl_dir = repo_root / "rtl"
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v"))]
    build_dir = _build_dir()
    assemble(build_dir)

    sim_build = Path.cwd() / "sim_build" / "sim_build_svade"
    if sim_build.exists():
        shutil.rmtree(sim_build)

    run(
        verilog_sources=sources,
        toplevel="top",
        module="test_svade",
        includes=[str(rtl_dir / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=[f'INSTR_HEX_FILE="{build_dir / "nop.hex"}"'],
        sim_build=str(sim_build),
        force_compile=True,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": "test_svade",
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": "test_svade",
            "SVADE_BUILD": str(build_dir.resolve()),
        },
    )


if __name__ == "__main__":
    runCocotbTests()
