"""Probe 01 grades. Contract: probes/01-grades/task.md."""

import os
import sys

MAX_BYTES = 1_048_576
I64_MIN = -9_223_372_036_854_775_808
I64_MAX = 9_223_372_036_854_775_807


def emit(stream, message: str) -> None:
    stream.buffer.write(message.encode("utf-8"))
    stream.buffer.write(b"\n")


def die(message: str) -> None:
    emit(sys.stderr, message)
    raise SystemExit(1)


def die_line(line_no: int, raw: bytes) -> None:
    sys.stderr.buffer.write(f"bad line {line_no}: ".encode("ascii"))
    sys.stderr.buffer.write(raw)
    sys.stderr.buffer.write(b"\n")
    raise SystemExit(1)


def parse_i64(text: str) -> int | None:
    if text == "" or text == "+" or text == "-":
        return None
    body = text[1:] if text[0] in "+-" else text
    if body == "" or not body.isdigit():
        return None
    value = int(text, 10)
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


def parse_grade(raw: bytes) -> tuple[bytes, int] | None:
    if raw.count(b" ") != 1:
        return None
    name, text_bytes = raw.split(b" ")
    if not name_ok(name):
        return None
    try:
        text = text_bytes.decode("ascii")
    except UnicodeDecodeError:
        return None
    value = parse_i64(text)
    if value is None:
        return None
    return name, value


def trunc_div(total: int, count: int) -> int:
    magnitude = abs(total) // count
    if total < 0:
        return -magnitude
    return magnitude


def main() -> None:
    if len(sys.argv) != 2:
        die("usage: grades <file>")
    path = sys.argv[1]
    try:
        size = os.path.getsize(path)
    except OSError:
        die(f"cannot open {path}")
    if size > MAX_BYTES:
        die("file too large")
    if size == 0:
        die("empty file")
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        die(f"cannot open {path}")

    count = 0
    total = 0
    low = 0
    high = 0
    max_name = b""
    any_line = False
    line_no = 1
    start = 0
    limit = len(data)
    while start < limit:
        end = data.find(b"\n", start)
        if end == -1:
            raw = data[start:]
            start = limit
        else:
            raw = data[start:end]
            start = end + 1
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        parsed = parse_grade(raw)
        value = None if parsed is None else parsed[1]
        overflow = value is not None and (
            (value > 0 and total > I64_MAX - value)
            or (value < 0 and total < I64_MIN - value)
        )
        if parsed is None or overflow:
            die_line(line_no, raw)
        name, value = parsed
        if not any_line:
            low = high = value
            max_name = name
            any_line = True
        else:
            if value < low:
                low = value
            if value > high:
                high = value
                max_name = name
        total += value
        count += 1
        if end != -1:
            line_no += 1
            if start == limit:
                break

    mean = trunc_div(total, count)
    sys.stdout.buffer.write(
        f"count {count}\nmean {mean}\nmin {low}\nmax {high}\nname ".encode("ascii")
    )
    sys.stdout.buffer.write(max_name)
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
