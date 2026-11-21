"""Helpers shared by the tests: the memory map, building programs, running them on the core, and reading memory
the way the program's loads would see it."""

import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from cocotb_test.simulator import run

# rtl/include/memory_map.vh
INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_SIZE = 0x0400_0000
INSTR_MEM_WORDS = INSTR_MEM_SIZE // 4
DATA_MEM_BASE = 0x1000_0000

NOP = 0x0000_0013
PARK = 0x0000_006F  # jal x0, 0

# dcache.v engine states
E_EVICT_READ = 3
E_EVICT_WRITE = 4


def find_repo_root() -> Path:
    """The checkout the tests run in: the first directory up from the working directory that holds rtl/."""
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def rtl_sources() -> list:
    """Every Verilog file under rtl/: the runners compile them all, instantiated or not."""
    return [str(p) for p in sorted((find_repo_root() / "rtl").rglob("*.v"))]


def nop_image() -> Path:
    """The boot image most system tests start from: 512 NOPs, replaced by the test's own loader at reset."""
    path = Path.cwd() / "build" / "nop.hex"
    text = "@00000000\n" + "00000013 00000013 00000013 00000013\n" * 128
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        # Written whole and renamed into place, so a test starting in parallel never reads half a file.
        tmp = path.with_name(f"nop.hex.{os.getpid()}")
        tmp.write_text(text)
        os.replace(tmp, path)
    return path


def build_directory(name: str) -> Path:
    """A test's own directory for its build products, so tests running in parallel never share one."""
    path = Path.cwd() / "build" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---- Memory

def word_index(addr: int) -> int:
    """The RAM array index of a physical address."""
    if INSTR_MEM_BASE <= addr < INSTR_MEM_BASE + INSTR_MEM_SIZE:
        return (addr - INSTR_MEM_BASE) // 4
    if addr >= DATA_MEM_BASE:
        return (INSTR_MEM_SIZE + (addr - DATA_MEM_BASE)) // 4
    raise AssertionError(f"Unsupported physical address 0x{addr:08x}")


def poke(dut, addr: int, value: int) -> None:
    """Write RAM directly: only while the core is held in reset, since the caches would not see it."""
    dut.unified_mem_inst.instr_ram[word_index(addr)].value = value & 0xFFFF_FFFF


def peek(dut, addr: int) -> int:
    """The word at a physical address as the program's loads would see it."""
    return read_word(dut, word_index(addr))


def _phys_addr(index: int) -> int:
    if index < INSTR_MEM_WORDS:
        return INSTR_MEM_BASE + 4 * index
    return DATA_MEM_BASE + 4 * (index - INSTR_MEM_WORDS)


class _Scope:
    """A module inside a generate block: Verilator's VPI finds its signals only by their full dotted name."""

    def __init__(self, parent, path):
        self._parent = parent
        self._path = path

    def __getattr__(self, name):
        return self._parent._id(f"{self._path}.{name}", extended=False)


def dcache(dut):
    """The core's data cache, or None in a build without one."""
    try:
        dut.cpu_inst._id("g_dcache.dcache_inst", extended=False)
    except AttributeError:
        return None
    return _Scope(dut.cpu_inst, "g_dcache.dcache_inst")


def mshr_slots(cache) -> int:
    """The number of MSHRs: the packed line-address vector holds one 30 - log2(words) bit entry per MSHR."""
    words = len(cache.data_mem) // len(cache.tag_mem)
    return len(cache.mshr_line_q) // (30 - (words.bit_length() - 1))


def _locate(cache, index: int):
    """The word's data-array row, set, tag, line address and word in line, and the way holding it or None."""
    sets = len(cache.tag_mem)
    way_words = len(cache.data_mem)
    words = way_words // sets
    ways = len(cache.data_rd_q) // 32
    tag_bits = 30 - (way_words.bit_length() - 1)
    addr = _phys_addr(index)
    row = (addr >> 2) % way_words
    set_index = row // words
    tag = addr >> (32 - tag_bits)
    line = addr >> (2 + (words.bit_length() - 1))
    valid = int(cache.valid_q.value)
    tags = int(cache.tag_mem[set_index].value)
    way = None
    for w in range(ways):
        if (valid >> (w * sets + set_index)) & 1 and ((tags >> (tag_bits * w)) & ((1 << tag_bits) - 1)) == tag:
            way = w
    return row, set_index, tag, line, row % words, way


def _lane(row: int, way: int) -> int:
    return (row >> (32 * way)) & 0xFFFF_FFFF


def read_word(dut, index: int) -> int:
    """The word at backing-memory word index `index` (the RAM array's index). The data cache is write-back, so RAM
    alone can be stale: a read takes a valid cache line, else a dirty line being written back, else RAM with pending
    MSHR bytes on top."""
    word = int(dut.unified_mem_inst.instr_ram[index].value) & 0xFFFF_FFFF
    cache = dcache(dut)
    if cache is None:
        return word
    row, set_index, tag, line, word_in_line, way = _locate(cache, index)
    if way is not None:
        return _lane(int(cache.data_mem[row].value), way)
    if (int(cache.eng_state.value) in (E_EVICT_READ, E_EVICT_WRITE) and not int(cache.eng_clean.value) and
            int(cache.eng_set.value) == set_index and int(cache.eng_tag.value) == tag):
        return _lane(int(cache.data_mem[row].value), int(cache.eng_way.value))
    words = len(cache.data_mem) // len(cache.tag_mem)
    line_bits = 30 - (words.bit_length() - 1)
    lines, bes, datas = (int(x.value) for x in (cache.mshr_line_q, cache.mshr_be_q, cache.mshr_data_q))
    for i in range(int(cache.mshr_count.value)):
        if (lines >> (i * line_bits)) & ((1 << line_bits) - 1) != line:
            continue
        be = (bes >> (4 * words * i + 4 * word_in_line)) & 0xF
        data = (datas >> (32 * words * i + 32 * word_in_line)) & 0xFFFF_FFFF
        for byte in range(4):
            if (be >> byte) & 1:
                mask = 0xFF << (8 * byte)
                word = (word & ~mask) | (data & mask)
    return word & 0xFFFF_FFFF


# ---- Programs

def elf32_symbols(elf: bytes) -> dict:
    """Name to value for every named symbol of a little-endian ELF32 file."""
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


def load_symbols(directory: Path) -> dict:
    """The symbols assemble() wrote, read back in the simulation process."""
    table = {}
    for line in (directory / "symbols.txt").read_text().splitlines():
        value, name = line.split()
        table[name] = int(value, 16)
    return table


def pte(pa: int, flags: int) -> int:
    """An Sv32 page-table entry for physical address pa."""
    return ((pa >> 12) << 10) | flags


def assemble(directory: Path, name: str, program: str, linker_script: str,
             march: str = "rv32ima_zicsr_zifencei") -> dict:
    """Link an assembly program into <name>.elf and image.bin, write its symbols.txt, and return the symbols."""
    directory.mkdir(parents=True, exist_ok=True)
    src = directory / f"{name}.S"
    lds = directory / f"{name}.ld"
    elf = directory / f"{name}.elf"
    src.write_text(program)
    lds.write_text(linker_script)
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc", f"-march={march}", "-mabi=ilp32",
            "-nostdlib", "-ffreestanding", "-Wl,--no-relax", "-Wl,-m,elf32lriscv",
            "-T", str(lds), str(src), "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(directory / "image.bin")],
                   check=True)
    symbols = elf32_symbols(elf.read_bytes())
    (directory / "symbols.txt").write_text("".join(f"{value:08x} {sym}\n" for sym, value in sorted(symbols.items())))
    return symbols


def _shared_build(toplevel: str, sources: list, parameters: dict, defines: list, compile_args: list,
                  waves: bool) -> Path:
    """The build directory for one configuration of a toplevel. Runs with the same configuration share it: the
    first compiles the model, later ones find nothing changed and only start a new simulation. Each pytest-xdist
    worker keeps its own copy, so two processes never build into the same directory."""
    key = json.dumps([toplevel, sources, sorted(parameters.items()), sorted(defines), compile_args, waves])
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return Path.cwd() / "sim_build" / f"{toplevel}_{digest}_{worker}"


def run_top(module: str, *, parameters: dict = None, boot_image: Path = None, testcase: str = None,
            extra_env: dict = None, plus_args: list = None) -> None:
    """Run the cocotb tests of `module` (or only `testcase`) in one new simulation of top built with every rtl/
    file. boot_image is the hex file memory holds at time 0 (none: memory starts uninitialised)."""
    parameters = parameters or {}
    defines = [f'INSTR_HEX_FILE="{boot_image}"'] if boot_image else []
    waves = os.getenv("WAVES", "0") == "1"
    plus_args = list(plus_args or [])
    if waves and not any(a.startswith("+dumpfile=") for a in plus_args):
        # top.v dumps to riscv_cpu.fst in the build directory by default, which the runs sharing it would overwrite.
        (Path.cwd() / "waveforms").mkdir(exist_ok=True)
        dump = f"{module}_{testcase}.fst" if testcase else f"{module}.fst"
        plus_args.append(f"+dumpfile={Path.cwd() / 'waveforms' / dump}")
    sources = rtl_sources()
    run(
        verilog_sources=sources,
        toplevel="top",
        module=module,
        testcase=testcase,
        parameters=parameters,
        includes=[str(find_repo_root() / "rtl" / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        defines=defines,
        sim_build=str(_shared_build("top", sources, parameters, defines, [], waves)),
        waves=waves,
        plus_args=plus_args,
        extra_env={
            "TOPLEVEL": "top",
            "MODULE": module,
            "COCOTB_TOPLEVEL": "top",
            "COCOTB_TEST_MODULES": module,
            **(extra_env or {}),
        },
    )


def run_unit(toplevel: str, module: str, sources: list, *, parameters: dict = None, testcase: str = None,
             extra_env: dict = None, compile_args: list = None) -> None:
    """Build one module (paths relative to the repo root) and run the cocotb tests of `module` on it."""
    root = find_repo_root()
    sources = [str(root / s) for s in sources]
    parameters = parameters or {}
    compile_args = compile_args or []
    run(
        verilog_sources=sources,
        toplevel=toplevel,
        module=module,
        testcase=testcase,
        parameters=parameters,
        includes=[str(root / "rtl" / "include")],
        simulator="verilator",
        timescale="1ns/1ps",
        sim_build=str(_shared_build(toplevel, sources, parameters, [], compile_args, False)),
        compile_args=compile_args,
        extra_env={
            "TOPLEVEL": toplevel,
            "MODULE": module,
            "COCOTB_TOPLEVEL": toplevel,
            "COCOTB_TEST_MODULES": module,
            **(extra_env or {}),
        },
    )


# ---- Instruction-word programs

def program_hex(folder: str, name: str, words, min_words: int) -> str:
    """Write instruction words as a boot image, four per line and padded with NOPs to at least min_words, into
    build/<folder>/<name>.hex, and return its path."""
    padded = list(words)
    while len(padded) % 4 or len(padded) < min_words:
        padded.append(NOP)
    path = build_directory(folder) / f"{name}.hex"
    with open(path, "w") as f:
        f.write("@00000000\n")
        for i in range(0, len(padded), 4):
            f.write(" ".join(f"{w:08x}" for w in padded[i:i + 4]) + "\n")
    return str(path.absolute())


def run_hex_programs(module: str, programs) -> None:
    """For each (name, builder) pair, build the program's boot image and run cocotb test test_<name> of module on it.
    The builder returns (name, hex path). With WAVES=1 each run dumps waveforms/<name>.vcd."""
    waves = os.getenv("WAVES", "0") == "1"
    if waves:
        (Path.cwd() / "waveforms").mkdir(exist_ok=True)
    for name, builder in programs:
        _, hex_file = builder()
        plus_args = [f"+dumpfile={Path.cwd() / 'waveforms' / f'{name}.vcd'}"] if waves else []
        run_top(module, testcase=f"test_{name}", boot_image=hex_file, plus_args=plus_args)


async def monitor_execution(dut, test_name, max_cycles=100):
    """Record every write on the core's data port for max_cycles: address to the last value written."""
    mem_writes = {}

    for cycle in range(max_cycles):
        try:
            if hasattr(dut.cpu_inst, 'module_mem_wr_en') and int(dut.cpu_inst.module_mem_wr_en.value):
                addr = int(dut.cpu_inst.module_write_addr.value)
                data = int(dut.cpu_inst.module_wr_data_out.value)
                mem_writes[addr] = data
                print(f"Cycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
        except Exception:
            pass

        try:
            pc_val = int(dut.pc_debug.value)
            instr_val = int(dut.instr_debug.value)
            if cycle % 20 == 0:
                print(f"Cycle {cycle}: PC=0x{pc_val:08x}, Instr=0x{instr_val:08x}")
        except Exception:
            pass

        await RisingEdge(dut.clk)

    return mem_writes


def _parks(word: int) -> bool:
    """jal x0 to itself or backwards: the end of a test program."""
    return (word & 0xFFF) == 0x06F and (word >> 31 or word >> 12 == 0)


async def run_program(dut, instr_mem, done=None, max_cycles=5000):
    """Load instr_mem at INSTR_MEM_BASE, run it until done(dut) or a parking jump retires."""
    program = list(instr_mem) + [PARK]
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    for index, word in enumerate(program):
        dut.unified_mem_inst.instr_ram[index].value = word
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    cpu = dut.cpu_inst
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if done is not None:
            if done(dut):
                break
        elif int(cpu.instret_increment.value):
            index = (int(cpu.id_ex_inst0_pc_out.value) - INSTR_MEM_BASE) // 4
            if 0 <= index < len(program) and _parks(program[index]):
                break
    else:
        raise AssertionError(f"the program did not finish within {max_cycles} cycles")
    # Older instructions are still in MEM and WB.
    await ClockCycles(dut.clk, 15)


def run_tests(module, tests, parameters=None):
    """Run each cocotb test of module in its own simulation, on the shared build for these parameters."""
    waves = os.getenv("WAVES", "0") == "1"
    for test_name in tests:
        plus_args = []
        if waves:
            waveform_dir = Path.cwd() / "waveforms"
            waveform_dir.mkdir(exist_ok=True)
            plus_args = [f"+dumpfile={waveform_dir / f'{test_name}.fst'}"]
        run_top(module, parameters=parameters, testcase=test_name, plus_args=plus_args)
