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


def clang_unit(c_path: Path, exe: Path) -> subprocess.CompletedProcess[bytes]:
    return run([*CLANG, "-I", str(ROOT), "-o", str(exe), "--", str(c_path)])


def clang_program(c_path: Path, exe: Path) -> subprocess.CompletedProcess[bytes]:
    lib = foldc.stage_dll(exe)
    return run([*CLANG, "-I", str(ROOT), "-o", str(exe), "--", str(c_path), str(lib)])


def compile_fold(name: str, source: str) -> tuple[Path, Path]:
    fold_path = BUILD / f"{name}.sensepin"
    c_path = BUILD / f"{name}.c"
    exe = BUILD / f"{name}.exe"
    fold_path.write_text(source, encoding="utf-8")
    try:
        c_path.write_text(foldc.compile_text(source), encoding="utf-8")
    except foldc.FoldError as exc:
        raise SystemExit(f"{name} failed to compile: {exc}") from exc
    built = clang_program(c_path, exe)
    if built.returncode != 0:
        sys.stderr.buffer.write(built.stderr)
        raise SystemExit(f"{name} failed to clang")
    return c_path, exe


def expect_error(
    label: str,
    source: str,
    needle: str,
    failures: list[str],
    origin: Path | None = None,
) -> None:
    try:
        foldc.compile_text(source, origin)
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
    expect_error(
        "bytes call",
        "phase console\ngauge bytes\nfn main\n  let t = bytes(\"a\")\nend\n",
        "bytes()",
        failures,
    )
    expect_error(
        "divide without i64 gauge",
        "phase console\nfn main\n  write 1 / 1\nend\n",
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

    _, cut_exe = compile_fold(
        "cut",
        """phase console
gauge i64
gauge bytes
fn main
  write (10 / 2)
  write " "
  write (0 - 5) / 2
  write " "
  write (0 - 1) / 2
  write " "
  let z = 1 / 0 else 7
  write z
  write " "
  let edge = -9223372036854775808 / -1 else 9
  write edge
  write " "
  write len("ab")
  write " "
  write before("ada 10", " ")
  write " "
  write after("ada 10", " ")
  write " "
  write holds("a  b", " ")
  write " "
  let miss = before("ab", " ") else "NO"
  write miss
  write " "
  let badsep = holds("ab", "") else 4
  write badsep
  write " "
  let ok = 1
  for b in bytes("A_z")
    if b < 48
      set ok = 0
    end
  end
  write ok
  write "\\n"
end
""",
    )
    check(
        "cut",
        run([str(cut_exe)]),
        0,
        b"5 -2 0 7 9 2 ada 10 2 NO 4 1\n",
        b"",
        failures,
    )

    unit_c = ROOT / "stress_runtime.c"
    unit_exe = BUILD / "stress_runtime.exe"
    built = clang_unit(unit_c, unit_exe)
    if built.returncode != 0:
        sys.stderr.buffer.write(built.stderr)
        failures.append("runtime unit failed to clang")
    else:
        check("runtime unit", run([str(unit_exe)]), 0, b"", b"", failures)
        wrapped = run([str(unit_exe), "wrap"], timeout=10)
        check("arena wrap", wrapped, 1, b"", b"out of memory\n", failures)

    try:
        foldc.compile_text("phase console\nfn id(n: f64) -> f64\n  return n\nend\nfn main\nend\n")
    except foldc.FoldError as exc:
        failures.append(f"a typed f64 function with no arithmetic was rejected: {exc}")
    try:
        foldc.compile_text(
            "phase console\nfn id(n: list i64) -> list i64\n  return n\nend\nfn main\nend\n"
        )
    except foldc.FoldError as exc:
        failures.append(f"a typed list function with no list gauge was rejected: {exc}")
    try:
        foldc.compile_text(
            "phase console\nfn id(n: map i64 i64) -> map i64 i64\n  return n\nend\nfn main\nend\n"
        )
    except foldc.FoldError as exc:
        failures.append(f"a typed map function with no map gauge was rejected: {exc}")
    try:
        foldc.compile_text(
            "phase console\nstruct node\n  kids: map i64 node\nend\nfn main\nend\n"
        )
    except foldc.FoldError as exc:
        failures.append(f"a struct map of itself was rejected: {exc}")
    expect_error(
        "empty list",
        "phase console\ngauge list\nfn main\n  let xs = list()\nend\n",
        "list() needs a type",
        failures,
    )
    expect_error(
        "empty map",
        "phase console\ngauge map\nfn main\n  let xs = map()\nend\n",
        "map() needs a type",
        failures,
    )
    expect_error(
        "odd map",
        "phase console\ngauge map\ngauge i64\nfn main\n  let xs = map(1, 2, 3)\nend\n",
        "map needs pairs",
        failures,
    )
    expect_error(
        "mixed map",
        "phase console\ngauge map\ngauge i64\nfn main\n  let xs = map(1, \"a\", \"b\", \"c\")\nend\n",
        "map pairs have different types",
        failures,
    )
    expect_error(
        "map key",
        "phase console\ngauge map\ngauge list\ngauge i64\nfn main\n  let xs = map(list(1), 2)\nend\n",
        "map key needs i64, f64, or bytes",
        failures,
    )
    expect_error(
        "unnamed map",
        "phase console\ngauge i64\nfn main\n  let n = len(map(1, 2))\nend\n",
        "gauge map is not named",
        failures,
    )
    expect_error(
        "unused map",
        "phase console\ngauge map\nfn main\nend\n",
        "gauge map is unused",
        failures,
    )
    expect_error(
        "reserved map",
        "phase console\ngauge i64\nfn map() -> i64\n  return 1\nend\nfn main\nend\n",
        "map is reserved",
        failures,
    )
    expect_error(
        "mixed add",
        "phase console\ngauge i64\ngauge f64\nfn main\n  let n = 1 + 1.0\nend\n",
        "needs i64 or f64",
        failures,
    )
    expect_error(
        "struct cycle",
        "phase console\nstruct box\n  b: box\nend\nfn main\nend\n",
        "struct cycle",
        failures,
    )
    expect_error(
        "use escape",
        "phase console\nuse \"../x.sensepin\"\nfn main\nend\n",
        "beside the source",
        failures,
        BUILD / "escape.sensepin",
    )
    expect_error(
        "missing use",
        "phase console\nuse \"nope.sensepin\"\nfn main\nend\n",
        "missing use",
        failures,
        BUILD / "missing.sensepin",
    )
    (BUILD / "cycle_a.sensepin").write_text(
        "phase console\nuse \"cycle_b.sensepin\"\nfn main\nend\n",
        encoding="utf-8",
    )
    (BUILD / "cycle_b.sensepin").write_text(
        "phase console\nuse \"cycle_a.sensepin\"\nfn hop(n: i64) -> i64\n  return n\nend\n",
        encoding="utf-8",
    )
    expect_error(
        "use cycle",
        (BUILD / "cycle_a.sensepin").read_text(encoding="utf-8"),
        "use cycle",
        failures,
        BUILD / "cycle_a.sensepin",
    )

    surface = ROOT / "examples" / "surface.sensepin"
    surface_c = BUILD / "surface.c"
    surface_exe = BUILD / "surface.exe"
    try:
        surface_c.write_text(foldc.compile_text(surface.read_text(encoding="utf-8"), surface), encoding="utf-8")
    except foldc.FoldError as exc:
        failures.append(f"surface failed to compile: {exc}")
    else:
        built = clang_program(surface_c, surface_exe)
        if built.returncode != 0:
            sys.stderr.buffer.write(built.stderr)
            failures.append("surface failed to clang")
        else:
            check("surface", run([str(surface_exe)]), 0, b"42 0.5 1 3 4 7 0 5 8\n", b"", failures)

    _, edges_exe = compile_fold(
        "edges",
        """phase console
gauge i64
gauge f64
gauge list
struct point
  x: i64
  y: i64
end
struct box
  p: point
end
fn parse(text: bytes) -> i64
  return i64(text) else fail "bad"
end
fn inner() -> i64
  fail "nope"
end
fn outer() -> i64
  return inner() else 4
end
fn main
  let half = 1.0 / 2.0
  let back = i64(0.0 - 1.9)
  let xs: list i64 = list()
  set xs = push(xs, 3)
  set xs = push(xs, 4)
  let p = point(at(xs, 0) else 0, at(xs, 1) else 0)
  let b = box(p)
  let mul_min = -9223372036854775808 * -1 else 9
  let mul_big = 9223372036854775807 * 2 else 8
  let mul_neg = (0 - 3) * (0 - 4)
  let min_one = -9223372036854775808 * 1
  let zero_min = 0 * -9223372036854775808
  let fdiv = 1.0 / 0.0 else 7.0
  let span = 3.0 * 2.0 - 1.0
  let words: list bytes = list("aa", "b")
  let grid: list list i64 = list()
  let row0: list i64 = list(1, 2)
  set grid = push(grid, row0)
  let cell = at(at(grid, 0) else list(0), 1) else 0
  let fs: list f64 = list(1.5, 2.5)
  let missed = at(xs, 9) else 6
  while 0
    write "NO"
  end
  write half
  write " "
  write back
  write " "
  write b.p.y
  write " "
  write outer()
  write " "
  write mul_min
  write " "
  write mul_big
  write " "
  write mul_neg
  write " "
  write min_one
  write " "
  write zero_min
  write " "
  write fdiv
  write " "
  write span
  write " "
  write 1.5 > 1.0
  write " "
  write at(words, 0) else "?"
  write " "
  write len(words)
  write " "
  write cell
  write " "
  write at(fs, 1) else 0.0
  write " "
  write missed
  write "\\n"
end
""",
    )
    check(
        "edges",
        run([str(edges_exe)]),
        0,
        b"0.5 -1 4 4 9 8 12 -9223372036854775808 0 7.0 5.0 1 aa 2 2 2.5 6\n",
        b"",
        failures,
    )

    _, boom_exe = compile_fold(
        "boom",
        """phase console
gauge i64
fn boom() -> i64
  fail "boom"
end
fn main
  let n = boom()
  write n
end
""",
    )
    check("boom", run([str(boom_exe)]), 1, b"", b"boom\n", failures)

    _, maps_exe = compile_fold(
        "maps",
        """phase console
gauge i64
gauge f64
gauge list
gauge map
struct point
  x: i64
  y: i64
end
struct node
  kids: map i64 node
end
fn id(n: map i64 bytes) -> map i64 bytes
  return n
end
fn main
  let fresh = map(1, "a", 2, "b", 1, "c")
  let kept = map(1, 10)
  let replaced = put(kept, 1, 20)
  let grown = put(replaced, 2, 30)
  let zeros = map(0.0, 1, -0.0, 2)
  let words = map("b", 1, "a", 2, "b", 3)
  let empty: map bytes i64 = map()
  let nested: map i64 map bytes i64 = map()
  set nested = put(nested, 1, map("x", 4))
  let spots = map(7, point(2, 3))
  let row: list i64 = list(8, 9)
  let rows = map("r", row)
  let grid: list map i64 i64 = list()
  set grid = push(grid, map(4, 5))
  let missed = get(fresh, 9) else "z"
  let blank = get(empty, "no") else 5
  let named = id(fresh)
  write len(fresh)
  write " "
  write get(fresh, 1) else "?"
  write " "
  write get(fresh, 2) else "?"
  write " "
  write get(kept, 1) else 0
  write " "
  write get(replaced, 1) else 0
  write " "
  write has(kept, 2)
  write " "
  write get(grown, 2) else 0
  write " "
  write len(zeros)
  write " "
  write get(zeros, -0.0) else 0
  write " "
  write len(words)
  write " "
  for k in words
    write k
  end
  write " "
  write get(words, "a") else 0
  write " "
  write len(empty)
  write " "
  write has(empty, "a")
  write " "
  write blank
  write " "
  write get(get(nested, 1) else map("z", 0), "x") else 0
  write " "
  write (get(spots, 7) else point(0, 0)).y
  write " "
  write at(get(rows, "r") else list(0), 1) else 0
  write " "
  write missed
  write " "
  for k in fresh
    write k
    write " "
  end
  write get(named, 1) else "?"
  write " "
  write has(fresh, 2)
  write " "
  write get(at(grid, 0) else map(0, 0), 4) else 0
  write "\\n"
end
""",
    )
    check(
        "maps",
        run([str(maps_exe)]),
        0,
        b"2 c b 10 20 0 30 1 2 2 ba 2 0 0 5 4 3 9 z 1 2 c 1 5\n",
        b"",
        failures,
    )

    _, miss_exe = compile_fold(
        "miss",
        """phase console
gauge map
gauge i64
fn main
  let m = map(1, 2)
  let n = get(m, 3)
  write n
end
""",
    )
    check("miss", run([str(miss_exe)]), 1, b"", b"\n", failures)

    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"stress passed ({BUILD})")


if __name__ == "__main__":
    main()
