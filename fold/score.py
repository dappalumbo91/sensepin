"""Score Sensepin v0. The behavior bar for tally is probe 00. The size bar is the host program."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import foldc

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
BUILD = ROOT / "build"
EXAMPLES = ROOT / "examples"


def load_probe():
    path = PROJECT / "probes" / "00-tally" / "measure.py"
    spec = importlib.util.spec_from_file_location("probe00", path)
    if spec is None or spec.loader is None:
        raise SystemExit("probe 00 scorer is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True)


def compile_example(name: str) -> Path:
    source = EXAMPLES / f"{name}.sensepin"
    exe = BUILD / f"{name}.exe"
    proc = run(
        [
            sys.executable,
            str(ROOT / "foldc.py"),
            str(source),
            "-o",
            str(BUILD / f"{name}.c"),
            "--exe",
            str(exe),
        ]
    )
    if proc.returncode != 0:
        sys.stdout.buffer.write(proc.stdout)
        sys.stderr.buffer.write(proc.stderr)
        raise SystemExit(f"{name} failed to compile")
    return exe


def check(name: str, proc: subprocess.CompletedProcess[bytes], code: int, out: bytes, err: bytes) -> str | None:
    if proc.returncode == code and proc.stdout == out and proc.stderr == err:
        return None
    return (
        f"{name} exited {proc.returncode} expected {code}\n"
        f"stdout {proc.stdout!r} expected {out!r}\n"
        f"stderr {proc.stderr!r} expected {err!r}"
    )


def expect_compile_error(text: str, needle: str) -> str | None:
    try:
        foldc.compile_text(text)
    except foldc.FoldError as exc:
        if needle not in str(exc):
            return f"compile error {exc} does not mention {needle}"
        return None
    return "compile succeeded where the contract requires an error"


def write_fixture(name: str, data: bytes) -> Path:
    path = BUILD / "fixtures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    (PROJECT / "results").mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    reject = run(
        [
            sys.executable,
            str(ROOT / "foldc.py"),
            str(EXAMPLES / "reject-gauge.sensepin"),
            "-o",
            str(BUILD / "reject.c"),
        ]
    )
    if reject.returncode == 0 or b"gauge i64" not in reject.stderr:
        failures.append(f"unnamed gauge compiled or the error changed: {reject.stderr!r}")
    unused = expect_compile_error("phase console\ngauge file\nfn main\nend\n", "unused")
    if unused:
        failures.append(unused)

    double = compile_example("double")
    proc = run([str(double)])
    bad = check("double", proc, 0, b"42\n", b"")
    if bad:
        failures.append(bad)

    overflow = compile_example("overflow")
    proc = run([str(overflow)])
    bad = check("overflow", proc, 1, b"", b"overflow\n")
    if bad:
        failures.append(bad)

    probe = load_probe()
    (PROJECT / "results" / "probe-00-work").mkdir(parents=True, exist_ok=True)
    tally = compile_example("tally")
    tally_cases = probe.build_cases()
    tally_pass = 0
    for case in tally_cases:
        proc = run([str(tally), *case["args"]])
        expect = case["expect"]
        bad = check(f"tally {case['name']}", proc, expect["code"], expect["out"], expect["err"])
        if bad:
            failures.append(bad)
        else:
            tally_pass += 1

    sample = write_fixture("nums.txt", b"10\n-2\n3\n")
    empty = write_fixture("empty.txt", b"")
    nope = write_fixture("nope.txt", b"1\nnope\n")
    total = compile_example("sum")
    bounds = compile_example("bounds")
    sum_rows = [
        ("sum sample", [str(sample)], 0, b"11\n", b""),
        ("sum empty", [str(empty)], 1, b"", b"empty file\n"),
        ("sum bad", [str(nope)], 1, b"", b"bad line 2: nope\n"),
        ("sum usage", [], 1, b"", b"usage: sum <file>\n"),
    ]
    bound_rows = [
        ("bounds sample", [str(sample)], 0, b"min -2\nmax 10\n", b""),
    ]
    for name, args, code, out, err in sum_rows:
        bad = check(name, run([str(total), *args]), code, out, err)
        if bad:
            failures.append(bad)
    for name, args, code, out, err in bound_rows:
        bad = check(name, run([str(bounds), *args]), code, out, err)
        if bad:
            failures.append(bad)

    if failures:
        print("\n".join(failures))
        raise SystemExit(1)

    hosts = {}
    probe_json = PROJECT / "results" / "probe-00.json"
    if probe_json.exists():
        for row in json.loads(probe_json.read_text(encoding="utf-8"))["hosts"]:
            hosts[row["name"]] = row

    def size(path: Path) -> int:
        return path.stat().st_size

    programs = {
        "tally": size(EXAMPLES / "tally.sensepin"),
        "sum": size(EXAMPLES / "sum.sensepin"),
        "bounds": size(EXAMPLES / "bounds.sensepin"),
        "double": size(EXAMPLES / "double.sensepin"),
    }
    payload = {
        "spec_sha256": hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(),
        "tally_cases": f"{tally_pass}/{len(tally_cases)}",
        "program_bytes": programs,
        "gauge_bytes": size(ROOT / "runtime.c"),
        "factory_bytes": size(ROOT / "foldc.py"),
        "binary_bytes": {
            "tally": size(BUILD / "tally.exe"),
            "sum": size(BUILD / "sum.exe"),
            "bounds": size(BUILD / "bounds.exe"),
            "double": size(BUILD / "double.exe"),
        },
        "probe00": {
            name: {
                "program_bytes": row["program_bytes"],
                "binary_bytes": row["binary_bytes"],
            }
            for name, row in hosts.items()
        },
    }
    lines = [
        "# Sensepin v0 score",
        "",
        f"Contract `{payload['spec_sha256'][:12]}`. Tally behavior {payload['tally_cases']} against probe 00. "
        "double, overflow, sum, and bounds matched their declared bytes.",
        "",
        "| Program | Residual bytes | Binary |",
        "| --- | ---: | ---: |",
    ]
    for name in ("tally", "sum", "bounds", "double"):
        lines.append(f"| {name} | {programs[name]} | {payload['binary_bytes'][name]} |")
    lines.extend(
        [
            "",
            f"Gauge runtime: {payload['gauge_bytes']} bytes. Compiler factory: {payload['factory_bytes']} bytes.",
            "",
            "Probe 00 host program text, same tally behavior:",
            "",
            "| Host | Program text | Binary |",
            "| --- | ---: | ---: |",
        ]
    )
    for name, row in payload["probe00"].items():
        binary = "shared interpreter" if row["binary_bytes"] is None else str(row["binary_bytes"])
        lines.append(f"| {name} | {row['program_bytes']} | {binary} |")
    lines.extend(
        [
            "",
            "The tally residual is the behavior file. The file, line, and integer gauges live in the runtime, once, and sum and bounds use that same runtime. Each binary still contains the runtime, because v0 does not share a library across programs. A smaller residual is not a smaller vessel.",
            "",
        ]
    )
    (PROJECT / "results" / "fold-v0.md").write_text("\n".join(lines), encoding="utf-8")
    (PROJECT / "results" / "fold-v0.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(PROJECT / "results" / "fold-v0.md")
    print(
        f"tally residual {programs['tally']} binary {payload['binary_bytes']['tally']} "
        f"gauge {payload['gauge_bytes']}"
    )


if __name__ == "__main__":
    main()
