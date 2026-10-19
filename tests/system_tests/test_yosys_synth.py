"""The RTL a board instantiates elaborates and synthesizes with Yosys.

The core and the top level are synthesized; the peripherals around the core are elaborated and checked.
unified_mem is the simulation backing store and is not part of a board design, so the top level sees it
as a black box. An out-of-range select becomes undefined logic in hardware, so its warning fails the test.
"""

import re
import subprocess
import tempfile
from pathlib import Path

CORE = "riscv_cpu"
TOP = "top"
PERIPHERALS = ["sv32_mmu", "mem_adapter", "store_buffer", "uart", "plic", "timer"]


def _find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def _unified_mem_blackbox(rtl_dir: Path, out_dir: Path) -> Path:
    source = (rtl_dir / "unified_mem.v").read_text()
    header = re.search(r"^module unified_mem\b.*?\);", source, re.MULTILINE | re.DOTALL)
    assert header, "unified_mem.v: module header not found"
    stub = out_dir / "unified_mem_blackbox.v"
    stub.write_text(f"(* blackbox *)\n{header.group(0)}\nendmodule\n")
    return stub


def _yosys(rtl_dir: Path, script: str, extra: str = "") -> subprocess.CompletedProcess:
    sources = " ".join(str(p) for p in sorted(rtl_dir.rglob("*.v")) if p.name != "unified_mem.v")
    return subprocess.run(
        ["yosys", "-q", "-p", f"read_verilog -I{rtl_dir / 'include'} {sources} {extra}; {script}"],
        capture_output=True,
        text=True,
    )


def runCocotbTests():
    rtl_dir = _find_repo_root() / "rtl"
    with tempfile.TemporaryDirectory() as tmp:
        stub = _unified_mem_blackbox(rtl_dir, Path(tmp))
        checks = [(CORE, f"synth -flatten -top {CORE}; check -assert", "")]
        checks += [(TOP, f"synth -flatten -top {TOP}; check -assert", str(stub))]
        checks += [(name, f"hierarchy -check -top {name}; proc; flatten; opt_clean; check -assert", "")
                   for name in PERIPHERALS]
        failures = []
        for name, script, extra in checks:
            result = _yosys(rtl_dir, script, extra)
            output = (result.stdout + result.stderr).splitlines()
            if result.returncode != 0:
                errors = [line for line in output if "ERROR" in line]
                failures.append(f"{name}: {errors[0] if errors else result.stderr.strip()[-300:]}")
            failures += [f"{name}: {line.strip()}" for line in output if "out of bounds" in line]
    assert not failures, "; ".join(failures)


if __name__ == "__main__":
    runCocotbTests()
