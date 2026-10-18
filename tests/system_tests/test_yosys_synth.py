"""The RTL a board instantiates elaborates and synthesizes with Yosys.

The core is synthesized; the peripherals around it are elaborated and checked. unified_mem is the
simulation backing store and is not part of a board design.
"""

import subprocess
from pathlib import Path

CORE = "riscv_cpu"
PERIPHERALS = ["sv32_mmu", "mem_adapter", "store_buffer", "uart", "plic", "timer"]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _yosys(rtl_dir: Path, script: str) -> subprocess.CompletedProcess:
    sources = " ".join(str(p) for p in sorted(rtl_dir.rglob("*.v")) if p.name != "unified_mem.v")
    return subprocess.run(
        ["yosys", "-q", "-p", f"read_verilog -I{rtl_dir / 'include'} {sources}; {script}"],
        capture_output=True,
        text=True,
    )


def runCocotbTests():
    rtl_dir = _find_repo_root() / "rtl"
    checks = [(CORE, f"synth -flatten -top {CORE}; check -assert")]
    checks += [(name, f"hierarchy -check -top {name}; proc; flatten; opt_clean; check -assert")
               for name in PERIPHERALS]
    failures = []
    for name, script in checks:
        result = _yosys(rtl_dir, script)
        if result.returncode != 0:
            errors = [line for line in (result.stdout + result.stderr).splitlines() if "ERROR" in line]
            failures.append(f"{name}: {errors[0] if errors else result.stderr.strip()[-300:]}")
    assert not failures, "; ".join(failures)


if __name__ == "__main__":
    runCocotbTests()
