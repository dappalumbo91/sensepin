"""Hole pass for Sensepin. The contract is SPEC.md."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import foldc

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build" / "stress"
CLANG = ["clang", "-O2", "-Wall", "-Wextra", "-Werror"]


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, bytes) else b""
        err = exc.stderr if isinstance(exc.stderr, bytes) else b"timeout"
        return subprocess.CompletedProcess(cmd, 124, out, err or b"timeout")


def clang_exe(c_path: Path, exe: Path) -> subprocess.CompletedProcess[bytes]:
    return run([*CLANG, "-o", str(exe), "--", str(c_path)])


def compile_fold(name: str, source: str) -> tuple[Path, Path]:
    fold_path = BUILD / f"{name}.sensepin"
    c_path = BUILD / f"{name}.c"
    exe = BUILD / f"{name}.exe"
    fold_path.write_text(source, encoding="utf-8")
    try:
        c_path.write_text(foldc.compile_text(source), encoding="utf-8")
    except foldc.FoldError as exc:
        raise SystemExit(f"{name} failed to compile: {exc}") from exc
    built = clang_exe(c_path, exe)
    if built.returncode != 0:
        sys.stderr.buffer.write(built.stderr)
        raise SystemExit(f"{name} failed to clang")
    return c_path, exe


def expect_error(label: str, source: str, needle: str, failures: list[str]) -> None:
    try:
        foldc.compile_text(source)
    except foldc.FoldError as exc:
        if needle not in str(exc):
            failures.append(f"{label}: {exc} does not mention {needle}")
        return
    failures.append(f"{label}: compiled")


def check(
    label: str,
    proc: subprocess.CompletedProcess[bytes],
    code: int,
    out: bytes,
    err: bytes,
    failures: list[str],
) -> None:
    if proc.returncode != code or proc.stdout != out or proc.stderr != err:
        failures.append(
            f"{label} exited {proc.returncode} expected {code}\n"
            f"stdout {proc.stdout!r} expected {out!r}\n"
            f"stderr {proc.stderr!r} expected {err!r}"
        )


def make_sparse(path: Path, size: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel.DeviceIoControl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.SetFilePointerEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    ]
    kernel.SetFilePointerEx.restype = wintypes.BOOL
    kernel.SetEndOfFile.argtypes = [ctypes.c_void_p]
    kernel.SetEndOfFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x40000000, 0, None, 2, 0x80, None)
    invalid = ctypes.c_void_p(-1).value
    if not handle or handle == invalid:
        raise OSError(ctypes.get_last_error(), "CreateFileW")
    try:
        returned = wintypes.DWORD(0)
        if not kernel.DeviceIoControl(handle, 0x000900C4, None, 0, None, 0, ctypes.byref(returned), None):
            raise OSError(ctypes.get_last_error(), "FSCTL_SET_SPARSE")
        pos = ctypes.c_longlong(size)
        newpos = ctypes.c_longlong(0)
        if not kernel.SetFilePointerEx(handle, pos, ctypes.byref(newpos), 0):
            raise OSError(ctypes.get_last_error(), "SetFilePointerEx")
        if not kernel.SetEndOfFile(handle):
            raise OSError(ctypes.get_last_error(), "SetEndOfFile")
    finally:
        kernel.CloseHandle(handle)


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    base = "phase console\ngauge i64\nfn main\n"

    expect_error("unicode ident", base + "  let nπ = 1\nend\n", "unexpected", failures)
    expect_error("long ident", base + f"  let {'a' * 65} = 1\nend\n", "too long", failures)
    expect_error("chained compare", base + "  write 1 < 2 < 3\nend\n", "unexpected", failures)
    expect_error("bare reason", base + "  write reason\nend\n", "reason", failures)
    expect_error(
        "lines call",
        "phase console\ngauge lines\nfn main\n  let t = lines(\"a\")\nend\n",
        "lines()",
        failures,
    )
    expect_error(
        "render without i64 gauge",
        "phase console\ngauge args\nfn main\n  write argc()\nend\n",
        "gauge i64",
        failures,
    )
    try:
        foldc.compile_text("phase console\nfn id(n: i64) -> i64\n  return n\nend\nfn main\nend\n")
    except foldc.FoldError as exc:
        failures.append(f"a typed function with no arithmetic was rejected: {exc}")
    try:
        foldc.compile_text(base + f"  let {'b' * 64} = 1\n  write {'b' * 64}\nend\n")
    except foldc.FoldError as exc:
        failures.append(f"64-character identifier was rejected: {exc}")
    try:
        foldc.compile_text(base + "  write " + ("(" * 4000) + "1" + (")" * 4000) + "\nend\n")
    except foldc.FoldError as exc:
        if "too deep" not in str(exc):
            failures.append(f"deep source: {exc}")
    else:
        failures.append("deep source compiled")
    try:
        foldc.compile_text("a" * (foldc.SOURCE_LIMIT + 1))
    except foldc.FoldError as exc:
        if "too large" not in str(exc):
            failures.append(f"large source: {exc}")
    else:
        failures.append("large source compiled")

    bad_path = BUILD / "bad.sensepin"
    bad_path.write_bytes(b"\xff\xfe")
    bad = run([sys.executable, str(ROOT / "foldc.py"), str(bad_path), "-o", str(BUILD / "bad.c")])
    if bad.returncode == 0 or b"utf-8" not in bad.stderr:
        failures.append(f"non-utf8 source: {bad.stderr!r}")

    deep = "(" * 40 + "1" + ")" * 40
    arith = f"""phase console
gauge i64
fn keep(n: i64) -> i64
  return n + 1 else 0
end
fn tag(s: bytes) -> bytes
  return s ++ "!"
end
fn main
  let overflow_max = 9223372036854775807 + 1 else 0
  let overflow_min = -9223372036854775808 + -1 else 0
  let sub_min = 0 - -9223372036854775808 else 0
  let neg_min = --9223372036854775808 else 0
  let max_ok = 9223372036854775807 + 0
  let min_ok = -9223372036854775808 + 0
  let min_from_add = -9223372036854775807 + -1
  let parsed_min = i64("-9223372036854775808") else 1
  let parsed_plus = i64("+0010") else 1
  let parsed_bad = i64("9223372036854775808") else 7
  let parsed_space = i64(" 1") else 3
  let stayed = 5 else fail "else-ran"
  let nested = i64("nope") else i64(reason) else 4
  let shadow = 1
  if 1
    let shadow = 9
    set shadow = 8
    write shadow
    write " "
  end
  set shadow = shadow + 1 else 0
  write overflow_max
  write " "
  write overflow_min
  write " "
  write sub_min
  write " "
  write neg_min
  write " "
  write max_ok
  write " "
  write min_ok
  write " "
  write min_from_add
  write " "
  write parsed_min
  write " "
  write parsed_plus
  write " "
  write parsed_bad
  write " "
  write parsed_space
  write " "
  write stayed
  write " "
  write shadow
  write " "
  write keep(41)
  write " "
  write tag("go")
  write " "
  write {deep}
  write " "
  write nested
  write "\\n"
  write "\\"); int evil(void){{return 7;}}"
end
"""
    c_path, arith_exe = compile_fold("arith", arith)
    c_text = c_path.read_text(encoding="utf-8")
    if "int evil" in c_text:
        failures.append("a string broke out into the generated C")
    expected = (
        b"8 0 0 0 0 9223372036854775807 -9223372036854775808 -9223372036854775808 "
        b"-9223372036854775808 10 7 3 5 2 42 go! 1 4\n"
        b'"); int evil(void){return 7;}'
    )
    check("arith", run([str(arith_exe)]), 0, expected, b"", failures)

    bare = """phase console
gauge i64
fn main
  let n = 9223372036854775807 + 1
  write n
end
"""
    _, bare_exe = compile_fold("bare", bare)
    check("bare overflow", run([str(bare_exe)]), 1, b"", b"\n", failures)

    depth = """phase console
gauge i64
fn down(n: i64) -> i64
  if n
    return down(n - 1 else 0)
  end
  return 7
end
fn main
  write down(255)
  write down(255)
  let dead = down(256)
  write dead
end
"""
    _, depth_exe = compile_fold("depth", depth)
    check("call depth", run([str(depth_exe)]), 1, b"77", b"call depth\n", failures)

    sample = BUILD / "sample.bin"
    empty = BUILD / "empty.bin"
    huge = BUILD / "huge.bin"
    lined = BUILD / "lines.bin"
    sample.write_bytes(b"a\0b\n")
    empty.write_bytes(b"")
    lined.write_bytes(b"a\r\nb\n\nc\r\r\n")
    try:
        make_sparse(huge, 2147483648)
    except OSError as exc:
        failures.append(f"sparse file was not created: {exc}")
    else:
        files = f"""phase console
gauge args
gauge file
gauge lines
gauge i64
fn main
  let path = arg(1) else fail "arg"
  let text = open(path, 4, "MISS ", "EMPTY", "LARGE") else fail reason
  write text
  let small = open(path, 3, "MISS ", "EMPTY", "LARGE") else reason
  write small
  write "\\n"
  let blank = open(arg(2) else fail "arg", 10, "MISS ", "EMPTY", "LARGE") else reason
  write blank
  write "\\n"
  let big = open(arg(3) else fail "arg", 100, "MISS ", "EMPTY", "LARGE") else reason
  write big
  write "\\n"
  let directory = open(arg(4) else fail "arg", 10, "MISS ", "EMPTY", "LARGE") else reason
  write directory
  write "\\n"
  let nowhere = open("", 10, "MISS", "EMPTY", "LARGE") else reason
  write nowhere
  write "\\n"
  let lined = open(arg(5) else fail "arg", 100, "MISS ", "EMPTY", "LARGE") else fail reason
  for line in lines(lined)
    write line.n
    write "="
    write line.text
    write ";"
  end
  for line in lines("")
    write "NO"
  end
  for line in lines("\\n")
    write "BLANK"
    write line.n
  end
end
"""
        _, files_exe = compile_fold("files", files)
        directory = str(ROOT)
        proc = run([str(files_exe), str(sample), str(empty), str(huge), directory, str(lined)], timeout=20)
        file_out = b"a\0b\nLARGE\nEMPTY\nLARGE\nMISS " + directory.encode("utf-8") + b"\nMISS\n1=a;2=b;3=;4=c\r;BLANK1"
        check("files", proc, 0, file_out, b"", failures)
        huge.unlink(missing_ok=True)

    unit_c = ROOT / "stress_runtime.c"
    unit_exe = BUILD / "stress_runtime.exe"
    built = clang_exe(unit_c, unit_exe)
    if built.returncode != 0:
        sys.stderr.buffer.write(built.stderr)
        failures.append("runtime unit failed to clang")
    else:
        check("runtime unit", run([str(unit_exe)]), 0, b"", b"", failures)
        wrapped = run([str(unit_exe), "wrap"], timeout=10)
        check("arena wrap", wrapped, 1, b"", b"out of memory\n", failures)

    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"stress passed ({BUILD})")


if __name__ == "__main__":
    main()
