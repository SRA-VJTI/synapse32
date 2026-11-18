"""Every size the core offers elaborates at its limits, and one step past a limit stops elaboration.

Verilator lints riscv_cpu with the sizes set as parameters; warnings are not fatal, as in the simulation builds. A
module out of range instantiates its missing *_parameters_out_of_range module, which names it in the error. The
cache enables lint clean both ways, so a build that sets them on the command line compiles.
"""

import subprocess
from pathlib import Path

CORE = "riscv_cpu"

VALID = [
    {"ICACHE_WAYS": 1, "ICACHE_SET_INDEX_BITS": 1, "ICACHE_WORD_OFFSET_BITS": 1},
    {"ICACHE_WAYS": 16, "ICACHE_SET_INDEX_BITS": 8, "ICACHE_WORD_OFFSET_BITS": 2},
    {"ICACHE_SET_INDEX_BITS": 1, "ICACHE_WORD_OFFSET_BITS": 9},
    {"DCACHE_WAYS": 1, "DCACHE_SET_INDEX_BITS": 1, "DCACHE_WORD_OFFSET_BITS": 1, "NUM_MSHR": 1},
    {"DCACHE_WAYS": 8, "DCACHE_SET_INDEX_BITS": 8, "DCACHE_WORD_OFFSET_BITS": 2, "NUM_MSHR": 16},
    {"DCACHE_SET_INDEX_BITS": 6, "DCACHE_WORD_OFFSET_BITS": 4},
    {"TLB_ENTRIES": 1, "STORE_BUFFER_DEPTH": 1},
    {"TLB_ENTRIES": 64, "STORE_BUFFER_DEPTH": 255},
]

CLEAN = [
    {"ICACHE_ENABLE": 0, "DCACHE_ENABLE": 0},
    {"ICACHE_ENABLE": 1, "DCACHE_ENABLE": 1},
]

INVALID = [
    ({"ICACHE_WAYS": 17}, "icache"),
    ({"ICACHE_WORD_OFFSET_BITS": 0}, "icache"),
    ({"ICACHE_SET_INDEX_BITS": 9}, "icache"),
    ({"DCACHE_WAYS": 3}, "dcache"),
    ({"DCACHE_SET_INDEX_BITS": 0}, "dcache"),
    ({"DCACHE_SET_INDEX_BITS": 8, "DCACHE_WORD_OFFSET_BITS": 3}, "dcache"),
    ({"NUM_MSHR": 17}, "dcache"),
    ({"TLB_ENTRIES": 0}, "sv32_tlb"),
    ({"TLB_ENTRIES": 65}, "sv32_tlb"),
    ({"STORE_BUFFER_DEPTH": 0}, "store_buffer"),
    ({"STORE_BUFFER_DEPTH": 256}, "store_buffer"),
    ({"CACHEABLE_REGIONS": 0, "CACHEABLE_BASES": 0, "CACHEABLE_SIZES": 0}, "riscv_cpu"),
]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _lint(rtl_dir: Path, parameters: dict, fatal: bool = False) -> subprocess.CompletedProcess:
    sources = [str(p) for p in sorted(rtl_dir.rglob("*.v")) if p.name != "unified_mem.v"]
    warnings = [] if fatal else ["-Wno-fatal"]
    return subprocess.run(
        ["verilator", "--lint-only", *warnings, f"-I{rtl_dir / 'include'}", f"-I{rtl_dir}", "--top-module", CORE]
        + [f"-G{name}={value}" for name, value in parameters.items()] + sources,
        capture_output=True,
        text=True,
    )


def runCocotbTests():
    rtl_dir = _find_repo_root() / "rtl"
    failures = []
    for parameters in VALID:
        result = _lint(rtl_dir, parameters)
        if result.returncode != 0:
            failures.append(f"{parameters} should elaborate: {result.stderr.strip().splitlines()[:1]}")
    for parameters in CLEAN:
        result = _lint(rtl_dir, parameters, fatal=True)
        if result.returncode != 0:
            failures.append(f"{parameters} should lint clean: {result.stderr.strip().splitlines()[:1]}")
    for parameters, module in INVALID:
        result = _lint(rtl_dir, parameters)
        if result.returncode == 0 or f"{module}_parameters_out_of_range" not in result.stderr:
            failures.append(f"{parameters} should stop {module}'s elaboration: {result.stderr.strip().splitlines()[:1]}")
    assert not failures, "; ".join(failures)


if __name__ == "__main__":
    runCocotbTests()
