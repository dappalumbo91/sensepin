"""Probe 02 shelf. Contract: probes/02-shelf/task.md."""

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


def parse_row(raw: bytes) -> tuple[bytes, int, int] | None:
    if raw.count(b" ") != 2:
        return None
    name, qty_text, price_text = raw.split(b" ")
    if not name_ok(name):
        return None
    try:
        qty_raw = qty_text.decode("ascii")
        price_raw = price_text.decode("ascii")
    except UnicodeDecodeError:
        return None
    qty = parse_i64(qty_raw)
    price = parse_i64(price_raw)
    if qty is None or price is None:
        return None
    return name, qty, price


def main() -> None:
    if len(sys.argv) != 2:
        die("usage: shelf <file>")
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
    pieces = 0
    worth = 0
    high = 0
    item = b""
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
        parsed = parse_row(raw)
        if parsed is None:
            die_line(line_no, raw)
        name, qty, price = parsed
        line_value = mul_i64(qty, price)
        next_pieces = None if line_value is None else add_i64(pieces, qty)
        next_worth = None if next_pieces is None else add_i64(worth, line_value)
        if line_value is None or next_pieces is None or next_worth is None:
            die_line(line_no, raw)
        pieces = next_pieces
        worth = next_worth
        if not any_line:
            high = line_value
            item = name
            any_line = True
        elif line_value > high:
            high = line_value
            item = name
        count += 1
        if end != -1:
            line_no += 1
            if start == limit:
                break

    sys.stdout.buffer.write(
        f"count {count}\npieces {pieces}\nvalue {worth}\nitem ".encode("ascii")
    )
    sys.stdout.buffer.write(item)
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
