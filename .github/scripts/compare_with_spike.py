#!/usr/bin/env python3
"""Compare riscv-tests results between Spike (golden) and Verilator model.

Assumes riscv-tests has already been built, producing ELF binaries under:
  <riscv-tests>/isa/rv32*-p-*

Usage:
  python .github/scripts/compare_with_spike.py --riscv-tests /path/to/riscv-tests
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


TEST_NAME_RE = re.compile(r"^rv32(ui|um|ua)-p-")


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=env, cwd=cwd, text=True, capture_output=True)


def find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def discover_tests(isa_dir: Path, limit: int) -> list[Path]:
    tests = []
    for p in sorted(isa_dir.iterdir()):
        if not p.is_file():
            continue
        if TEST_NAME_RE.match(p.name):
            tests.append(p)
    if limit > 0:
        tests = tests[:limit]
    return tests


def tohost_addr(elf: Path) -> int:
    nm = run(["riscv64-unknown-elf-nm", str(elf)])
    if nm.returncode != 0:
        raise RuntimeError(f"nm failed for {elf}:\n{nm.stderr}")
    for line in nm.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[-1] == "tohost":
            return int(parts[0], 16)
    raise RuntimeError(f"tohost symbol not found in {elf}")


def elf_to_hex(elf: Path, out_hex: Path) -> None:
    out_hex.parent.mkdir(parents=True, exist_ok=True)
    bin_file = out_hex.with_suffix(".bin")
    rc = run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(bin_file)])
    if rc.returncode != 0:
        raise RuntimeError(f"objcopy binary failed for {elf}:\n{rc.stderr}")
    # Match existing test image sizing strategy.
    rc = run(["truncate", "-s", "2048", str(bin_file)])
    if rc.returncode != 0:
        raise RuntimeError(f"truncate failed for {bin_file}:\n{rc.stderr}")
    rc = run(
        [
            "riscv64-unknown-elf-objcopy",
            "-I",
            "binary",
            "-O",
            "verilog",
            "--verilog-data-width=4",
            "--reverse-bytes=4",
            str(bin_file),
            str(out_hex),
        ]
    )
    if rc.returncode != 0:
        raise RuntimeError(f"objcopy verilog failed for {elf}:\n{rc.stderr}")


def run_spike(elf: Path) -> tuple[bool, str]:
    rc = run(["spike", "--isa=rv32ima", str(elf)])
    ok = rc.returncode == 0
    detail = (rc.stdout + "\n" + rc.stderr).strip()
    return ok, detail


def run_verilator(repo_root: Path, hex_file: Path, tohost: int, max_cycles: int) -> tuple[bool, str]:
    env = os.environ.copy()
    env["ISA_HEX_FILE"] = str(hex_file)
    env["ISA_TOHOST_ADDR"] = hex(tohost)
    env["ISA_MAX_CYCLES"] = str(max_cycles)
    rc = run([sys.executable, "tests/system_tests/test_riscv_isa.py"], env=env, cwd=repo_root)
    ok = rc.returncode == 0
    detail = (rc.stdout + "\n" + rc.stderr).strip()
    return ok, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--riscv-tests", required=True, type=Path, help="Path to built riscv-tests repo")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of ISA tests (0 = all)")
    ap.add_argument("--max-cycles", type=int, default=200000, help="Max cycles per Verilator ISA test")
    ap.add_argument("--report", type=Path, default=Path(".github/artifacts/isa/compare_report.json"))
    args = ap.parse_args()

    repo_root = find_repo_root()
    isa_dir = args.riscv_tests / "isa"
    if not isa_dir.exists():
        print(f"Missing isa dir: {isa_dir}", file=sys.stderr)
        return 2

    tests = discover_tests(isa_dir, args.limit)
    if not tests:
        print("No rv32*-p-* test binaries found. Did riscv-tests build succeed?", file=sys.stderr)
        return 2

    out_hex_dir = repo_root / ".github" / "artifacts" / "isa" / "build_hex"
    results = []
    mismatches = []

    for elf in tests:
        try:
            th = tohost_addr(elf)
            hex_file = out_hex_dir / f"{elf.name}.hex"
            elf_to_hex(elf, hex_file)
            spike_ok, spike_log = run_spike(elf)
            verilator_ok, verilator_log = run_verilator(repo_root, hex_file, th, args.max_cycles)
            same = spike_ok == verilator_ok
            rec = {
                "test": elf.name,
                "spike_pass": spike_ok,
                "verilator_pass": verilator_ok,
                "match": same,
            }
            results.append(rec)
            if not same:
                mismatches.append(
                    {
                        **rec,
                        "spike_log_tail": spike_log[-1200:],
                        "verilator_log_tail": verilator_log[-1200:],
                    }
                )
            print(f"[{elf.name}] spike={spike_ok} verilator={verilator_ok} match={same}")
        except Exception as exc:
            rec = {
                "test": elf.name,
                "spike_pass": False,
                "verilator_pass": False,
                "match": False,
                "error": str(exc),
            }
            results.append(rec)
            mismatches.append(rec)
            print(f"[{elf.name}] ERROR: {exc}")

    summary = {
        "total": len(results),
        "matches": len([r for r in results if r.get("match")]),
        "mismatches": len(mismatches),
        "results": results,
        "mismatch_details": mismatches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2), encoding="ascii")
    print(f"Wrote report: {args.report}")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
