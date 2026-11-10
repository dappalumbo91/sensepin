"""Score probe 00 against task.md. This file is the bench, not a host."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
WORK = PROJECT / "results" / "probe-00-work"
OUT_JSON = PROJECT / "results" / "probe-00.json"
OUT_MD = PROJECT / "results" / "probe-00.md"
MAX_BYTES = 1_048_576


def success(count: int, total: int, low: int, high: int) -> dict:
    text = f"count {count}\nsum {total}\nmin {low}\nmax {high}\n"
    return {"code": 0, "out": text.encode("ascii"), "err": b""}


def bad_line(number: int, text: str) -> dict:
    return {
        "code": 1,
        "out": b"",
        "err": f"bad line {number}: {text}\n".encode("ascii"),
    }


def fixed(message: str) -> dict:
    return {"code": 1, "out": b"", "err": (message + "\n").encode("ascii")}


def write_fixture(name: str, data: bytes) -> Path:
    path = WORK / name
    path.write_bytes(data)
    return path


def build_cases() -> list[dict]:
    ok = write_fixture("ok.txt", b"10\n-2\n3\n")
    no_nl = write_fixture("no-nl.txt", b"10\n-2\n3")
    plus = write_fixture("plus.txt", b"+7\n-0\n")
    crlf = write_fixture("crlf.txt", b"10\r\n-2\r\n")
    bad = write_fixture("bad.txt", b"10\nnope\n")
    blank = write_fixture("blank.txt", b"1\n\n2\n")
    under = write_fixture("under.txt", b"1_0\n")
    space = write_fixture("space.txt", b" 1\n")
    empty = write_fixture("empty.txt", b"")
    huge = write_fixture("huge.txt", b"0" * (MAX_BYTES + 1))
    overflow = write_fixture("overflow.txt", b"9223372036854775807\n1\n")
    lowest = write_fixture("min.txt", b"-9223372036854775808\n")
    past = write_fixture("past.txt", b"9223372036854775808\n")
    missing = WORK / "missing.txt"
    if missing.exists():
        missing.unlink()

    rows = [
        ("ok", [ok], success(3, 11, -2, 10)),
        ("no newline at end", [no_nl], success(3, 11, -2, 10)),
        ("sign and negative zero", [plus], success(2, 7, 0, 7)),
        ("crlf", [crlf], success(2, 8, -2, 10)),
        ("bad token", [bad], bad_line(2, "nope")),
        ("blank line", [blank], bad_line(2, "")),
        ("underscore", [under], bad_line(1, "1_0")),
        ("leading space", [space], bad_line(1, " 1")),
        ("empty", [empty], fixed("empty file")),
        ("too large", [huge], fixed("file too large")),
        ("sum overflow", [overflow], bad_line(2, "1")),
        (
            "int64 min",
            [lowest],
            success(1, -9223372036854775808, -9223372036854775808, -9223372036854775808),
        ),
        ("one past int64 max", [past], bad_line(1, "9223372036854775808")),
        ("missing", [missing], fixed(f"cannot open {missing}")),
        ("usage", [], fixed("usage: tally <file>")),
        ("two args", [ok, ok], fixed("usage: tally <file>")),
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
            "program": [ROOT / "python" / "tally.py"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "python",
            "run": [sys.executable, str(ROOT / "python" / "tally.py")],
            "build": None,
            "binary": None,
            "version": tool_version([sys.executable, "--version"]),
        },
        {
            "name": "C",
            "program": [ROOT / "c" / "tally.c"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "c",
            "run": [str(ROOT / "c" / "tally.exe")],
            "build": ["clang", "-O2", "-o", str(ROOT / "c" / "tally.exe"), str(ROOT / "c" / "tally.c")],
            "binary": ROOT / "c" / "tally.exe",
            "version": tool_version(["clang", "--version"]),
        },
        {
            "name": "Rust",
            "program": [ROOT / "rust" / "src" / "main.rs"],
            "project": [ROOT / "rust" / "Cargo.toml"],
            "lock": [ROOT / "rust" / "Cargo.lock"],
            "cwd": ROOT / "rust",
            "run": [str(ROOT / "rust" / "target" / "release" / "tally.exe")],
            "build": ["cargo", "build", "--release", "--offline"],
            "binary": ROOT / "rust" / "target" / "release" / "tally.exe",
            "version": tool_version(["rustc", "--version"]),
        },
        {
            "name": "Zig",
            "program": [ROOT / "zig" / "src" / "main.zig"],
            "project": [ROOT / "zig" / "build.zig"],
            "lock": [],
            "cwd": ROOT / "zig",
            "run": [str(ROOT / "zig" / "zig-out" / "bin" / "tally.exe")],
            "build": ["zig", "build", "-Doptimize=ReleaseFast"],
            "binary": ROOT / "zig" / "zig-out" / "bin" / "tally.exe",
            "version": tool_version(["zig", "version"]),
        },
        {
            "name": "Go",
            "program": [ROOT / "go" / "tally.go"],
            "project": [ROOT / "go" / "go.mod"],
            "lock": [ROOT / "go" / "go.sum"],
            "cwd": ROOT / "go",
            "run": [str(ROOT / "go" / "tally.exe")],
            "build": ["go", "build", "-o", "tally.exe", "."],
            "binary": ROOT / "go" / "tally.exe",
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


def write_report(payload: dict) -> None:
    lines = [
        "# Probe 00 score",
        "",
        f"Contract `{payload['contract_sha256'][:12]}`. {payload['cases']} cases. Flags are the ones named in METHOD.md.",
        "",
        "| Host | Version | Behavior | Program text | Project text | Lockfile | Binary |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["hosts"]:
        behavior = f"{row['passed']}/{row['cases']}" if row["build_ok"] else "build failed"
        binary = "shared interpreter" if row["binary_bytes"] is None and row["name"] == "Python" else (
            str(row["binary_bytes"]) if row["binary_bytes"] is not None else "absent"
        )
        lines.append(
            f"| {row['name']} | {row['version']} | {behavior} | {row['program_bytes']} | {row['project_bytes']} | {row['lock_bytes']} | {binary} |"
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
            "Program text is the behavior file. Project text is the manifest. The binary is the release vessel. Python's interpreter stays off this table because the contract named it as a shared vessel.",
            "",
            "This probe is one behavior, written once. It can show the ceremony floor. It cannot show repeated sense. Probe 01 is still unwritten.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    contract = (ROOT / "task.md").read_bytes()
    cases = build_cases()
    payload = {
        "probe": "00-tally",
        "contract_sha256": hashlib.sha256(contract).hexdigest(),
        "cases": len(cases),
        "hosts": [score_host(host, cases) for host in hosts()],
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
    if not all(row["behavior_ok"] for row in payload["hosts"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
