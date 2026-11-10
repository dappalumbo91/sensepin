"""Score probe 01 against task.md. This file is the bench, not a host."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
WORK = PROJECT / "results" / "probe-01-work"
OUT_JSON = PROJECT / "results" / "probe-01.json"
OUT_MD = PROJECT / "results" / "probe-01.md"
PROBE00 = PROJECT / "results" / "probe-00.json"
MAX_BYTES = 1_048_576
I64_MIN = -9_223_372_036_854_775_808


def trunc_div(total: int, count: int) -> int:
    magnitude = abs(total) // count
    if total < 0:
        return -magnitude
    return magnitude


def success(count: int, total: int, low: int, high: int, name: bytes) -> dict:
    mean = trunc_div(total, count)
    text = f"count {count}\nmean {mean}\nmin {low}\nmax {high}\nname ".encode("ascii")
    return {"code": 0, "out": text + name + b"\n", "err": b""}


def bad_line(number: int, text: bytes) -> dict:
    return {
        "code": 1,
        "out": b"",
        "err": f"bad line {number}: ".encode("ascii") + text + b"\n",
    }


def fixed(message: str) -> dict:
    return {"code": 1, "out": b"", "err": (message + "\n").encode("ascii")}


def write_fixture(name: str, data: bytes) -> Path:
    path = WORK / name
    path.write_bytes(data)
    return path


def build_cases() -> list[dict]:
    ok = write_fixture("ok.txt", b"ada 10\nbea -2\ncy 4\n")
    no_nl = write_fixture("no-nl.txt", b"ada 10\nbea -2\ncy 4")
    tie = write_fixture("tie.txt", b"ada 5\nbea 5\n")
    later = write_fixture("later.txt", b"ada 1\nbea 9\n")
    toward = write_fixture("toward.txt", b"ada -1\nbea 0\n")
    crlf = write_fixture("crlf.txt", b"ada 10\r\nbea -2\r\n")
    bad = write_fixture("bad.txt", b"ada 10\nnope\n")
    blank = write_fixture("blank.txt", b"ada 1\n\nbea 2\n")
    spaces = write_fixture("spaces.txt", b"ada  1\n")
    under = write_fixture("under.txt", b"ada 1_0\n")
    hyphen = write_fixture("hyphen.txt", b"a-b 1\n")
    lead = write_fixture("lead.txt", b" ada 1\n")
    empty = write_fixture("empty.txt", b"")
    huge = write_fixture("huge.txt", b"0" * (MAX_BYTES + 1))
    overflow = write_fixture("overflow.txt", b"ada 9223372036854775807\nbea 1\n")
    lowest = write_fixture("min.txt", b"ada -9223372036854775808\n")
    half = write_fixture("half.txt", b"ada -9223372036854775808\nbea 0\n")
    past = write_fixture("past.txt", b"ada 9223372036854775808\n")
    plus = write_fixture("plus.txt", b"ada +07\nbea -0\n")
    rem = write_fixture("rem.txt", b"ada 1\nbea 1\ncy 1\n")
    named = write_fixture("named.txt", b"a_1 8\n")
    raw = write_fixture("raw.txt", b"ada 1\n\xff\n")
    missing = WORK / "missing.txt"
    if missing.exists():
        missing.unlink()

    rows = [
        ("ok", [ok], success(3, 12, -2, 10, b"ada")),
        ("no newline at end", [no_nl], success(3, 12, -2, 10, b"ada")),
        ("tie keeps the first name", [tie], success(2, 10, 5, 5, b"ada")),
        ("later max replaces the name", [later], success(2, 10, 1, 9, b"bea")),
        ("mean toward zero", [toward], success(2, -1, -1, 0, b"bea")),
        ("crlf", [crlf], success(2, 8, -2, 10, b"ada")),
        ("bad token", [bad], bad_line(2, b"nope")),
        ("blank line", [blank], bad_line(2, b"")),
        ("two spaces", [spaces], bad_line(1, b"ada  1")),
        ("underscore in the integer", [under], bad_line(1, b"ada 1_0")),
        ("hyphen in the name", [hyphen], bad_line(1, b"a-b 1")),
        ("leading space", [lead], bad_line(1, b" ada 1")),
        ("empty", [empty], fixed("empty file")),
        ("too large", [huge], fixed("file too large")),
        ("sum overflow", [overflow], bad_line(2, b"bea 1")),
        ("int64 min", [lowest], success(1, I64_MIN, I64_MIN, I64_MIN, b"ada")),
        ("int64 min mean", [half], success(2, I64_MIN, I64_MIN, 0, b"bea")),
        ("one past int64 max", [past], bad_line(1, b"ada 9223372036854775808")),
        ("sign and negative zero", [plus], success(2, 7, 0, 7, b"ada")),
        ("remainder dropped", [rem], success(3, 3, 1, 1, b"ada")),
        ("name alphabet", [named], success(1, 8, 8, 8, b"a_1")),
        ("raw bad line", [raw], bad_line(2, b"\xff")),
        ("missing", [missing], fixed(f"cannot open {missing}")),
        ("usage", [], fixed("usage: grades <file>")),
        ("two args", [ok, ok], fixed("usage: grades <file>")),
    ]
    return [{"name": name, "args": [str(path) for path in paths], "expect": expect} for name, paths, expect in rows]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True)


def tool_version(command: list[str]) -> str:
    proc = subprocess.run(command, capture_output=True)
    text = (proc.stdout or proc.stderr).decode("utf-8", errors="replace").strip()
    return text.splitlines()[0] if text else "unavailable"


def file_bytes(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists())


def show(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text) > 300:
        return text[:300] + "..."
    return text


def hosts() -> list[dict]:
    return [
        {
            "name": "Python",
            "program": [ROOT / "python" / "grades.py"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "python",
            "run": [sys.executable, str(ROOT / "python" / "grades.py")],
            "build": None,
            "binary": None,
            "version": tool_version([sys.executable, "--version"]),
        },
        {
            "name": "C",
            "program": [ROOT / "c" / "grades.c"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "c",
            "run": [str(ROOT / "c" / "grades.exe")],
            "build": ["clang", "-O2", "-o", str(ROOT / "c" / "grades.exe"), str(ROOT / "c" / "grades.c")],
            "binary": ROOT / "c" / "grades.exe",
            "version": tool_version(["clang", "--version"]),
        },
        {
            "name": "Rust",
            "program": [ROOT / "rust" / "src" / "main.rs"],
            "project": [ROOT / "rust" / "Cargo.toml"],
            "lock": [ROOT / "rust" / "Cargo.lock"],
            "cwd": ROOT / "rust",
            "run": [str(ROOT / "rust" / "target" / "release" / "grades.exe")],
            "build": ["cargo", "build", "--release", "--offline"],
            "binary": ROOT / "rust" / "target" / "release" / "grades.exe",
            "version": tool_version(["rustc", "--version"]),
        },
        {
            "name": "Zig",
            "program": [ROOT / "zig" / "src" / "main.zig"],
            "project": [ROOT / "zig" / "build.zig"],
            "lock": [],
            "cwd": ROOT / "zig",
            "run": [str(ROOT / "zig" / "zig-out" / "bin" / "grades.exe")],
            "build": ["zig", "build", "-Doptimize=ReleaseFast"],
            "binary": ROOT / "zig" / "zig-out" / "bin" / "grades.exe",
            "version": tool_version(["zig", "version"]),
        },
        {
            "name": "Go",
            "program": [ROOT / "go" / "grades.go"],
            "project": [ROOT / "go" / "go.mod"],
            "lock": [ROOT / "go" / "go.sum"],
            "cwd": ROOT / "go",
            "run": [str(ROOT / "go" / "grades.exe")],
            "build": ["go", "build", "-o", "grades.exe", "."],
            "binary": ROOT / "go" / "grades.exe",
            "version": tool_version(["go", "version"]),
        },
    ]


def score_host(host: dict, cases: list[dict]) -> dict:
    build_ok = True
    build_log = ""
    if host["build"] is not None:
        proc = run(host["build"], host["cwd"])
        build_ok = proc.returncode == 0
        build_log = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")[-2000:]
    case_rows = []
    if build_ok:
        for case in cases:
            proc = run(host["run"] + case["args"], host["cwd"])
            expect = case["expect"]
            ok = (
                proc.returncode == expect["code"]
                and proc.stdout == expect["out"]
                and proc.stderr == expect["err"]
            )
            case_rows.append(
                {
                    "name": case["name"],
                    "ok": ok,
                    "code": proc.returncode,
                    "stdout": show(proc.stdout),
                    "stderr": show(proc.stderr),
                }
            )
    binary = host["binary"]
    binary_bytes = binary.stat().st_size if binary is not None and binary.exists() else None
    passed = sum(1 for row in case_rows if row["ok"])
    return {
        "name": host["name"],
        "version": host["version"],
        "build_ok": build_ok,
        "build_log": build_log,
        "program_bytes": file_bytes(host["program"]),
        "project_bytes": file_bytes(host["project"]),
        "lock_bytes": file_bytes(host["lock"]),
        "binary_bytes": binary_bytes,
        "passed": passed,
        "cases": len(case_rows),
        "behavior_ok": build_ok and passed == len(cases),
        "failures": [row for row in case_rows if not row["ok"]],
    }


def earlier_program_bytes() -> dict[str, int]:
    if not PROBE00.exists():
        return {}
    payload = json.loads(PROBE00.read_text(encoding="utf-8"))
    return {row["name"]: row["program_bytes"] for row in payload["hosts"]}


def score_sensepin(cases: list[dict]) -> dict:
    source = PROJECT / "fold" / "examples" / "grades.sensepin"
    build = PROJECT / "fold" / "build"
    build.mkdir(parents=True, exist_ok=True)
    exe = build / "grades.exe"
    proc = run(
        [
            sys.executable,
            str(PROJECT / "fold" / "foldc.py"),
            str(source),
            "-o",
            str(build / "grades.c"),
            "--exe",
            str(exe),
        ],
        PROJECT,
    )
    row = {
        "program_bytes": source.stat().st_size if source.exists() else 0,
        "runtime_bytes": (PROJECT / "fold" / "runtime.c").stat().st_size,
        "binary_bytes": None,
        "build_ok": proc.returncode == 0,
        "build_log": (proc.stdout + proc.stderr).decode("utf-8", errors="replace")[-2000:],
        "passed": 0,
        "cases": 0,
        "behavior_ok": False,
        "failures": [],
    }
    if not row["build_ok"]:
        return row
    row["binary_bytes"] = exe.stat().st_size
    case_rows = []
    for case in cases:
        got = run([str(exe), *case["args"]], PROJECT)
        expect = case["expect"]
        ok = got.returncode == expect["code"] and got.stdout == expect["out"] and got.stderr == expect["err"]
        case_rows.append(
            {
                "name": case["name"],
                "ok": ok,
                "code": got.returncode,
                "stdout": show(got.stdout),
                "stderr": show(got.stderr),
            }
        )
    passed = sum(1 for item in case_rows if item["ok"])
    row["passed"] = passed
    row["cases"] = len(case_rows)
    row["behavior_ok"] = passed == len(case_rows)
    row["failures"] = [item for item in case_rows if not item["ok"]]
    return row


def write_report(payload: dict) -> None:
    lines = [
        "# Probe 01 score",
        "",
        f"Contract `{payload['contract_sha256'][:12]}`. {payload['cases']} cases. Flags are the ones named in METHOD.md.",
        "",
        "| Host | Version | Behavior | Program text | Delta vs tally | Project text | Lockfile | Binary |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    earlier = earlier_program_bytes()
    for row in payload["hosts"]:
        behavior = f"{row['passed']}/{row['cases']}" if row["build_ok"] else "build failed"
        binary = "shared interpreter" if row["binary_bytes"] is None and row["name"] == "Python" else (
            str(row["binary_bytes"]) if row["binary_bytes"] is not None else "absent"
        )
        if row["name"] in earlier:
            delta = f"{row['program_bytes'] - earlier[row['name']]:+d}"
        else:
            delta = ""
        lines.append(
            f"| {row['name']} | {row['version']} | {behavior} | {row['program_bytes']} | {delta} | {row['project_bytes']} | {row['lock_bytes']} | {binary} |"
        )
    lines.extend(["", "## Failures", ""])
    any_failure = False
    for row in payload["hosts"]:
        if not row["build_ok"]:
            any_failure = True
            lines.append(f"### {row['name']} build")
            lines.append("")
            lines.append("```text")
            lines.append(row["build_log"].strip() or "no compiler output")
            lines.append("```")
            lines.append("")
        for failure in row["failures"]:
            any_failure = True
            lines.append(
                f"- {row['name']} `{failure['name']}` exited {failure['code']}. stdout `{failure['stdout']!r}` stderr `{failure['stderr']!r}`."
            )
    if not any_failure:
        lines.append("Every host matched the contract.")
    lines.extend(
        [
            "",
            "## What this score can say",
            "",
            "The delta column is grades program text minus the probe 00 tally program text for the same host. That is the cost of the name, of the integer as its own field, of the toward-zero mean, and of keeping the first name that holds the max.",
            "",
            "File, line split, the integer rule, and the bad-line message are the ceremony probe 00 already paid for. They show up again here. The delta is what the new fields add on top of that copy.",
            "",
            "Sensepin's first pass at this contract had no residual. v0 could not cut a line, and it could not divide. The rebuild adds gauge `bytes` (`len`, `before`, `after`, `holds`, and a byte walk) and checked `/` on gauge `i64`. The host table above is the same contract.",
            "",
        ]
    )
    sense = payload["sensepin"]
    if sense["behavior_ok"]:
        lines.extend(
            [
                f"Sensepin residual {sense['program_bytes']} bytes, binary {sense['binary_bytes']}, "
                f"runtime {sense['runtime_bytes']} bytes, behavior {sense['passed']}/{sense['cases']}.",
                "",
            ]
        )
    else:
        lines.append("Sensepin did not rebuild the contract.")
        lines.append("")
        if not sense["build_ok"]:
            lines.extend(["```text", sense["build_log"].strip() or "no compiler output", "```", ""])
        for failure in sense["failures"]:
            lines.append(
                f"- Sensepin `{failure['name']}` exited {failure['code']}. stdout `{failure['stdout']!r}` stderr `{failure['stderr']!r}`."
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    stored = {
        "probe": payload["probe"],
        "contract_sha256": payload["contract_sha256"],
        "cases": payload["cases"],
        "hosts": [
            {key: row[key] for key in row if key != "build_log"}
            | {"build_log": row["build_log"] if not row["behavior_ok"] else ""}
            for row in payload["hosts"]
        ],
        "sensepin": {
            key: payload["sensepin"][key]
            for key in payload["sensepin"]
            if key != "build_log" or not payload["sensepin"]["behavior_ok"]
        },
    }
    OUT_JSON.write_text(json.dumps(stored, indent=2), encoding="utf-8")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    contract = (ROOT / "task.md").read_bytes()
    cases = build_cases()
    sensepin = score_sensepin(cases)
    payload = {
        "probe": "01-grades",
        "contract_sha256": hashlib.sha256(contract).hexdigest(),
        "cases": len(cases),
        "hosts": [score_host(host, cases) for host in hosts()],
        "sensepin": sensepin,
    }
    write_report(payload)
    print(OUT_MD)
    for row in payload["hosts"]:
        status = "pass" if row["behavior_ok"] else "fail"
        print(
            f"{row['name']}: {status} behavior {row['passed']}/{row['cases']} "
            f"program {row['program_bytes']} project {row['project_bytes']} "
            f"binary {row['binary_bytes']}"
        )
    status = "pass" if sensepin["behavior_ok"] else "fail"
    print(
        f"Sensepin: {status} behavior {sensepin['passed']}/{sensepin['cases']} "
        f"residual {sensepin['program_bytes']} binary {sensepin['binary_bytes']}"
    )
    if not all(row["behavior_ok"] for row in payload["hosts"]) or not sensepin["behavior_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
