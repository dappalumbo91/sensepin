"""Score Sensepin. The behavior bar for tally is probe 00. The vessel is the exe plus the shared library."""

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

    compile_example("grades")

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
        "grades": size(EXAMPLES / "grades.sensepin"),
    }
    exe_bytes = {
        "tally": size(BUILD / "tally.exe"),
        "sum": size(BUILD / "sum.exe"),
        "bounds": size(BUILD / "bounds.exe"),
        "double": size(BUILD / "double.exe"),
        "grades": size(BUILD / "grades.exe"),
    }
    library = size(BUILD / "sensepin.dll")
    surface_tally = 178688
    surface_grades = 179712
    surface_two = surface_tally + surface_grades
    one_tally = exe_bytes["tally"] + library
    one_grades = exe_bytes["grades"] + library
    two = exe_bytes["tally"] + exe_bytes["grades"] + library
    payload = {
        "spec_sha256": hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(),
        "tally_cases": f"{tally_pass}/{len(tally_cases)}",
        "program_bytes": programs,
        "gauge_bytes": size(ROOT / "runtime.c"),
        "header_bytes": size(ROOT / "runtime.h"),
        "factory_bytes": size(ROOT / "foldc.py"),
        "binary_bytes": exe_bytes,
        "library_bytes": library,
        "shipped_one": {"tally": one_tally, "grades": one_grades},
        "shipped_two": two,
        "surface_embedded": {
            "contract": "d100dcf839db",
            "tally": surface_tally,
            "grades": surface_grades,
            "two": surface_two,
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
        "# Sensepin score after gauge map",
        "",
        f"Contract `{payload['spec_sha256'][:12]}`. Tally behavior {payload['tally_cases']} against probe 00. "
        "double, overflow, sum, and bounds matched their declared bytes.",
        "",
        "| Program | Residual bytes | Exe |",
        "| --- | ---: | ---: |",
    ]
    for name in ("tally", "sum", "bounds", "double", "grades"):
        lines.append(f"| {name} | {programs[name]} | {exe_bytes[name]} |")
    lines.extend(
        [
            "",
            f"Shared library `sensepin.dll`: {library} bytes. Built with `clang -O2 -shared` and no strip flag.",
            "",
            "| Mass | Bytes |",
            "| --- | ---: |",
            f"| tally exe + library | {one_tally} |",
            f"| grades exe + library | {one_grades} |",
            f"| tally exe + grades exe + library | {two} |",
            f"| surface tally binary | {surface_tally} |",
            f"| surface grades binary | {surface_grades} |",
            f"| surface tally + grades | {surface_two} |",
            "",
            f"One shipped tally is the exe plus the library, {one_tally} bytes. "
            f"One shipped grades is the exe plus the library, {one_grades} bytes. "
            f"Two shipped programs are the two exes plus the library once, {two} bytes.",
            "",
            f"The surface row, contract `d100dcf839db`, embedded the runtime in each binary: "
            f"tally {surface_tally}, grades {surface_grades}, together {surface_two}.",
            "",
        ]
    )
    if two < surface_two:
        lines.append(f"The two-program vessel is smaller by {surface_two - two} bytes.")
    else:
        lines.append(
            f"The two-program vessel is {two} bytes, larger than the surface pair {surface_two} by {two - surface_two} bytes."
        )
    one_delta = one_tally - surface_tally
    if one_delta > 0:
        one_line = (
            f"One shipped tally is {one_tally} bytes, larger than the surface tally binary {surface_tally} by {one_delta} bytes. "
            "The library holds every gauge."
        )
    elif one_delta < 0:
        one_line = (
            f"One shipped tally is {one_tally} bytes, smaller than the surface tally binary {surface_tally} by {-one_delta} bytes."
        )
    else:
        one_line = f"One shipped tally is {one_tally} bytes, the same mass as the surface tally binary."
    lines.append(one_line)
    lines.extend(
        [
            "",
            f"Gauge runtime source: `runtime.c` {payload['gauge_bytes']} bytes, "
            f"`runtime.h` {payload['header_bytes']} bytes. Compiler factory: {payload['factory_bytes']} bytes.",
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
            "The tally residual is the behavior file. The gauge runtime is one shared library, paid once. "
            "An exe holds that program's residual. One shipped program is the exe plus the library. "
            "Gauge `map` is in this contract. A byte index other than `for` over bytes stays out. "
            "The desk command, the Windows installer, and editor diagnostics are in this tree. "
            "Probe 02 shelf is results/probe-02.md, contract 40947a4db99c. "
            "The earlier rows are results/fold-v0.md, contract 281b6f432322, "
            "results/sensepin-rebuild.md, contract 2d4aebf83dec, "
            "results/sensepin-surface.md, contract d100dcf839db, "
            "results/sensepin-shared.md, contract c6ecd694d103, and "
            "results/sensepin-desk.md, contract 803bc794ee66. "
            "Grades behavior is scored by probes/01-grades/measure.py. This row records the grades exe from the same link.",
            "",
        ]
    )
    (PROJECT / "results" / "sensepin-map.md").write_text("\n".join(lines), encoding="utf-8")
    (PROJECT / "results" / "sensepin-map.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(PROJECT / "results" / "sensepin-map.md")
    print(
        f"tally residual {programs['tally']} exe {exe_bytes['tally']} "
        f"library {library} one {one_tally} two {two} "
        f"grades exe {exe_bytes['grades']} gauge {payload['gauge_bytes']}"
    )


if __name__ == "__main__":
    main()
