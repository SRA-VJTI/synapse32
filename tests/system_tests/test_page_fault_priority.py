"""Integrated regressions for AMO faults and younger return/WFI squashing."""

import subprocess
from pathlib import Path


def runCocotbTests(tmp_path):
    # This timed RTL harness checks architectural trap state directly, so it
    # needs no firmware toolchain or cocotb driver. Keep the suite's runner name.
    root = Path(__file__).resolve().parents[2]
    rtl = root / "rtl"
    sources = [
        root / "tests/testbenches/page_fault_priority_tb.v",
        rtl / "riscv_cpu.v",
        rtl / "execution_unit.v",
        rtl / "memory_unit.v",
        rtl / "writeback.v",
        rtl / "mmu/sv32_data_check.v",
        *sorted((rtl / "core_modules").glob("*.v")),
        *sorted((rtl / "pipeline_stages").glob("*.v")),
    ]
    build = tmp_path / "obj_dir"
    compiled = subprocess.run(
        ["verilator", "--binary", "--timing", "--top-module", "page_fault_priority_tb",
         "-Wno-fatal", f"-I{rtl / 'include'}", "--Mdir", str(build),
         *map(str, sources)],
        capture_output=True, text=True,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    failures = []
    for case_id in range(5):
        result = subprocess.run(
            [str(build / "Vpage_fault_priority_tb"), f"+CASE_ID={case_id}"],
            cwd=tmp_path, capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            failures.append(f"case {case_id}: {result.stdout}{result.stderr}")
    assert not failures, "\n".join(failures)
