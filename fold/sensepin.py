"""Sensepin desk. Run, build, or check one .sensepin file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def compiler() -> Path:
    exe = ROOT / "build" / "compiler.exe"
    if not exe.is_file():
        print("fold/build/compiler.exe is missing. Build it from fold/compiler.sensepin.", file=sys.stderr)
        raise SystemExit(1)
    return exe


def build(source: Path, exe: Path) -> int:
    exe.parent.mkdir(parents=True, exist_ok=True)
    if exe.is_file():
        exe.unlink()
    proc = subprocess.run([str(compiler()), str(source.resolve()), str(exe.resolve())])
    return proc.returncode


def check(source: Path) -> int:
    cache = ROOT / "build" / "desk"
    cache.mkdir(parents=True, exist_ok=True)
    return build(source, cache / f"{source.stem}-check.exe")


def run_program(source: Path, args: list[str]) -> int:
    cache = ROOT / "build" / "desk"
    cache.mkdir(parents=True, exist_ok=True)
    exe = cache / f"{source.stem}.exe"
    code = build(source, exe)
    if code != 0:
        return code
    proc = subprocess.run([str(exe), *args])
    return proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run, build, or check a Sensepin file.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Compile the file and run it.")
    run_parser.add_argument("source")
    run_parser.add_argument("args", nargs="*")

    build_parser = sub.add_parser("build", help="Compile the file and write an exe.")
    build_parser.add_argument("source")
    build_parser.add_argument("-o", required=True, dest="exe")

    check_parser = sub.add_parser("check", help="Report the first compile error.")
    check_parser.add_argument("source")

    parsed = parser.parse_args()
    source = Path(parsed.source)
    if parsed.command == "check":
        raise SystemExit(check(source))
    if parsed.command == "build":
        raise SystemExit(build(source, Path(parsed.exe)))
    raise SystemExit(run_program(source, parsed.args))


if __name__ == "__main__":
    main()
