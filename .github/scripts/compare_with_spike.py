#!/usr/bin/env python3
"""Compare riscv-tests and riscv-arch-test results between Spike (golden) and Verilator model.

riscv-tests must already be built, producing ELF binaries under <riscv-tests>/isa/rv32*-p-*. riscv-arch-test tests
are compiled here from <riscv-arch-test>/riscv-test-suite/rv32i_m/<suite>/src with the target files in
.github/arch-test, selected by their RVTEST_CASE conditions as RISCOF does.

Usage:
  python .github/scripts/compare_with_spike.py --riscv-tests /path/to/riscv-tests
  python .github/scripts/compare_with_spike.py --arch-test /path/to/riscv-arch-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_SUITES = "rv32ui,rv32um,rv32ua,rv32mi,rv32si"
TEST_NAME_RE = re.compile(r"^(rv32(ui|um|ua|mi|si))-p-[A-Za-z0-9_-]+$")
# Spike v1.1.0 predates the Zicntr name; its counters are always present.
SPIKE_ISA = "rv32ima_zicsr"
NOT_APPLICABLE = {
    "rv32ui-p-ma_data": "Zicclsm (misaligned loads/stores) not implemented; core traps",
    "rv32mi-p-pmpaddr": "PMP not implemented; pmpaddr0/pmpcfg0 are plain registers",
}
DEFAULT_ARCH_SUITES = "I,M,A,Zifencei,privilege"
# What riscv-arch-test's RVTEST_CASE conditions are evaluated against: our ISA and platform.
ARCH_ISA = "RV32IMAZicsr_Zifencei"
ARCH_PLATFORM = {"hw_data_misaligned_support": "False"}
ARCH_MARCH = "rv32ima_zicsr_zifencei"
RVTEST_CASE_RE = re.compile(r'RVTEST_CASE\(\s*\d+\s*,\s*"([^"]*)"')
# Empty: every compared test's trace now matches Spike. A listed test's pass/fail must still match
# Spike, only its trace is not compared; add one with a recorded reason.
TRACE_NOT_COMPARABLE: dict[str, str] = {}
# Empty: every rv32i_m test in the selected suites applies to our ISA and platform. A test no
# RVTEST_CASE selects fails the run unless it is listed here with a recorded reason.
ARCH_NOT_APPLICABLE: dict[str, str] = {}


def parse_suites(suites: str) -> set[str]:
    return {suite.strip() for suite in suites.split(",") if suite.strip()}


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=env, cwd=cwd, text=True, capture_output=True)


def find_repo_root() -> Path:
    cur = Path.cwd()
    while not (cur / "rtl").exists():
        if cur.parent == cur:
            raise FileNotFoundError("Could not locate repo root (no rtl/ directory found)")
        cur = cur.parent
    return cur


def discover_tests(isa_dir: Path, suites: set[str], limit: int) -> list[Path]:
    tests = []
    for p in sorted(isa_dir.iterdir()):
        if not p.is_file():
            continue
        match = TEST_NAME_RE.match(p.name)
        if match and match.group(1) in suites:
            tests.append(p)
    if limit > 0:
        tests = tests[:limit]
    return tests


def require_suites(tests: list[Path], required: set[str]) -> None:
    discovered = {
        match.group(1)
        for test in tests
        if (match := TEST_NAME_RE.match(test.name))
    }
    missing = sorted(required - discovered)
    if missing:
        found = ", ".join(sorted(discovered)) or "<none>"
        raise RuntimeError(
            "Missing required riscv-tests suites: "
            f"{', '.join(missing)}. Discovered suites: {found}"
        )


def arch_test_macros(source: Path) -> list[str] | None:
    """Macros of every RVTEST_CASE whose checks hold for ARCH_ISA and ARCH_PLATFORM; None if no case applies."""
    macros, applies = [], False
    for case in RVTEST_CASE_RE.findall(source.read_text(errors="replace")):
        holds, defines = True, []
        for item in (part.strip() for part in case.replace("//", "").split(";")):
            if item.startswith("check ISA:=regex(") and item.endswith(")"):
                holds = holds and re.match(item[len("check ISA:=regex("):-1], ARCH_ISA) is not None
            elif item.startswith("check "):
                key, _, value = item[len("check "):].partition(":=")
                holds = holds and ARCH_PLATFORM.get(key.strip()) == value.strip()
            elif item.startswith("def "):
                defines.append(item[len("def "):].strip())
        if holds:
            applies = True
            macros += defines
    return macros if applies else None


def build_arch_tests(arch_dir: Path, suites: set[str], repo_root: Path, out_dir: Path) -> tuple[list[Path], list[dict]]:
    target_dir = repo_root / ".github" / "arch-test"
    env_dir = arch_dir / "riscv-test-suite" / "env"
    out_dir.mkdir(parents=True, exist_ok=True)
    elves, skipped = [], []
    for suite in sorted(suites):
        sources = sorted((arch_dir / "riscv-test-suite" / "rv32i_m" / suite / "src").glob("*.S"))
        if not sources:
            raise RuntimeError(f"no riscv-arch-test sources for rv32i_m/{suite} under {arch_dir}")
        for source in sources:
            name = f"rv32i_m-{suite}-{source.stem}"
            macros = arch_test_macros(source)
            if macros is None:
                skipped.append({"test": name, "reason": f"no RVTEST_CASE applies to {ARCH_ISA} {ARCH_PLATFORM}"})
                continue
            elf = out_dir / name
            rc = run([
                "riscv64-unknown-elf-gcc", f"-march={ARCH_MARCH}", "-mabi=ilp32", "-static", "-mcmodel=medany",
                "-fvisibility=hidden", "-nostdlib", "-nostartfiles", "-T", str(target_dir / "link.ld"),
                "-I", str(target_dir), "-I", str(env_dir), "-DXLEN=32", *[f"-D{m}" for m in macros],
                str(source), "-o", str(elf),
            ])
            if rc.returncode != 0:
                raise RuntimeError(f"compiling {source} failed:\n{rc.stderr}")
            elves.append(elf)
    return elves, skipped


def tohost_addr(elf: Path) -> int:
    nm = run(["riscv64-unknown-elf-nm", str(elf)])
    if nm.returncode != 0:
        raise RuntimeError(f"nm failed for {elf}:\n{nm.stderr}")
    for line in nm.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[-1] == "tohost":
            return int(parts[0], 16)
    raise RuntimeError(f"tohost symbol not found in {elf}")


def entry_address(elf: Path) -> int:
    rc = run(["riscv64-unknown-elf-readelf", "-h", str(elf)])
    if rc.returncode != 0:
        raise RuntimeError(f"readelf failed for {elf}:\n{rc.stderr}")
    match = re.search(r"Entry point address:\s+0x([0-9a-f]+)", rc.stdout)
    if not match:
        raise RuntimeError(f"no entry point in {elf}")
    return int(match.group(1), 16)


def elf_to_hex(elf: Path, out_hex: Path) -> None:
    out_hex.parent.mkdir(parents=True, exist_ok=True)
    bin_file = out_hex.with_suffix(".bin")
    rc = run(["riscv64-unknown-elf-objcopy", "-O", "binary", str(elf), str(bin_file)])
    if rc.returncode != 0:
        raise RuntimeError(f"objcopy binary failed for {elf}:\n{rc.stderr}")
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


# Implementation-defined values: counters and mvendorid/marchid/mimpid.
IMPLEMENTATION_DEFINED_CSRS = {
    0xC00, 0xC01, 0xC02, 0xC80, 0xC81, 0xC82, 0xB00, 0xB02, 0xB80, 0xB82,
    0xF11, 0xF12, 0xF13,
}
SPIKE_COMMIT_RE = re.compile(r"^core\s+\d+:\s+\d\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$")


def reads_implementation_defined_csr(insn: int) -> bool:
    return (insn & 0x7F) == 0x73 and ((insn >> 12) & 0x7) not in (0, 4) and (insn >> 20) in IMPLEMENTATION_DEFINED_CSRS


def store_width(insn: int) -> int:
    opcode = insn & 0x7F
    if opcode == 0x23:  # sb/sh/sw
        return 1 << ((insn >> 12) & 0x3)
    if opcode == 0x2F:  # sc.w / amo*.w
        return 4
    raise ValueError(f"memory write from non-store instruction 0x{insn:08x}")


def parse_spike_commits(path: Path, entry_pc: int, tohost: int) -> tuple[list[tuple], list[tuple]]:
    registers, memory = [], []
    started = False
    for commit, line in enumerate(path.read_text(errors="replace").splitlines()):
        match = SPIKE_COMMIT_RE.match(line)
        if not match:
            continue
        pc, insn = int(match.group(1), 16), int(match.group(2), 16)
        started = started or pc == entry_pc  # skip Spike's boot ROM
        if not started:
            continue
        tokens = re.sub(r"\bx\s+(\d+)\b", r"x\1", match.group(3)).split()
        writes, bytes_written = [], []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if re.fullmatch(r"x\d+", token) and i + 1 < len(tokens):
                writes.append((pc, int(token[1:]), int(tokens[i + 1], 16) & 0xFFFFFFFF, insn, reads_implementation_defined_csr(insn), commit))
                i += 2
            elif token == "mem" and i + 1 < len(tokens):
                address = int(tokens[i + 1], 16)
                if i + 2 < len(tokens) and re.fullmatch(r"0x[0-9a-f]+", tokens[i + 2]):
                    value = int(tokens[i + 2], 16)
                    for index in range(store_width(insn)):
                        bytes_written.append((pc, (address + index) & 0xFFFFFFFF, (value >> (8 * index)) & 0xFF, insn, False, commit))
                    i += 3
                else:
                    i += 2
            else:
                i += 1
        if any(entry[1] == tohost for entry in bytes_written):
            break
        registers += writes
        memory += bytes_written
    return registers, memory


def parse_rtl_trace(path: Path, tohost: int) -> tuple[list[tuple], list[tuple]]:
    registers, memory = [], []
    for line in path.read_text().splitlines():
        fields = line.split()
        if fields[0] == "x":
            registers.append((int(fields[1], 16), int(fields[2]), int(fields[3], 16)))
        elif int(fields[2], 16) == tohost:
            break
        else:
            memory.append((int(fields[1], 16), int(fields[2], 16), int(fields[3], 16)))
    return registers, memory


def first_divergence(name: str, spike: list[tuple], rtl: list[tuple]) -> tuple[float, str] | None:
    for index in range(max(len(spike), len(rtl))):
        if index >= len(spike):
            pc, where, value = rtl[index]
            order = spike[-1][5] + 0.5 if spike else 0
            return order, f"{name} {index}: only RTL has pc 0x{pc:08x} {where:#x}={value:#x} (Spike {len(spike)} entries, RTL {len(rtl)})"
        s_pc, s_where, s_value, insn, may_differ, commit = spike[index]
        if index >= len(rtl):
            return commit, f"{name} {index}: only Spike has pc 0x{s_pc:08x} (insn 0x{insn:08x}) {s_where:#x}={s_value:#x} (Spike {len(spike)} entries, RTL {len(rtl)})"
        r_pc, r_where, r_value = rtl[index]
        if (s_pc, s_where) != (r_pc, r_where) or (s_value != r_value and not may_differ):
            return commit, (
                f"{name} {index}: Spike pc 0x{s_pc:08x} (insn 0x{insn:08x}) {s_where:#x}={s_value:#x}, "
                f"RTL pc 0x{r_pc:08x} {r_where:#x}={r_value:#x}"
            )
    return None


def compare_traces(spike: tuple, rtl: tuple) -> str | None:
    found = [d for d in (first_divergence("register write", spike[0], rtl[0]),
                         first_divergence("memory write", spike[1], rtl[1])) if d]
    return min(found)[1] if found else None


def run_spike(elf: Path, commit_log: Path) -> tuple[bool, str]:
    rc = run(["spike", "--isa=" + SPIKE_ISA, "-l", "--log-commits", f"--log={commit_log}", str(elf)])
    ok = rc.returncode == 0
    detail = (rc.stdout + "\n" + rc.stderr).strip()
    return ok, detail


def run_verilator(
    repo_root: Path,
    hex_file: Path,
    runtime_hex: Path,
    sim_build: Path,
    tohost: int,
    max_cycles: int,
    compile_model: bool,
    trace_file: Path,
    mem_latency: int,
    fetch_latency: int,
) -> tuple[bool, str]:
    # The image is read by the RTL at simulator start.  Keep the Verilog
    # define and build directory constant, changing only the file contents.
    runtime_hex.parent.mkdir(parents=True, exist_ok=True)
    runtime_hex.write_bytes(hex_file.read_bytes())
    env = os.environ.copy()
    env["ISA_HEX_FILE"] = str(runtime_hex)
    env["ISA_SIM_HEX_FILE"] = str(runtime_hex)
    env["ISA_SIM_BUILD"] = str(sim_build)
    env["ISA_FORCE_COMPILE"] = "1" if compile_model else "0"
    env["ISA_TOHOST_ADDR"] = hex(tohost)
    env["ISA_MAX_CYCLES"] = str(max_cycles)
    env["ISA_TRACE_FILE"] = str(trace_file)
    env["ISA_MEM_LATENCY"] = str(mem_latency)
    env["ISA_FETCH_LATENCY"] = str(fetch_latency)
    rc = run([sys.executable, "tests/system_tests/test_riscv_isa.py"], env=env, cwd=repo_root)
    ok = rc.returncode == 0
    detail = (rc.stdout + "\n" + rc.stderr).strip()
    return ok, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--riscv-tests", type=Path, help="Path to built riscv-tests repo")
    ap.add_argument("--arch-test", type=Path, help="Path to a riscv-arch-test checkout")
    ap.add_argument("--arch-suites", default=DEFAULT_ARCH_SUITES, help="Comma-separated rv32i_m suites to compare")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of ISA tests (0 = all)")
    ap.add_argument("--max-cycles", type=int, default=200000, help="Max cycles per Verilator ISA test")
    ap.add_argument("--mem-latency", type=int, default=0, help="Cycles the RTL's memory takes to answer")
    ap.add_argument("--fetch-latency", type=int, default=None, help="Fetch side only (default: --mem-latency)")
    ap.add_argument("--report", type=Path, default=Path(".github/artifacts/isa/compare_report.json"))
    ap.add_argument(
        "--suites",
        default=DEFAULT_SUITES,
        help="Comma-separated riscv-tests suite prefixes to compare",
    )
    args = ap.parse_args()

    repo_root = find_repo_root()
    if args.riscv_tests is None and args.arch_test is None:
        print("Give --riscv-tests, --arch-test or both", file=sys.stderr)
        return 2
    all_tests = []
    skipped = []
    arch_skipped = []
    if args.riscv_tests is not None:
        isa_dir = args.riscv_tests / "isa"
        if not isa_dir.exists():
            print(f"Missing isa dir: {isa_dir}", file=sys.stderr)
            return 2
        suites = parse_suites(args.suites)
        all_tests = discover_tests(isa_dir, suites, 0)
        require_suites(all_tests, suites)
    if args.arch_test is not None:
        arch_elves, arch_skipped = build_arch_tests(
            args.arch_test, parse_suites(args.arch_suites), repo_root,
            repo_root / ".github" / "artifacts" / "isa" / "arch_elf",
        )
        all_tests += arch_elves
        skipped += arch_skipped
    tests = all_tests[: args.limit] if args.limit > 0 else all_tests
    if not tests:
        print("No test binaries found. Did riscv-tests build succeed?", file=sys.stderr)
        return 2

    out_hex_dir = repo_root / ".github" / "artifacts" / "isa" / "build_hex"
    runtime_hex = repo_root / ".github" / "artifacts" / "isa" / "runtime.hex"
    fetch_latency = args.mem_latency if args.fetch_latency is None else args.fetch_latency
    sim_build = (repo_root / ".github" / "artifacts" / "isa" /
                 f"sim_build_riscv_isa_lat{args.mem_latency}_fetch{fetch_latency}")
    trace_dir = repo_root / ".github" / "artifacts" / "isa" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    results = []
    mismatches = []
    trace_not_comparable = []
    model_compiled = False

    for elf in tests:
        if elf.name in NOT_APPLICABLE:
            skipped.append({"test": elf.name, "reason": NOT_APPLICABLE[elf.name]})
            print(f"[{elf.name}] SKIPPED: {NOT_APPLICABLE[elf.name]}")
            continue
        try:
            th = tohost_addr(elf)
            hex_file = out_hex_dir / f"{elf.name}.hex"
            elf_to_hex(elf, hex_file)
            spike_commits = trace_dir / f"{elf.name}.spike.log"
            rtl_trace = trace_dir / f"{elf.name}.rtl.trace"
            rtl_trace.unlink(missing_ok=True)
            spike_ok, spike_log = run_spike(elf, spike_commits)
            verilator_ok, verilator_log = run_verilator(
                repo_root,
                hex_file,
                runtime_hex,
                sim_build,
                th,
                args.max_cycles,
                compile_model=not model_compiled,
                trace_file=rtl_trace,
                mem_latency=args.mem_latency,
                fetch_latency=fetch_latency,
            )
            model_compiled = True
            if elf.name in TRACE_NOT_COMPARABLE:
                divergence = None
                trace_not_comparable.append({"test": elf.name, "reason": TRACE_NOT_COMPARABLE[elf.name]})
            elif rtl_trace.is_file() and spike_commits.is_file():
                divergence = compare_traces(
                    parse_spike_commits(spike_commits, entry_address(elf), th), parse_rtl_trace(rtl_trace, th)
                )
            else:
                divergence = "commit trace missing"
            # A test failing on both proves nothing, so both must pass.
            same = spike_ok and verilator_ok and divergence is None
            rec = {
                "test": elf.name,
                "spike_pass": spike_ok,
                "verilator_pass": verilator_ok,
                "trace_match": divergence is None if elf.name not in TRACE_NOT_COMPARABLE else None,
                "match": same,
                "tohost": f"0x{th:x}",
            }
            if divergence:
                rec["trace_divergence"] = divergence
            results.append(rec)
            if not same:
                mismatches.append(
                    {
                        **rec,
                        "spike_log_tail": spike_log[-8000:],
                        "verilator_log_tail": verilator_log[-8000:],
                    }
                )
            trace = "not comparable" if elf.name in TRACE_NOT_COMPARABLE else divergence is None
            print(f"[{elf.name}] spike={spike_ok} verilator={verilator_ok} trace={trace} match={same}")
            if divergence:
                print(f"    first divergence: {divergence}")
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

    for entry in arch_skipped:
        if entry["test"] in ARCH_NOT_APPLICABLE:
            continue
        rec = {"test": entry["test"], "spike_pass": False, "verilator_pass": False, "match": False,
               "error": f"not compared ({entry['reason']}) and not in ARCH_NOT_APPLICABLE"}
        mismatches.append(rec)
        print(f"[{entry['test']}] ERROR: {rec['error']}")

    summary = {
        "mem_latency": args.mem_latency,
        "fetch_latency": fetch_latency,
        "total": len(results),
        "matches": len([r for r in results if r.get("match")]),
        "mismatches": len(mismatches),
        "skipped": skipped,
        "trace_not_comparable": trace_not_comparable,
        "results": results,
        "mismatch_details": mismatches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2), encoding="ascii")
    print(f"Wrote report: {args.report}")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
