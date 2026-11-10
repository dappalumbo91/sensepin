"""Score probe 02 against task.md. This file is the bench, not a host."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
WORK = PROJECT / "results" / "probe-02-work"
OUT_JSON = PROJECT / "results" / "probe-02.json"
OUT_MD = PROJECT / "results" / "probe-02.md"
PROBE01 = PROJECT / "results" / "probe-01.json"
MAX_BYTES = 1_048_576
I64_MIN = -9_223_372_036_854_775_808
I64_MAX = 9_223_372_036_854_775_807


def mul_i64(left: int, right: int) -> int | None:
    if left == 0 or right == 0:
        return 0
    if left == I64_MIN:
        return left if right == 1 else None
    if right == I64_MIN:
        return right if left == 1 else None
    if abs(left) > I64_MAX // abs(right):
        return None
    return left * right


def add_i64(total: int, value: int) -> int | None:
    if value > 0 and total > I64_MAX - value:
        return None
    if value < 0 and total < I64_MIN - value:
        return None
    return total + value


def parse_i64(text: bytes) -> int | None:
    if text in (b"", b"+", b"-"):
        return None
    body = text[1:] if text[:1] in (b"+", b"-") else text
    if body == b"" or any(byte < 48 or byte > 57 for byte in body):
        return None
    value = int(text.decode("ascii"), 10)
    if value < I64_MIN or value > I64_MAX:
        return None
    return value


def name_ok(name: bytes) -> bool:
    if name == b"":
        return False
    for byte in name:
        if byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122:
            continue
        return False
    return True


def bad_line(number: int, text: bytes) -> dict:
    return {
        "code": 1,
        "out": b"",
        "err": f"bad line {number}: ".encode("ascii") + text + b"\n",
    }


def fixed(message: str) -> dict:
    return {"code": 1, "out": b"", "err": (message + "\n").encode("ascii")}


def evaluate(data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        return fixed("file too large")
    if len(data) == 0:
        return fixed("empty file")
    count = 0
    pieces = 0
    worth = 0
    high = 0
    item = b""
    seen = False
    line_no = 1
    start = 0
    while start < len(data):
        end = data.find(b"\n", start)
        if end == -1:
            raw = data[start:]
            start = len(data)
            newline = False
        else:
            raw = data[start:end]
            start = end + 1
            newline = True
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        spaces = [index for index, byte in enumerate(raw) if byte == 32]
        parsed = None
        if len(spaces) == 2 and spaces[0] != 0 and spaces[1] != spaces[0] + 1 and spaces[1] != len(raw) - 1:
            name = raw[: spaces[0]]
            qty = parse_i64(raw[spaces[0] + 1 : spaces[1]])
            price = parse_i64(raw[spaces[1] + 1 :])
            if name_ok(name) and qty is not None and price is not None:
                parsed = (name, qty, price)
        if parsed is None:
            return bad_line(line_no, raw)
        name, qty, price = parsed
        line_value = mul_i64(qty, price)
        next_pieces = None if line_value is None else add_i64(pieces, qty)
        next_worth = None if next_pieces is None or line_value is None else add_i64(worth, line_value)
        if line_value is None or next_pieces is None or next_worth is None:
            return bad_line(line_no, raw)
        pieces = next_pieces
        worth = next_worth
        if not seen or line_value > high:
            high = line_value
            item = name
            seen = True
        count += 1
        if newline:
            line_no += 1
            if start == len(data):
                break
    text = f"count {count}\npieces {pieces}\nvalue {worth}\nitem ".encode("ascii")
    return {"code": 0, "out": text + item + b"\n", "err": b""}


def write_fixture(name: str, data: bytes) -> Path:
    path = WORK / name
    path.write_bytes(data)
    return path


def build_cases() -> list[dict]:
    half = 4_611_686_018_427_387_903
    rows = [
        ("ok", b"ada 2 5\nbea 1 20\ncy 4 1\n"),
        ("no newline at end", b"ada 2 5\nbea 1 20\ncy 4 1"),
        ("tie keeps the first item", b"ada 2 5\nbea 1 10\n"),
        ("later max replaces the item", b"ada 1 1\nbea 3 4\n"),
        ("return", b"ada -2 5\n"),
        ("negative price", b"ada 3 -4\n"),
        ("two negatives", b"ada -3 -4\n"),
        ("crlf", b"ada 2 5\r\nbea 1 20\r\n"),
        ("two fields", b"ada 10\n"),
        ("blank line", b"ada 1 1\n\nbea 2 2\n"),
        ("extra field", b"ada 1 2 3\n"),
        ("empty quantity", b"ada  5\n"),
        ("underscore in the integer", b"ada 1_0 2\n"),
        ("hyphen in the name", b"a-b 1 2\n"),
        ("leading space", b" ada 1 2\n"),
        ("empty", b""),
        ("too large", b"0" * (MAX_BYTES + 1)),
        ("pieces overflow", b"ada 9223372036854775807 1\nbea 1 1\n"),
        ("value overflow", f"ada 2 {half}\nbea 2 {half}\n".encode("ascii")),
        ("multiply overflow", b"ada 9223372036854775807 2\n"),
        ("minimum times negative one", b"ada -9223372036854775808 -1\n"),
        ("minimum times one", b"ada -9223372036854775808 1\n"),
        ("zero times minimum", b"ada 0 -9223372036854775808\n"),
        ("sign and negative zero", b"ada +07 -0\n"),
        ("name alphabet", b"a_1 2 3\n"),
        ("raw bad line", b"ada 1 1\n\xff\n"),
        ("zero price", b"ada 4 0\nbea 1 1\n"),
    ]
    cases = []
    for index, (name, data) in enumerate(rows):
        path = write_fixture(f"{index:02d}.txt", data)
        cases.append({"name": name, "args": [str(path)], "expect": evaluate(data)})
    missing = WORK / "missing.txt"
    if missing.exists():
        missing.unlink()
    cases.append({"name": "missing", "args": [str(missing)], "expect": fixed(f"cannot open {missing}")})
    cases.append({"name": "usage", "args": [], "expect": fixed("usage: shelf <file>")})
    ok = cases[0]["args"][0]
    cases.append({"name": "two args", "args": [ok, ok], "expect": fixed("usage: shelf <file>")})
    return cases


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
            "program": [ROOT / "python" / "shelf.py"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "python",
            "run": [sys.executable, str(ROOT / "python" / "shelf.py")],
            "build": None,
            "binary": None,
            "version": tool_version([sys.executable, "--version"]),
        },
        {
            "name": "C",
            "program": [ROOT / "c" / "shelf.c"],
            "project": [],
            "lock": [],
            "cwd": ROOT / "c",
            "run": [str(ROOT / "c" / "shelf.exe")],
            "build": ["clang", "-O2", "-o", str(ROOT / "c" / "shelf.exe"), str(ROOT / "c" / "shelf.c")],
            "binary": ROOT / "c" / "shelf.exe",
            "version": tool_version(["clang", "--version"]),
        },
        {
            "name": "Rust",
            "program": [ROOT / "rust" / "src" / "main.rs"],
            "project": [ROOT / "rust" / "Cargo.toml"],
            "lock": [ROOT / "rust" / "Cargo.lock"],
            "cwd": ROOT / "rust",
            "run": [str(ROOT / "rust" / "target" / "release" / "shelf.exe")],
            "build": ["cargo", "build", "--release", "--offline"],
            "binary": ROOT / "rust" / "target" / "release" / "shelf.exe",
            "version": tool_version(["rustc", "--version"]),
        },
        {
            "name": "Zig",
            "program": [ROOT / "zig" / "src" / "main.zig"],
            "project": [ROOT / "zig" / "build.zig"],
            "lock": [],
            "cwd": ROOT / "zig",
            "run": [str(ROOT / "zig" / "zig-out" / "bin" / "shelf.exe")],
            "build": ["zig", "build", "-Doptimize=ReleaseFast"],
            "binary": ROOT / "zig" / "zig-out" / "bin" / "shelf.exe",
            "version": tool_version(["zig", "version"]),
        },
        {
            "name": "Go",
            "program": [ROOT / "go" / "shelf.go"],
            "project": [ROOT / "go" / "go.mod"],
            "lock": [ROOT / "go" / "go.sum"],
            "cwd": ROOT / "go",
            "run": [str(ROOT / "go" / "shelf.exe")],
            "build": ["go", "build", "-o", "shelf.exe", "."],
            "binary": ROOT / "go" / "shelf.exe",
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
    if not PROBE01.exists():
        return {}
    payload = json.loads(PROBE01.read_text(encoding="utf-8"))
    rows = {row["name"]: row["program_bytes"] for row in payload["hosts"]}
    sense = payload.get("sensepin", {})
    if "program_bytes" in sense:
        rows["Sensepin"] = sense["program_bytes"]
    return rows


def score_sensepin(cases: list[dict]) -> dict:
    source = PROJECT / "fold" / "examples" / "shelf.sensepin"
    build = PROJECT / "fold" / "build"
    build.mkdir(parents=True, exist_ok=True)
    exe = build / "shelf.exe"
    proc = run(
        [
            sys.executable,
            str(PROJECT / "fold" / "foldc.py"),
            str(source),
            "-o",
            str(build / "shelf.c"),
            "--exe",
            str(exe),
        ],
        PROJECT,
    )
    row = {
        "program_bytes": source.stat().st_size if source.exists() else 0,
        "runtime_bytes": (PROJECT / "fold" / "runtime.c").stat().st_size,
        "binary_bytes": None,
        "library_bytes": None,
        "shipped_bytes": None,
        "build_ok": proc.returncode == 0,
        "build_log": (proc.stdout + proc.stderr).decode("utf-8", errors="replace")[-2000:],
        "passed": 0,
        "cases": 0,
        "behavior_ok": False,
        "failures": [],
    }
    if not row["build_ok"]:
        return row
    library = build / "sensepin.dll"
    row["binary_bytes"] = exe.stat().st_size
    row["library_bytes"] = library.stat().st_size if library.exists() else None
    if row["library_bytes"] is not None:
        row["shipped_bytes"] = row["binary_bytes"] + row["library_bytes"]
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


def live_size(path: Path) -> int | None:
    return path.stat().st_size if path.exists() else None


def write_report(payload: dict) -> None:
    lines = [
        "# Probe 02 score",
        "",
        f"Contract `{payload['contract_sha256'][:12]}`. {payload['cases']} cases. Flags are the ones named in METHOD.md.",
        "",
        "| Host | Version | Behavior | Program text | Delta vs grades | Project text | Lockfile | Binary |",
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
    for row in payload["hosts"] + [payload["sensepin"] | {"name": "Sensepin"}]:
        if row.get("name") == "Sensepin":
            continue
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
    sense = payload["sensepin"]
    if not sense["behavior_ok"]:
        any_failure = True
    if not any_failure:
        lines.append("Every host matched the contract.")
    fold_build = PROJECT / "fold" / "build"
    tally_exe = live_size(fold_build / "tally.exe")
    grades_exe = live_size(fold_build / "grades.exe")
    library = sense.get("library_bytes")
    shelf_exe = sense.get("binary_bytes")
    three = None
    if None not in (tally_exe, grades_exe, shelf_exe, library):
        three = tally_exe + grades_exe + shelf_exe + library
    lines.extend(
        [
            "",
            "## What this score can say",
            "",
            "The delta column is shelf program text minus the probe 01 grades program text for the same host. That is the cost of the third field and of the checked product of quantity and price.",
            "",
            "File, line split, the integer rule, the name alphabet, and the bad-line message are the ceremony the earlier probes already paid for. They show up again here.",
            "",
        ]
    )
    if sense["behavior_ok"]:
        lines.append(
            f"Sensepin residual {sense['program_bytes']} bytes, exe {sense['binary_bytes']}, "
            f"shared library {sense['library_bytes']}, one shipped program {sense['shipped_bytes']}, "
            f"runtime {sense['runtime_bytes']} bytes, behavior {sense['passed']}/{sense['cases']}. "
            "The language gained no new word for this contract."
        )
        if "Sensepin" in earlier:
            lines.append(
                f"The residual is {sense['program_bytes'] - earlier['Sensepin']:+d} bytes beside the grades residual {earlier['Sensepin']}."
            )
        if three is not None:
            lines.append(
                f"Three shipped programs are tally exe {tally_exe}, grades exe {grades_exe}, shelf exe {shelf_exe}, "
                f"and the library once, together {three}."
            )
        host_by_name = {row["name"]: row for row in payload["hosts"]}
        for host_name in ("C", "Rust"):
            host = host_by_name.get(host_name)
            if host and host["binary_bytes"] is not None and sense["shipped_bytes"] is not None and shelf_exe is not None:
                lines.append(
                    f"The shelf exe is {shelf_exe} bytes. One shipped shelf is {sense['shipped_bytes']} bytes. "
                    f"The {host_name} binary is {host['binary_bytes']} bytes."
                )
        lines.append("")
    else:
        lines.append("Sensepin missed the contract with the language as it stands.")
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
            key: sense[key]
            for key in sense
            if key != "build_log" or not sense["behavior_ok"]
        },
        "three_program_bytes": three,
    }
    OUT_JSON.write_text(json.dumps(stored, indent=2), encoding="utf-8")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    contract = (ROOT / "task.md").read_bytes()
    cases = build_cases()
    sensepin = score_sensepin(cases)
    payload = {
        "probe": "02-shelf",
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
        f"residual {sensepin['program_bytes']} exe {sensepin['binary_bytes']} "
        f"library {sensepin.get('library_bytes')} shipped {sensepin.get('shipped_bytes')}"
    )
    if not all(row["behavior_ok"] for row in payload["hosts"]) or not sensepin["behavior_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
