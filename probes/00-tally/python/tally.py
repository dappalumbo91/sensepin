"""Probe 00 tally. Contract: probes/00-tally/task.md."""

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


def main() -> None:
    if len(sys.argv) != 2:
        die("usage: tally <file>")
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
            if start == limit:
                # A final newline does not create another line.
                pass
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            die_line(line_no, raw)
        value = parse_i64(text)
        overflow = value is not None and (
            (value > 0 and total > I64_MAX - value)
            or (value < 0 and total < I64_MIN - value)
        )
        if value is None or overflow:
            die_line(line_no, raw)
        if not any_line:
            low = high = value
            any_line = True
        else:
            if value < low:
                low = value
            if value > high:
                high = value
        total += value
        count += 1
        if end != -1:
            line_no += 1
            if start == limit:
                break

    emit(sys.stdout, f"count {count}")
    emit(sys.stdout, f"sum {total}")
    emit(sys.stdout, f"min {low}")
    emit(sys.stdout, f"max {high}")


if __name__ == "__main__":
    main()
