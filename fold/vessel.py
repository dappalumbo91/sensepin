"""Sensepin vessel.

Python in this file is the bootstrap. The program that runs is a Windows exe
this tree assembles. clang is not on that path.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

import foldc

I64_MIN = foldc.I64_MIN
I64_MAX = foldc.I64_MAX
U64_MAX = (1 << 64) - 1

HALT = 0
WRITE = 1
FAIL_EXIT = 2
BYTE = 3
SAVE = 4
PUSH_CONST = 5
POP_LOCAL = 6
PUSH_LOCAL = 7
JUMP = 8
JZ = 9
SET_BYTE = 10
IF_FAIL = 11
CLEAR_FAIL = 12
ADD = 13
SUB = 14
MUL = 15
DIV = 16
NEG = 17
CMP = 18
CAT = 19
I64_PARSE = 20
ARGC = 21
ARG = 22
OPEN = 23
BYTE_AT = 24
BYTES_LEN = 25
LINE_VIEW = 26
FIELD_N = 27
FIELD_TEXT = 28
PUSH_REASON = 29
CALL = 30
RET = 31
RET_FAIL = 32
DEC = 34
BEFORE = 35
AFTER = 36
HOLDS = 37
FADD = 38
FSUB = 39
FMUL = 40
FDIV = 41
FNEG = 42
FCMP = 43
FFROM = 44
FTOI = 45
LIST_NEW = 46
LIST_PUSH = 47
LIST_AT = 48
LIST_LEN = 49
STRUCT_NEW = 50
FIELD = 51
MAP_NEW = 52
MAP_PUT = 53
MAP_GET = 54
MAP_HAS = 55
MAP_LEN = 56
MAP_KEY = 57

CMP_EQ, CMP_NE, CMP_LT, CMP_GT, CMP_LE, CMP_GE = range(6)
CMP_CODE = {"==": CMP_EQ, "!=": CMP_NE, "<": CMP_LT, ">": CMP_GT, "<=": CMP_LE, ">=": CMP_GE}

TAG_I64 = 0
TAG_BYTES = 1
TAG_LINE = 2
TAG_F64 = 3
TAG_LIST = 4
TAG_STRUCT = 5
TAG_MAP = 6
CELL_CAP = 8192
CALL_CAP = 256


def i64_parse(text: bytes) -> int | None:
    if not text:
        return None
    neg = False
    index = 0
    if text[0] in (ord("+"), ord("-")):
        neg = text[0] == ord("-")
        index = 1
        if index == len(text):
            return None
    acc = 0
    while index < len(text):
        byte = text[index]
        if byte < 48 or byte > 57:
            return None
        digit = byte - 48
        if acc > U64_MAX // 10 or (acc == U64_MAX // 10 and digit > U64_MAX % 10):
            return None
        acc = acc * 10 + digit
        index += 1
    if not neg:
        if acc > I64_MAX:
            return None
        return acc
    if acc > I64_MAX + 1:
        return None
    if acc == I64_MAX + 1:
        return I64_MIN
    return -acc


def i64_add(left: int, right: int) -> int | None:
    if right > 0 and left > I64_MAX - right:
        return None
    if right < 0 and left < I64_MIN - right:
        return None
    return left + right


def i64_sub(left: int, right: int) -> int | None:
    if right == I64_MIN:
        return None
    return i64_add(left, -right)


def i64_mul(left: int, right: int) -> int | None:
    if left == 0 or right == 0:
        return 0
    if left == I64_MIN:
        return left if right == 1 else None
    if right == I64_MIN:
        return right if left == 1 else None
    aa = -left if left < 0 else left
    bb = -right if right < 0 else right
    if aa > I64_MAX // bb:
        return None
    return left * right


def i64_div(left: int, right: int) -> int | None:
    if right == 0 or (left == I64_MIN and right == -1):
        return None
    sign = -1 if (left < 0) ^ (right < 0) else 1
    return sign * (abs(left) // abs(right))


def i64_neg(value: int) -> int | None:
    if value == I64_MIN:
        return None
    return -value


def f64_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", float(value)))[0]


def f64_from_bits(bits: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", bits & 0xFFFFFFFFFFFFFFFF))[0]


def f64_finite(value: float) -> bool:
    bits = f64_bits(value)
    return (bits & 0x7FF0000000000000) != 0x7FF0000000000000


def f64_result(value: float) -> int | None:
    if not f64_finite(value):
        return None
    return f64_bits(value)


def i64_from_f64(value: float) -> int | None:
    if not f64_finite(value) or value >= 9223372036854775808.0 or value < -9223372036854775808.0:
        return None
    return int(value)


def dec_f64(value: float) -> bytes:
    if value == 0.0:
        value = 0.0
    text = format(value, ".17g")
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text.encode("ascii")


def find_bytes(text: bytes, sep: bytes) -> int | None:
    if not sep or len(sep) > len(text):
        return None
    last = len(text) - len(sep)
    for index in range(last + 1):
        if text[index : index + len(sep)] == sep:
            return index
    return None


def holds_count(text: bytes, sep: bytes) -> int | None:
    if not sep:
        return None
    count = 0
    index = 0
    while index <= len(text) and len(sep) <= len(text) - index:
        if text[index : index + len(sep)] == sep:
            count += 1
            index += len(sep)
        else:
            index += 1
    if count > I64_MAX:
        return None
    return count


@dataclass
class Cell:
    tag: int
    a: int = 0
    b: int = 0
    c: int = 0
    blob: bytes = b""
    items: tuple["Cell", ...] = ()

    @staticmethod
    def i64(value: int) -> Cell:
        return Cell(TAG_I64, a=value)

    @staticmethod
    def f64(bits: int) -> Cell:
        return Cell(TAG_F64, a=bits & 0xFFFFFFFFFFFFFFFF)

    @staticmethod
    def bytes(data: bytes) -> Cell:
        return Cell(TAG_BYTES, b=len(data), blob=bytes(data))

    @staticmethod
    def line(data: bytes, number: int) -> Cell:
        return Cell(TAG_LINE, b=len(data), c=number, blob=bytes(data))

    @staticmethod
    def listed(items: tuple["Cell", ...]) -> Cell:
        return Cell(TAG_LIST, b=len(items), items=items)

    @staticmethod
    def struct(items: tuple["Cell", ...]) -> Cell:
        return Cell(TAG_STRUCT, b=len(items), items=items)

    @staticmethod
    def mapped(items: tuple["Cell", ...]) -> Cell:
        return Cell(TAG_MAP, b=len(items) // 2, items=items)


def share(cell: Cell) -> Cell:
    return Cell(cell.tag, cell.a, cell.b, cell.c, cell.blob, cell.items)


def keys_equal(left: Cell, right: Cell) -> bool:
    if left.tag != right.tag:
        return False
    if left.tag == TAG_F64:
        return f64_from_bits(left.a) == f64_from_bits(right.a)
    if left.tag == TAG_BYTES:
        return left.blob == right.blob
    return left.a == right.a


def map_count(cell: Cell) -> int:
    return len(cell.items) // 2


def map_put(src: Cell, key: Cell, value: Cell) -> Cell:
    items = list(src.items)
    for index in range(0, len(items), 2):
        if keys_equal(items[index], key):
            items[index + 1] = share(value)
            return Cell.mapped(tuple(items))
    items.append(share(key))
    items.append(share(value))
    return Cell.mapped(tuple(items))


def clone(cell: Cell) -> Cell:
    return Cell(
        cell.tag,
        cell.a,
        cell.b,
        cell.c,
        cell.blob,
        tuple(clone(item) for item in cell.items),
    )


class Bytecode:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def label(self, name: str) -> None:
        if name in self.labels:
            raise RuntimeError(f"duplicate label {name}")
        self.labels[name] = len(self.buf)

    def op(self, opcode: int) -> None:
        self.buf.append(opcode)

    def u8(self, value: int) -> None:
        self.buf.append(value & 0xFF)

    def u16(self, value: int) -> None:
        self.buf += (value & 0xFFFF).to_bytes(2, "little")

    def i32(self, name: str) -> None:
        self.fixups.append((len(self.buf), name))
        self.buf += b"\0\0\0\0"

    def patch(self) -> bytes:
        for at, name in self.fixups:
            rel = self.labels[name] - (at + 4)
            self.buf[at : at + 4] = (rel & 0xFFFFFFFF).to_bytes(4, "little")
        return bytes(self.buf)


@dataclass
class FuncRec:
    name: str
    off: int
    nparams: int
    nlocals: int


@dataclass
class Compiled:
    code: bytes
    consts: list[tuple[str, object]]
    funcs: list[FuncRec]
    main: int


class Emitter:
    def __init__(self, program: foldc.Program, types: dict[int, str]):
        self.program = program
        self.types = types
        self.bc = Bytecode()
        self.consts: list[tuple[str, object]] = []
        self.const_at: dict[tuple[str, object], int] = {}
        self.funcs: list[FuncRec] = []
        self.fn_index = {fn.name: index for index, fn in enumerate(program.fns)}
        self.scopes: list[dict[str, int]] = []
        self.nlocals = 0
        self.serial = 0
        self.fn: foldc.Fn | None = None
        self.unwind = ""

    def fresh(self) -> int:
        slot = self.nlocals
        self.nlocals += 1
        return slot

    def bind(self, name: str) -> int:
        slot = self.fresh()
        self.scopes[-1][name] = slot
        return slot

    def lookup(self, name: str, line: int) -> int:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        foldc.fail(line, f"unknown name {name}")
        raise AssertionError

    def lab(self, stem: str) -> str:
        self.serial += 1
        return f"{stem}_{self.serial}"

    def const_i64(self, value: int) -> int:
        key = ("i64", value)
        if key not in self.const_at:
            self.const_at[key] = len(self.consts)
            self.consts.append(key)
        return self.const_at[key]

    def const_bytes(self, value: bytes) -> int:
        key = ("bytes", bytes(value))
        if key not in self.const_at:
            self.const_at[key] = len(self.consts)
            self.consts.append(key)
        return self.const_at[key]

    def const_f64(self, value: float) -> int:
        bits = f64_bits(0.0 if value == 0.0 else value)
        key = ("f64", bits)
        if key not in self.const_at:
            self.const_at[key] = len(self.consts)
            self.consts.append(key)
        return self.const_at[key]

    def push_const(self, index: int) -> None:
        self.bc.op(PUSH_CONST)
        self.bc.u16(index)

    def push_i64(self, value: int) -> None:
        self.push_const(self.const_i64(value))

    def push_bytes(self, value: bytes) -> None:
        self.push_const(self.const_bytes(value))

    def pop_local(self, slot: int) -> None:
        self.bc.op(POP_LOCAL)
        self.bc.u16(slot)

    def push_local(self, slot: int) -> None:
        self.bc.op(PUSH_LOCAL)
        self.bc.u16(slot)

    def jump(self, opcode: int, name: str) -> None:
        self.bc.op(opcode)
        self.bc.i32(name)

    def mark(self, name: str) -> None:
        self.bc.label(name)

    def if_fail(self, name: str) -> None:
        self.jump(IF_FAIL, name)

    def compile(self) -> Compiled:
        main = -1
        for index, fn in enumerate(self.program.fns):
            if fn.name == "main":
                main = index
            self.emit_fn(fn, index)
        if main < 0:
            foldc.fail(1, "root file needs fn main")
        return Compiled(self.bc.patch(), self.consts, self.funcs, main)

    def emit_fn(self, fn: foldc.Fn, index: int) -> None:
        self.fn = fn
        self.nlocals = 0
        self.scopes = [{}]
        for param in fn.params:
            self.bind(param.name)
        self.unwind = self.lab("unwind")
        off = len(self.bc.buf)
        self.stmts(fn.body, self.unwind)
        if fn.name == "main":
            self.bc.op(HALT)
        self.mark(self.unwind)
        self.bc.op(PUSH_REASON)
        self.bc.op(FAIL_EXIT if fn.name == "main" else RET_FAIL)
        self.funcs.append(FuncRec(fn.name, off, len(fn.params), self.nlocals))
        if index != len(self.funcs) - 1:
            raise RuntimeError("function order drifted")

    def stmts(self, rows: list, fail_to: str) -> None:
        for row in rows:
            self.stmt(row, fail_to)

    def stmt(self, row: object, fail_to: str) -> None:
        if isinstance(row, foldc.Let):
            self.expr(row.expr, fail_to)
            self.pop_local(self.bind(row.name))
            return
        if isinstance(row, foldc.Set):
            self.expr(row.expr, fail_to)
            self.pop_local(self.lookup(row.name, row.line))
            return
        if isinstance(row, foldc.Write):
            self.as_bytes(row.expr, fail_to)
            self.bc.op(WRITE)
            return
        if isinstance(row, foldc.Fail):
            self.fail_with(row.expr, fail_to)
            return
        if isinstance(row, foldc.Return):
            self.expr(row.expr, fail_to)
            self.bc.op(RET)
            return
        if isinstance(row, foldc.If):
            alt = self.lab("else")
            done = self.lab("endif")
            self.expr(row.cond, fail_to)
            self.jump(JZ, alt)
            self.scopes.append({})
            self.stmts(row.then, fail_to)
            self.scopes.pop()
            self.jump(JUMP, done)
            self.mark(alt)
            if row.els is not None:
                self.scopes.append({})
                self.stmts(row.els, fail_to)
                self.scopes.pop()
            self.mark(done)
            return
        if isinstance(row, foldc.While):
            head = self.lab("while")
            done = self.lab("wend")
            self.mark(head)
            self.expr(row.cond, fail_to)
            self.jump(JZ, done)
            self.scopes.append({})
            self.stmts(row.body, fail_to)
            self.scopes.pop()
            self.jump(JUMP, head)
            self.mark(done)
            return
        if isinstance(row, foldc.For):
            self.for_stmt(row, fail_to)
            return
        foldc.fail(1, "unknown statement")

    def for_stmt(self, row: foldc.For, fail_to: str) -> None:
        call = row.expr
        if isinstance(call, foldc.Call) and call.name in {"lines", "bytes"}:
            if call.name == "lines":
                self.for_lines(row, call, fail_to)
            else:
                self.for_bytes(row, call, fail_to)
            return
        kind = self.types[id(row.expr)]
        if kind.startswith("list "):
            self.for_list(row, fail_to)
            return
        if kind.startswith("map "):
            self.for_map(row, fail_to)
            return
        foldc.fail(row.line, "vessel has no map walk yet")

    def for_lines(self, row: foldc.For, call: foldc.Call, fail_to: str) -> None:
        text = self.fresh()
        index = self.fresh()
        number = self.fresh()
        line = self.fresh()
        self.expr(call.args[0], fail_to)
        self.pop_local(text)
        self.push_i64(0)
        self.pop_local(index)
        self.push_i64(1)
        self.pop_local(number)
        loop = self.lab("lines")
        body = self.lab("lbody")
        done = self.lab("lend")
        self.mark(loop)
        self.push_local(index)
        self.push_local(text)
        self.bc.op(BYTES_LEN)
        self.if_fail(fail_to)
        self.bc.op(CMP)
        self.bc.u8(CMP_GE)
        self.jump(JZ, body)
        self.jump(JUMP, done)
        self.mark(body)
        self.push_local(text)
        self.push_local(index)
        self.push_local(number)
        self.bc.op(LINE_VIEW)
        self.if_fail(fail_to)
        self.pop_local(index)
        self.pop_local(line)
        self.scopes.append({row.name: line})
        self.stmts(row.body, fail_to)
        self.scopes.pop()
        self.push_local(number)
        self.push_i64(1)
        self.bc.op(ADD)
        self.if_fail(fail_to)
        self.pop_local(number)
        self.jump(JUMP, loop)
        self.mark(done)

    def for_bytes(self, row: foldc.For, call: foldc.Call, fail_to: str) -> None:
        text = self.fresh()
        index = self.fresh()
        byte = self.fresh()
        self.expr(call.args[0], fail_to)
        self.pop_local(text)
        self.push_i64(0)
        self.pop_local(index)
        loop = self.lab("bytes")
        body = self.lab("bbody")
        done = self.lab("bend")
        self.mark(loop)
        self.push_local(index)
        self.push_local(text)
        self.bc.op(BYTES_LEN)
        self.if_fail(fail_to)
        self.bc.op(CMP)
        self.bc.u8(CMP_GE)
        self.jump(JZ, body)
        self.jump(JUMP, done)
        self.mark(body)
        self.push_local(text)
        self.push_local(index)
        self.bc.op(BYTE_AT)
        self.if_fail(fail_to)
        self.pop_local(byte)
        self.scopes.append({row.name: byte})
        self.stmts(row.body, fail_to)
        self.scopes.pop()
        self.push_local(index)
        self.push_i64(1)
        self.bc.op(ADD)
        self.if_fail(fail_to)
        self.pop_local(index)
        self.jump(JUMP, loop)
        self.mark(done)

    def for_list(self, row: foldc.For, fail_to: str) -> None:
        xs = self.fresh()
        index = self.fresh()
        item = self.fresh()
        self.expr(row.expr, fail_to)
        self.pop_local(xs)
        self.push_i64(0)
        self.pop_local(index)
        loop = self.lab("list")
        body = self.lab("listbody")
        done = self.lab("listdone")
        self.mark(loop)
        self.push_local(index)
        self.push_local(xs)
        self.bc.op(LIST_LEN)
        self.if_fail(fail_to)
        self.bc.op(CMP)
        self.bc.u8(CMP_GE)
        self.jump(JZ, body)
        self.jump(JUMP, done)
        self.mark(body)
        self.push_local(xs)
        self.push_local(index)
        self.bc.op(LIST_AT)
        self.if_fail(fail_to)
        self.pop_local(item)
        self.scopes.append({row.name: item})
        self.stmts(row.body, fail_to)
        self.scopes.pop()
        self.push_local(index)
        self.push_i64(1)
        self.bc.op(ADD)
        self.if_fail(fail_to)
        self.pop_local(index)
        self.jump(JUMP, loop)
        self.mark(done)

    def for_map(self, row: foldc.For, fail_to: str) -> None:
        xs = self.fresh()
        index = self.fresh()
        item = self.fresh()
        self.expr(row.expr, fail_to)
        self.pop_local(xs)
        self.push_i64(0)
        self.pop_local(index)
        loop = self.lab("map")
        body = self.lab("mapbody")
        done = self.lab("mapdone")
        self.mark(loop)
        self.push_local(index)
        self.push_local(xs)
        self.bc.op(MAP_LEN)
        self.if_fail(fail_to)
        self.bc.op(CMP)
        self.bc.u8(CMP_GE)
        self.jump(JZ, body)
        self.jump(JUMP, done)
        self.mark(body)
        self.push_local(xs)
        self.push_local(index)
        self.bc.op(MAP_KEY)
        self.if_fail(fail_to)
        self.pop_local(item)
        self.scopes.append({row.name: item})
        self.stmts(row.body, fail_to)
        self.scopes.pop()
        self.push_local(index)
        self.push_i64(1)
        self.bc.op(ADD)
        self.if_fail(fail_to)
        self.pop_local(index)
        self.jump(JUMP, loop)
        self.mark(done)

    def field_index(self, owner: str, field_name: str, line: int) -> int:
        for struct in self.program.structs:
            if struct.name == owner:
                for index, field in enumerate(struct.fields):
                    if field.name == field_name:
                        return index
        foldc.fail(line, f"vessel has no field {field_name}")
        raise AssertionError

    def as_bytes(self, expr: object, fail_to: str) -> None:
        kind = self.types[id(expr)]
        self.expr(expr, fail_to)
        if kind in {"i64", "f64"}:
            self.bc.op(DEC)
            return
        if kind == "bytes":
            return
        foldc.fail(getattr(expr, "line", 1), "vessel has no text for that value yet")

    def fail_with(self, expr: object, fail_to: str) -> None:
        self.as_bytes(expr, fail_to)
        self.bc.op(FAIL_EXIT if self.fn is not None and self.fn.name == "main" else RET_FAIL)

    def expr(self, expr: object, fail_to: str) -> None:
        if isinstance(expr, foldc.IntLit):
            self.push_i64(expr.value)
            return
        if isinstance(expr, foldc.StrLit):
            self.push_bytes(expr.value)
            return
        if isinstance(expr, foldc.FloatLit):
            self.push_const(self.const_f64(expr.value))
            return
        if isinstance(expr, foldc.Name):
            if expr.name == "reason":
                self.bc.op(PUSH_REASON)
                return
            self.push_local(self.lookup(expr.name, expr.line))
            return
        if isinstance(expr, foldc.Field):
            owner = self.types[id(expr.recv)]
            self.expr(expr.recv, fail_to)
            if owner == "line" and expr.field == "text":
                self.bc.op(FIELD_TEXT)
                return
            if owner == "line" and expr.field == "n":
                self.bc.op(FIELD_N)
                return
            index = self.field_index(owner, expr.field, expr.line)
            self.bc.op(FIELD)
            self.bc.u16(index)
            return
        if isinstance(expr, foldc.Call):
            self.call(expr, fail_to)
            return
        if isinstance(expr, foldc.Fail):
            self.fail_with(expr.expr, fail_to)
            return
        if isinstance(expr, foldc.Unary):
            self.expr(expr.expr, fail_to)
            kind = self.types[id(expr.expr)]
            if kind == "f64":
                self.bc.op(FNEG)
            elif kind == "i64":
                self.bc.op(NEG)
            else:
                foldc.fail(expr.line, "vessel has no negation for that value yet")
            self.if_fail(fail_to)
            return
        if isinstance(expr, foldc.Binary):
            self.binary(expr, fail_to)
            return
        if isinstance(expr, foldc.Else):
            right = self.lab("or")
            done = self.lab("ordone")
            self.bc.op(CLEAR_FAIL)
            self.expr(expr.left, right)
            self.jump(JUMP, done)
            self.mark(right)
            self.bc.op(CLEAR_FAIL)
            self.expr(expr.right, fail_to)
            self.mark(done)
            return
        foldc.fail(1, "unknown expression")

    def binary(self, expr: foldc.Binary, fail_to: str) -> None:
        if expr.op == "++":
            self.as_bytes(expr.left, fail_to)
            self.as_bytes(expr.right, fail_to)
            self.bc.op(CAT)
            return
        self.expr(expr.left, fail_to)
        self.expr(expr.right, fail_to)
        left = self.types[id(expr.left)]
        right = self.types[id(expr.right)]
        if left == "f64" and right == "f64":
            if expr.op in CMP_CODE:
                self.bc.op(FCMP)
                self.bc.u8(CMP_CODE[expr.op])
                return
            opcode = {"+": FADD, "-": FSUB, "*": FMUL, "/": FDIV}[expr.op]
            self.bc.op(opcode)
            self.if_fail(fail_to)
            return
        if left != "i64" or right != "i64":
            foldc.fail(expr.line, "vessel has no mixed arithmetic yet")
        if expr.op in CMP_CODE:
            self.bc.op(CMP)
            self.bc.u8(CMP_CODE[expr.op])
            return
        opcode = {"+": ADD, "-": SUB, "*": MUL, "/": DIV}[expr.op]
        self.bc.op(opcode)
        self.if_fail(fail_to)

    def call(self, expr: foldc.Call, fail_to: str) -> None:
        name = expr.name
        if name == "map":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(MAP_NEW)
            self.bc.u16(len(expr.args) // 2)
            return
        if name == "put":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(MAP_PUT)
            return
        if name == "get":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(MAP_GET)
            self.if_fail(fail_to)
            return
        if name == "has":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(MAP_HAS)
            return
        if name == "list":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(LIST_NEW)
            self.bc.u16(len(expr.args))
            return
        if name == "push":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(LIST_PUSH)
            return
        if name == "at":
            for arg in expr.args:
                self.expr(arg, fail_to)
            kind = self.types[id(expr.args[0])]
            self.bc.op(BYTE_AT if kind == "bytes" else LIST_AT)
            self.if_fail(fail_to)
            return
        if name == "byte":
            self.expr(expr.args[0], fail_to)
            self.bc.op(BYTE)
            self.if_fail(fail_to)
            return
        if name == "set_byte":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(SET_BYTE)
            self.if_fail(fail_to)
            return
        if name == "save":
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(SAVE)
            self.if_fail(fail_to)
            return
        if name == "f64":
            self.expr(expr.args[0], fail_to)
            self.bc.op(FFROM)
            self.if_fail(fail_to)
            return
        if name == "len":
            self.expr(expr.args[0], fail_to)
            kind = self.types[id(expr.args[0])]
            if kind == "bytes":
                self.bc.op(BYTES_LEN)
            elif kind.startswith("list "):
                self.bc.op(LIST_LEN)
            elif kind.startswith("map "):
                self.bc.op(MAP_LEN)
            else:
                foldc.fail(expr.line, "vessel has no len of that value yet")
            self.if_fail(fail_to)
            return
        if name == "i64":
            self.expr(expr.args[0], fail_to)
            kind = self.types[id(expr.args[0])]
            if kind == "bytes":
                self.bc.op(I64_PARSE)
            elif kind == "f64":
                self.bc.op(FTOI)
            else:
                foldc.fail(expr.line, "i64 expects bytes or f64")
            self.if_fail(fail_to)
            return
        if name == "argc":
            self.bc.op(ARGC)
            return
        if name == "arg":
            self.expr(expr.args[0], fail_to)
            self.bc.op(ARG)
            self.if_fail(fail_to)
            return
        if name in {"open", "before", "after", "holds"}:
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op({"open": OPEN, "before": BEFORE, "after": AFTER, "holds": HOLDS}[name])
            self.if_fail(fail_to)
            return
        if name in self.fn_index:
            for arg in expr.args:
                self.expr(arg, fail_to)
            self.bc.op(CALL)
            self.bc.u16(self.fn_index[name])
            self.if_fail(fail_to)
            return
        for struct in self.program.structs:
            if struct.name == name:
                if len(expr.args) != len(struct.fields):
                    foldc.fail(expr.line, "struct field count")
                for arg in expr.args:
                    self.expr(arg, fail_to)
                self.bc.op(STRUCT_NEW)
                self.bc.u16(len(struct.fields))
                return
        foldc.fail(expr.line, f"vessel has no {name} yet")


class Stop(Exception):
    def __init__(self, code: int):
        self.code = code


def vm_run(image: Compiled, argv: list[bytes]) -> tuple[int, bytes, bytes]:
    cells = [Cell.i64(0) for _ in range(CELL_CAP)]
    main = image.funcs[image.main]
    sp = main.nlocals
    frame = 0
    ip = main.off
    depth = 0
    failed = False
    reason = b""
    calls: list[tuple[int, int, int]] = []
    out = bytearray()
    err = bytearray()
    code = image.code
    steps = 0

    def push(cell: Cell) -> None:
        nonlocal sp
        if sp >= CELL_CAP:
            err.extend(b"out of memory\n")
            raise Stop(1)
        cells[sp] = clone(cell)
        sp += 1

    def pop() -> Cell:
        nonlocal sp
        sp -= 1
        return cells[sp]

    def const_cell(index: int) -> Cell:
        kind, value = image.consts[index]
        if kind == "i64":
            return Cell.i64(int(value))  # type: ignore[arg-type]
        if kind == "f64":
            return Cell.f64(int(value))  # type: ignore[arg-type]
        return Cell.bytes(bytes(value))  # type: ignore[arg-type]

    def set_fail(data: bytes) -> None:
        nonlocal failed, reason
        failed = True
        reason = data

    def read_u16() -> int:
        nonlocal ip
        value = int.from_bytes(code[ip : ip + 2], "little")
        ip += 2
        return value

    def read_i32() -> int:
        nonlocal ip
        value = int.from_bytes(code[ip : ip + 4], "little", signed=True)
        ip += 4
        return value

    def as_i64(cell: Cell) -> int:
        return cell.a

    def as_bytes(cell: Cell) -> bytes:
        if cell.tag == TAG_LINE:
            return cell.blob
        return cell.blob

    try:
        while True:
            steps += 1
            if steps > 100_000_000:
                raise RuntimeError("step limit")
            op = code[ip]
            if os.environ.get("SENSEPIN_TRACE"):
                print(f"ip {ip} op {op} sp {sp} fail {failed}", file=sys.stderr)
            ip += 1
            if op == HALT:
                return 0, bytes(out), bytes(err)
            if op == WRITE:
                out.extend(as_bytes(pop()))
                continue
            if op == FAIL_EXIT:
                err.extend(as_bytes(pop()))
                err.extend(b"\n")
                return 1, bytes(out), bytes(err)
            if op == PUSH_CONST:
                push(const_cell(read_u16()))
                continue
            if op == POP_LOCAL:
                cells[frame + read_u16()] = pop()
                continue
            if op == PUSH_LOCAL:
                push(cells[frame + read_u16()])
                continue
            if op == JUMP:
                rel = read_i32()
                ip += rel
                continue
            if op == JZ:
                value = as_i64(pop())
                rel = read_i32()
                if value == 0:
                    ip += rel
                continue
            if op == IF_FAIL:
                rel = read_i32()
                if failed:
                    ip += rel
                continue
            if op == CLEAR_FAIL:
                failed = False
                continue
            if op in {ADD, SUB, MUL, DIV}:
                right = as_i64(pop())
                left = as_i64(pop())
                fn = {ADD: i64_add, SUB: i64_sub, MUL: i64_mul, DIV: i64_div}[op]
                got = fn(left, right)
                if got is None:
                    set_fail(b"")
                else:
                    push(Cell.i64(got))
                continue
            if op == NEG:
                got = i64_neg(as_i64(pop()))
                if got is None:
                    set_fail(b"")
                else:
                    push(Cell.i64(got))
                continue
            if op == CMP:
                kind = code[ip]
                ip += 1
                right = as_i64(pop())
                left = as_i64(pop())
                result = {
                    CMP_EQ: left == right,
                    CMP_NE: left != right,
                    CMP_LT: left < right,
                    CMP_GT: left > right,
                    CMP_LE: left <= right,
                    CMP_GE: left >= right,
                }[kind]
                push(Cell.i64(1 if result else 0))
                continue
            if op == CAT:
                right = as_bytes(pop())
                left = as_bytes(pop())
                if len(left) > U64_MAX - len(right):
                    err.extend(b"out of memory\n")
                    return 1, bytes(out), bytes(err)
                push(Cell.bytes(left + right))
                continue
            if op == DEC:
                cell = pop()
                if cell.tag == TAG_F64:
                    push(Cell.bytes(dec_f64(f64_from_bits(cell.a))))
                else:
                    push(Cell.bytes(str(as_i64(cell)).encode("ascii")))
                continue
            if op == I64_PARSE:
                got = i64_parse(as_bytes(pop()))
                if got is None:
                    set_fail(b"")
                else:
                    push(Cell.i64(got))
                continue
            if op == ARGC:
                push(Cell.i64(len(argv)))
                continue
            if op == ARG:
                index = as_i64(pop())
                if index < 0 or index >= len(argv):
                    set_fail(b"")
                else:
                    push(Cell.bytes(argv[index]))
                continue
            if op == OPEN:
                large = as_bytes(pop())
                empty = as_bytes(pop())
                missing = as_bytes(pop())
                limit = as_i64(pop())
                path = as_bytes(pop())
                ok, opened = vm_open(path, limit, missing, empty, large)
                if ok:
                    push(Cell.bytes(opened))
                else:
                    set_fail(opened)
                continue
            if op == BYTES_LEN:
                data = as_bytes(pop())
                if len(data) > I64_MAX:
                    set_fail(b"")
                else:
                    push(Cell.i64(len(data)))
                continue
            if op == BYTE_AT:
                index = as_i64(pop())
                data = as_bytes(pop())
                if index < 0 or index >= len(data):
                    set_fail(b"")
                else:
                    push(Cell.i64(data[index]))
                continue
            if op == BYTE:
                value = as_i64(pop())
                if value < 0 or value > 255:
                    set_fail(b"")
                else:
                    push(Cell.bytes(bytes([value])))
                continue
            if op == SET_BYTE:
                value = as_i64(pop())
                index = as_i64(pop())
                data = as_bytes(pop())
                if value < 0 or value > 255 or index < 0 or index >= len(data):
                    set_fail(b"")
                else:
                    raw = bytearray(data)
                    raw[index] = value
                    push(Cell.bytes(bytes(raw)))
                continue
            if op == SAVE:
                data = as_bytes(pop())
                path = as_bytes(pop())
                if b"\x00" in path:
                    set_fail(b"")
                else:
                    try:
                        with open(os.fsdecode(path), "wb") as handle:
                            handle.write(data)
                        push(Cell.i64(len(data)))
                    except OSError:
                        set_fail(b"")
                continue
            if op == LINE_VIEW:
                number = as_i64(pop())
                index = as_i64(pop())
                data = as_bytes(pop())
                if index < 0 or index > len(data):
                    set_fail(b"")
                    continue
                end = index
                while end < len(data) and data[end] != 10:
                    end += 1
                stop = end
                if stop > index and data[stop - 1] == 13:
                    stop -= 1
                nxt = len(data) if end == len(data) else end + 1
                push(Cell.line(data[index:stop], number))
                push(Cell.i64(nxt))
                continue
            if op == FIELD_N:
                push(Cell.i64(pop().c))
                continue
            if op == FIELD_TEXT:
                cell = pop()
                push(Cell.bytes(cell.blob))
                continue
            if op == PUSH_REASON:
                push(Cell.bytes(reason))
                continue
            if op == BEFORE or op == AFTER:
                sep = as_bytes(pop())
                text = as_bytes(pop())
                at = find_bytes(text, sep)
                if at is None:
                    set_fail(b"")
                elif op == BEFORE:
                    push(Cell.bytes(text[:at]))
                else:
                    push(Cell.bytes(text[at + len(sep) :]))
                continue
            if op == HOLDS:
                sep = as_bytes(pop())
                text = as_bytes(pop())
                got = holds_count(text, sep)
                if got is None:
                    set_fail(b"")
                else:
                    push(Cell.i64(got))
                continue
            if op == CALL:
                func = image.funcs[read_u16()]
                if depth >= CALL_CAP:
                    err.extend(b"call depth\n")
                    return 1, bytes(out), bytes(err)
                before = sp - func.nparams
                calls.append((ip, frame, before))
                frame = before
                for slot in range(func.nparams, func.nlocals):
                    cells[frame + slot] = Cell.i64(0)
                sp = frame + func.nlocals
                ip = func.off
                depth += 1
                continue
            if op == RET:
                value = pop()
                ip, frame, sp = calls.pop()
                depth -= 1
                push(value)
                continue
            if op == RET_FAIL:
                reason_cell = pop()
                set_fail(as_bytes(reason_cell))
                ip, frame, sp = calls.pop()
                depth -= 1
                continue
            if op in {FADD, FSUB, FMUL, FDIV}:
                right = f64_from_bits(pop().a)
                left = f64_from_bits(pop().a)
                try:
                    if op == FADD:
                        raw = left + right
                    elif op == FSUB:
                        raw = left - right
                    elif op == FMUL:
                        raw = left * right
                    else:
                        raw = left / right
                except ZeroDivisionError:
                    raw = float("nan")
                bits = f64_result(raw)
                if bits is None:
                    set_fail(b"")
                else:
                    push(Cell.f64(bits))
                continue
            if op == FNEG:
                bits = f64_result(-f64_from_bits(pop().a))
                if bits is None:
                    set_fail(b"")
                else:
                    push(Cell.f64(bits))
                continue
            if op == FCMP:
                kind = code[ip]
                ip += 1
                right = f64_from_bits(pop().a)
                left = f64_from_bits(pop().a)
                result = {
                    CMP_EQ: left == right,
                    CMP_NE: left != right,
                    CMP_LT: left < right,
                    CMP_GT: left > right,
                    CMP_LE: left <= right,
                    CMP_GE: left >= right,
                }[kind]
                push(Cell.i64(1 if result else 0))
                continue
            if op == FFROM:
                push(Cell.f64(f64_bits(float(as_i64(pop())))))
                continue
            if op == FTOI:
                got = i64_from_f64(f64_from_bits(pop().a))
                if got is None:
                    set_fail(b"")
                else:
                    push(Cell.i64(got))
                continue
            if op == LIST_NEW:
                count = read_u16()
                items: list[Cell] = [Cell.i64(0) for _ in range(count)]
                for index in range(count - 1, -1, -1):
                    items[index] = pop()
                push(Cell.listed(tuple(items)))
                continue
            if op == LIST_PUSH:
                value = pop()
                xs = pop()
                push(Cell.listed(xs.items + (value,)))
                continue
            if op == LIST_AT:
                index = as_i64(pop())
                xs = pop()
                if index < 0 or index >= len(xs.items):
                    set_fail(b"")
                else:
                    push(xs.items[index])
                continue
            if op == LIST_LEN:
                xs = pop()
                count = len(xs.items)
                if count > I64_MAX:
                    set_fail(b"")
                else:
                    push(Cell.i64(count))
                continue
            if op == STRUCT_NEW:
                count = read_u16()
                items = [Cell.i64(0) for _ in range(count)]
                for index in range(count - 1, -1, -1):
                    items[index] = pop()
                push(Cell.struct(tuple(items)))
                continue
            if op == FIELD:
                index = read_u16()
                obj = pop()
                push(obj.items[index])
                continue
            if op == MAP_NEW:
                count = read_u16()
                pairs: list[tuple[Cell, Cell]] = []
                for _ in range(count):
                    val = pop()
                    key = pop()
                    pairs.append((key, val))
                pairs.reverse()
                built = Cell.mapped(())
                for key, val in pairs:
                    built = map_put(built, key, val)
                push(built)
                continue
            if op == MAP_PUT:
                val = pop()
                key = pop()
                src = pop()
                push(map_put(src, key, val))
                continue
            if op == MAP_GET:
                key = pop()
                src = pop()
                found = None
                for index in range(0, len(src.items), 2):
                    if keys_equal(src.items[index], key):
                        found = src.items[index + 1]
                        break
                if found is None:
                    set_fail(b"")
                else:
                    push(found)
                continue
            if op == MAP_HAS:
                key = pop()
                src = pop()
                hit = 0
                for index in range(0, len(src.items), 2):
                    if keys_equal(src.items[index], key):
                        hit = 1
                        break
                push(Cell.i64(hit))
                continue
            if op == MAP_LEN:
                src = pop()
                count = map_count(src)
                if count > I64_MAX:
                    set_fail(b"")
                else:
                    push(Cell.i64(count))
                continue
            if op == MAP_KEY:
                index = as_i64(pop())
                src = pop()
                if index < 0 or index >= map_count(src):
                    set_fail(b"")
                else:
                    push(src.items[index * 2])
                continue
            raise RuntimeError(f"opcode {op}")
    except Stop as done:
        return done.code, bytes(out), bytes(err)


def vm_open(path: bytes, limit: int, missing: bytes, empty: bytes, large: bytes) -> tuple[bool, bytes]:
    if limit < 0:
        return False, large
    if b"\x00" in path:
        return False, missing + path
    try:
        name = os.fsdecode(path)
        info = os.stat(name)
    except OSError:
        return False, missing + path
    if not stat.S_ISREG(info.st_mode):
        return False, missing + path
    size = info.st_size
    if size == 0:
        return False, empty
    if size > limit:
        return False, large
    try:
        with open(name, "rb") as handle:
            data = handle.read()
    except OSError:
        return False, missing + path
    if len(data) != size:
        return False, missing + path
    return True, data


def compile_text(text: str, origin: Path | None = None) -> Compiled:
    try:
        program = foldc.load_program(text, origin)
        types = foldc.Checker(program).check()
        return Emitter(program, types).compile()
    except RecursionError as exc:
        raise foldc.FoldError("source is too deep") from exc


def compile_path(source: Path) -> Compiled:
    return compile_text(foldc.source_text(source.read_bytes()), source)


def run_vm_text(text: str, argv: list[bytes] | None = None) -> tuple[int, bytes, bytes]:
    image = compile_text(text, None)
    args = [b"sensepin"] if argv is None else argv
    return vm_run(image, args)


def _check(name: str, got: tuple[int, bytes, bytes], code: int, out: bytes, err: bytes) -> None:
    if got != (code, out, err):
        raise SystemExit(f"{name}\n got {got[0]} {got[1]!r} {got[2]!r}\n want {code} {out!r} {err!r}")


def selftest_vm() -> None:
    _check("double", run_vm_text(Path("examples/double.sensepin").read_text(encoding="utf-8")), 0, b"42\n", b"")
    _check(
        "overflow",
        run_vm_text(Path("examples/overflow.sensepin").read_text(encoding="utf-8")),
        1,
        b"",
        b"overflow\n",
    )
    _check(
        "depth",
        run_vm_text(
            "phase console\ngauge i64\nfn down(n: i64) -> i64\n  if n == 0\n    return 0\n  end\n  return down(n - 1)\nend\nfn main\n  write down(255) ++ \"\\n\"\nend\n"
        ),
        0,
        b"0\n",
        b"",
    )
    _check(
        "depth-fail",
        run_vm_text(
            "phase console\ngauge i64\nfn down(n: i64) -> i64\n  if n == 0\n    return 0\n  end\n  return down(n - 1)\nend\nfn main\n  write down(256) ++ \"\\n\"\nend\n"
        ),
        1,
        b"",
        b"call depth\n",
    )
    assert i64_mul(0, I64_MIN) == 0
    assert i64_mul(I64_MIN, 1) == I64_MIN
    assert i64_mul(I64_MIN, -1) is None
    assert i64_div(5, -2) == -2
    assert i64_div(-5, 2) == -2
    assert i64_parse(b"-9223372036854775808") == I64_MIN
    assert i64_parse(b"9223372036854775808") is None
    root = Path(__file__).resolve().parents[1]

    def load_measure(folder: str):
        path = root / "probes" / folder / "measure.py"
        spec = importlib.util.spec_from_file_location(f"measure_{folder}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    tally_measure = load_measure("00-tally")
    image = compile_path(Path("examples/tally.sensepin"))
    for case in tally_measure.build_cases():
        args = [b"tally"] + [os.fsencode(arg) for arg in case["args"]]
        got = vm_run(image, args)
        expect = case["expect"]
        _check(case["name"], got, expect["code"], expect["out"], expect["err"])
    nums = root / "fold" / "build" / "fixtures"
    nums.mkdir(parents=True, exist_ok=True)
    sample = nums / "nums.txt"
    sample.write_bytes(b"10\n-2\n3\n")
    for program, expect_out in (
        ("sum.sensepin", b"11\n"),
        ("bounds.sensepin", b"min -2\nmax 10\n"),
    ):
        got = vm_run(compile_path(Path("examples") / program), [program.encode(), os.fsencode(sample)])
        _check(program, got, 0, expect_out, b"")
    grades_measure = load_measure("01-grades")
    grades = compile_path(Path("examples/grades.sensepin"))
    for case in grades_measure.build_cases():
        args = [b"grades"] + [os.fsencode(arg) for arg in case["args"]]
        got = vm_run(grades, args)
        expect = case["expect"]
        _check("grades " + case["name"], got, expect["code"], expect["out"], expect["err"])
    shelf_measure = load_measure("02-shelf")
    shelf = compile_path(Path("examples/shelf.sensepin"))
    for case in shelf_measure.build_cases():
        args = [b"shelf"] + [os.fsencode(arg) for arg in case["args"]]
        got = vm_run(shelf, args)
        expect = case["expect"]
        _check("shelf " + case["name"], got, expect["code"], expect["out"], expect["err"])
    print("vm passed")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "vm":
        os.chdir(Path(__file__).resolve().parent)
        selftest_vm()
        return
    parser = argparse.ArgumentParser(description="Run a Sensepin program on the Sensepin vessel.")
    parser.add_argument("source")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--exe", dest="exe")
    parsed = parser.parse_args()
    source = Path(parsed.source)
    if parsed.exe:
        from machine import write_program

        write_program(source, Path(parsed.exe))
        return
    image = compile_path(source)
    code, out, err = vm_run(image, [b"sensepin"] + [os.fsencode(arg) for arg in parsed.args])
    sys.stdout.buffer.write(out)
    sys.stderr.buffer.write(err)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
