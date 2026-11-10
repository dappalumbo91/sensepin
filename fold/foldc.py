"""Sensepin compiler. The contract is SPEC.md. Python is the factory. C is the vessel.

The public name is Sensepin. This file stays foldc.py. Sources use .sensepin.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

I64_MIN = -9223372036854775808
I64_MAX = 9223372036854775807
SOURCE_LIMIT = 1_048_576
IDENT_LIMIT = 64
KEYWORDS = {
    "phase",
    "gauge",
    "fn",
    "end",
    "if",
    "else",
    "for",
    "in",
    "let",
    "set",
    "write",
    "fail",
    "return",
    "reason",
    "while",
    "struct",
    "use",
}
RESERVED = KEYWORDS | {
    "argc",
    "arg",
    "open",
    "lines",
    "i64",
    "bytes",
    "f64",
    "list",
    "map",
    "len",
    "before",
    "after",
    "holds",
    "at",
    "push",
    "get",
    "put",
    "has",
}
GAUGES = {"args", "file", "lines", "i64", "bytes", "f64", "list", "map"}
BUILTIN = {
    "argc": ("args", [], "i64", False),
    "arg": ("args", ["i64"], "bytes", True),
    "open": ("file", ["bytes", "i64", "bytes", "bytes", "bytes"], "bytes", True),
    "before": ("bytes", ["bytes", "bytes"], "bytes", True),
    "after": ("bytes", ["bytes", "bytes"], "bytes", True),
    "holds": ("bytes", ["bytes", "bytes"], "i64", True),
    "byte": ("bytes", ["i64"], "bytes", True),
    "set_byte": ("bytes", ["bytes", "i64", "i64"], "bytes", True),
    "save": ("file", ["bytes", "bytes"], "i64", True),
}
PRIMITIVES = {"i64", "bytes", "f64"}


class FoldError(Exception):
    pass


@dataclass
class Tok:
    kind: str
    text: str
    line: int


@dataclass
class IntLit:
    value: int
    line: int


@dataclass
class FloatLit:
    value: float
    line: int


@dataclass
class StrLit:
    value: bytes
    line: int


@dataclass
class Name:
    name: str
    line: int


@dataclass
class Field:
    recv: object
    field: str
    line: int


@dataclass
class Call:
    name: str
    args: list
    line: int


@dataclass
class Fail:
    expr: object
    line: int


@dataclass
class Unary:
    op: str
    expr: object
    line: int


@dataclass
class Binary:
    op: str
    left: object
    right: object
    line: int


@dataclass
class Else:
    left: object
    right: object
    line: int


@dataclass
class Let:
    name: str
    expr: object
    line: int
    ann: str | None = None


@dataclass
class Set:
    name: str
    expr: object
    line: int


@dataclass
class Write:
    expr: object
    line: int


@dataclass
class Return:
    expr: object
    line: int


@dataclass
class If:
    cond: object
    then: list
    els: list | None
    line: int


@dataclass
class For:
    name: str
    expr: object
    body: list
    line: int


@dataclass
class While:
    cond: object
    body: list
    line: int


@dataclass
class Param:
    name: str
    typ: str
    line: int


@dataclass
class Fn:
    name: str
    params: list
    ret: str | None
    body: list
    line: int
    cname: str = ""
    param_c: list = field(default_factory=list)


@dataclass
class StructField:
    name: str
    typ: str
    line: int


@dataclass
class Struct:
    name: str
    fields: list
    line: int


@dataclass
class Use:
    path: str
    line: int


@dataclass
class Program:
    gauges: list[str]
    structs: list
    fns: list
    uses: list
    line: int


def fail(line: int, message: str) -> None:
    raise FoldError(f"line {line}: {message}")


def ident_start(ch: str) -> bool:
    return ch == "_" or "A" <= ch <= "Z" or "a" <= ch <= "z"


def ident_cont(ch: str) -> bool:
    return ident_start(ch) or "0" <= ch <= "9"


def source_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if len(data) > SOURCE_LIMIT:
        raise FoldError("source is too large")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FoldError("source is not utf-8") from exc


def lex_line(text: str, line: int) -> list[Tok]:
    out: list[Tok] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in " \t\r":
            i += 1
            continue
        if ch == "#":
            break
        if ch == '"':
            i += 1
            raw = bytearray()
            while i < len(text) and text[i] != '"':
                if text[i] == "\\":
                    if i + 1 >= len(text):
                        fail(line, "unterminated escape")
                    nxt = text[i + 1]
                    if nxt == "n":
                        raw.append(10)
                    elif nxt == "\\":
                        raw.append(ord("\\"))
                    elif nxt == '"':
                        raw.append(ord('"'))
                    else:
                        fail(line, f"unknown escape \\{nxt}")
                    i += 2
                    continue
                raw.extend(text[i].encode("utf-8"))
                i += 1
            if i >= len(text) or text[i] != '"':
                fail(line, "unterminated string")
            i += 1
            out.append(Tok("string", raw.decode("utf-8"), line))
            out[-1].raw = bytes(raw)  # type: ignore[attr-defined]
            continue
        if ch.isdigit():
            start = i
            while i < len(text) and text[i].isdigit():
                i += 1
            if i + 1 < len(text) and text[i] == "." and text[i + 1].isdigit():
                i += 1
                while i < len(text) and text[i].isdigit():
                    i += 1
                out.append(Tok("float", text[start:i], line))
                continue
            out.append(Tok("number", text[start:i], line))
            continue
        if ident_start(ch):
            start = i
            while i < len(text) and ident_cont(text[i]):
                i += 1
            word = text[start:i]
            if len(word) > IDENT_LIMIT:
                fail(line, "identifier is too long")
            out.append(Tok(word if word in KEYWORDS else "ident", word, line))
            continue
        two = text[i : i + 2]
        if two in {"->", "++", "==", "!=", "<=", ">="}:
            out.append(Tok(two, two, line))
            i += 2
            continue
        if ch in "()=+-<>!,.:/*":
            out.append(Tok(ch, ch, line))
            i += 1
            continue
        fail(line, f"unexpected character {ch!r}")
    return out


class ExprParser:
    def __init__(self, tokens: list[Tok], line: int):
        self.tokens = tokens
        self.line = line
        self.i = 0

    def peek(self) -> Tok | None:
        if self.i >= len(self.tokens):
            return None
        return self.tokens[self.i]

    def take(self) -> Tok:
        tok = self.peek()
        if tok is None:
            fail(self.line, "unexpected end of line")
        self.i += 1
        return tok

    def match(self, kind: str) -> bool:
        tok = self.peek()
        if tok is not None and tok.kind == kind:
            self.i += 1
            return True
        return False

    def parse(self) -> object:
        expr = self.expr()
        if self.peek() is not None:
            fail(self.line, f"unexpected {self.peek().text}")
        return expr

    def expr(self) -> object:
        left = self.concat()
        if self.match("else"):
            return Else(left, self.expr(), self.line)
        return left

    def concat(self) -> object:
        left = self.cmp()
        while self.match("++"):
            left = Binary("++", left, self.cmp(), self.line)
        return left

    def cmp(self) -> object:
        left = self.sum()
        tok = self.peek()
        if tok is not None and tok.kind in {"==", "!=", "<", ">", "<=", ">="}:
            self.i += 1
            return Binary(tok.kind, left, self.sum(), self.line)
        return left

    def sum(self) -> object:
        left = self.product()
        while self.peek() is not None and self.peek().kind in {"+", "-"}:
            op = self.take().kind
            left = Binary(op, left, self.product(), self.line)
        return left

    def product(self) -> object:
        left = self.unary()
        while self.peek() is not None and self.peek().kind in {"*", "/"}:
            op = self.take().kind
            left = Binary(op, left, self.unary(), self.line)
        return left

    def unary(self) -> object:
        if self.match("-"):
            tok = self.peek()
            if tok is not None and tok.kind == "number":
                value = int(tok.text)
                if value == I64_MAX + 1:
                    self.i += 1
                    return IntLit(I64_MIN, self.line)
                if value > I64_MAX:
                    fail(self.line, "integer does not fit in i64")
            return Unary("-", self.unary(), self.line)
        return self.atom()

    def atom(self) -> object:
        return self.postfix(self.primary())

    def postfix(self, expr: object) -> object:
        while self.match("."):
            field = self.take()
            if field.kind != "ident":
                fail(self.line, "expected a field name")
            expr = Field(expr, field.text, self.line)
        return expr

    def arguments(self) -> list:
        args = []
        if self.match(")"):
            return args
        while True:
            args.append(self.expr())
            if self.match(")"):
                return args
            if not self.match(","):
                fail(self.line, "expected , or )")

    def primary(self) -> object:
        tok = self.take()
        if tok.kind == "number":
            value = int(tok.text)
            if value > I64_MAX:
                fail(tok.line, "integer does not fit in i64")
            return IntLit(value, tok.line)
        if tok.kind == "float":
            value = float(tok.text)
            if value != value or value in {float("inf"), float("-inf")}:
                fail(tok.line, "float does not fit in f64")
            return FloatLit(value, tok.line)
        if tok.kind == "string":
            return StrLit(tok.raw, tok.line)  # type: ignore[attr-defined]
        if tok.kind == "fail":
            return Fail(self.concat(), tok.line)
        if tok.kind == "reason":
            return Name("reason", tok.line)
        if tok.kind == "(":
            inner = self.expr()
            if not self.match(")"):
                fail(self.line, "expected )")
            return inner
        if tok.kind == "list":
            if not self.match("("):
                fail(tok.line, "expected (")
            return Call("list", self.arguments(), tok.line)
        if tok.kind == "ident":
            if self.match("("):
                return Call(tok.text, self.arguments(), tok.line)
            return Name(tok.text, tok.line)
        fail(tok.line, f"unexpected {tok.text}")
        raise AssertionError


def parse_type(parser: ExprParser) -> str:
    tok = parser.take()
    if tok.kind == "ident" and tok.text == "list":
        return "list " + parse_type(parser)
    if tok.kind == "ident" and tok.text == "map":
        key = parse_type(parser)
        val = parse_type(parser)
        return f"map {key} {val}"
    if tok.kind == "ident":
        return tok.text
    fail(tok.line, "expected a type")
    raise AssertionError


class Parser:
    def __init__(self, lines: list[tuple[int, list[Tok]]]):
        self.lines = lines
        self.i = 0

    def peek(self) -> tuple[int, list[Tok]] | None:
        while self.i < len(self.lines) and not self.lines[self.i][1]:
            self.i += 1
        if self.i >= len(self.lines):
            return None
        return self.lines[self.i]

    def take(self) -> tuple[int, list[Tok]]:
        row = self.peek()
        if row is None:
            fail(self.lines[-1][0] if self.lines else 1, "unexpected end of file")
        self.i += 1
        return row

    def parse(self, require_main: bool = True) -> Program:
        row = self.peek()
        if row is None or row[1][0].kind != "phase":
            fail(row[0] if row else 1, "expected phase console")
        _, tokens = self.take()
        if len(tokens) != 2 or tokens[1].text != "console":
            fail(tokens[0].line, "v0 phase is console")
        gauges: list[str] = []
        uses: list[Use] = []
        structs: list[Struct] = []
        fns: list[Fn] = []
        while self.peek() is not None:
            kind = self.peek()[1][0].kind
            if kind == "gauge":
                _, tokens = self.take()
                if len(tokens) != 2 or tokens[1].kind != "ident":
                    fail(tokens[0].line, "expected a gauge name")
                name = tokens[1].text
                if name not in GAUGES:
                    fail(tokens[1].line, f"unknown gauge {name}")
                if name in gauges:
                    fail(tokens[1].line, f"gauge {name} is named twice")
                gauges.append(name)
                continue
            if kind == "use":
                uses.append(self.parse_use())
                continue
            if kind == "struct":
                structs.append(self.parse_struct())
                continue
            if kind == "fn":
                fns.append(self.parse_fn())
                continue
            fail(self.peek()[0], "expected a declaration")
        if require_main and not any(fn.name == "main" for fn in fns):
            fail(1, "missing fn main")
        return Program(gauges, structs, fns, uses, 1)

    def parse_use(self) -> Use:
        line, tokens = self.take()
        if len(tokens) != 2 or tokens[1].kind != "string":
            fail(line, "expected use \"path\"")
        return Use(tokens[1].text, line)

    def parse_struct(self) -> Struct:
        line, tokens = self.take()
        if len(tokens) != 2 or tokens[1].kind != "ident":
            fail(line, "expected a struct name")
        name = tokens[1].text
        if name in RESERVED or name in {"line", "bottom"}:
            fail(line, f"{name} is reserved")
        fields: list[StructField] = []
        while True:
            row = self.peek()
            if row is None:
                fail(line, "expected end")
            field_line, field_tokens = row
            if len(field_tokens) == 1 and field_tokens[0].kind == "end":
                self.take()
                break
            parser = ExprParser(field_tokens, field_line)
            ident = parser.take()
            if ident.kind != "ident" or ident.text in RESERVED:
                fail(field_line, "expected a field name")
            if not parser.match(":"):
                fail(field_line, "expected :")
            typ = parse_type(parser)
            if parser.peek() is not None:
                fail(field_line, f"unexpected {parser.peek().text}")
            self.take()
            fields.append(StructField(ident.text, typ, field_line))
        if not fields:
            fail(line, "struct needs a field")
        return Struct(name, fields, line)

    def parse_fn(self) -> Fn:
        line, tokens = self.take()
        if tokens[0].kind != "fn":
            fail(line, "expected fn")
        if len(tokens) < 2 or tokens[1].kind != "ident":
            fail(line, "expected a function name")
        name = tokens[1].text
        if name in RESERVED:
            fail(line, f"{name} is reserved")
        params: list[Param] = []
        ret = None
        if name != "main":
            parser = ExprParser(tokens[2:], line)
            if not parser.match("("):
                fail(line, "expected (")
            if not parser.match(")"):
                while True:
                    ident = parser.take()
                    if ident.kind != "ident" or ident.text in RESERVED:
                        fail(line, "expected a parameter name")
                    if not parser.match(":"):
                        fail(line, "expected :")
                    params.append(Param(ident.text, parse_type(parser), line))
                    if parser.match(")"):
                        break
                    if not parser.match(","):
                        fail(line, "expected , or )")
            if not parser.match("->"):
                fail(line, "expected ->")
            ret = parse_type(parser)
            if parser.peek() is not None:
                fail(line, f"unexpected {parser.peek().text}")
        elif len(tokens) != 2:
            fail(line, "main takes no parameters")
        body, closed = self.parse_block(False)
        if not closed:
            fail(line, "expected end")
        return Fn(name, params, ret, body, line)

    def parse_block(self, stop_else: bool) -> tuple[list, bool]:
        stmts = []
        while True:
            row = self.peek()
            if row is None:
                fail(self.lines[-1][0] if self.lines else 1, "expected end")
            line, tokens = row
            if len(tokens) == 1 and tokens[0].kind == "end":
                self.take()
                return stmts, True
            if stop_else and len(tokens) == 1 and tokens[0].kind == "else":
                return stmts, False
            stmts.append(self.parse_stmt())

    def parse_stmt(self) -> object:
        line, tokens = self.take()
        head = tokens[0].kind
        if head == "let":
            if len(tokens) < 4 or tokens[1].kind != "ident":
                fail(line, "expected let name = expr")
            if tokens[1].text in RESERVED:
                fail(line, f"{tokens[1].text} is reserved")
            parser = ExprParser(tokens[2:], line)
            ann = None
            if parser.match(":"):
                ann = parse_type(parser)
            if not parser.match("="):
                fail(line, "expected let name = expr")
            return Let(tokens[1].text, parser.parse(), line, ann)
        if head == "set":
            if len(tokens) < 4 or tokens[1].kind != "ident" or tokens[2].kind != "=":
                fail(line, "expected set name = expr")
            return Set(tokens[1].text, ExprParser(tokens[3:], line).parse(), line)
        if head == "write":
            return Write(ExprParser(tokens[1:], line).parse(), line)
        if head == "fail":
            return Fail(ExprParser(tokens[1:], line).parse(), line)
        if head == "return":
            return Return(ExprParser(tokens[1:], line).parse(), line)
        if head == "if":
            cond = ExprParser(tokens[1:], line).parse()
            then, closed = self.parse_block(True)
            els = None
            if not closed:
                else_line, else_tokens = self.take()
                if len(else_tokens) != 1:
                    fail(else_line, "expected else")
                els, closed = self.parse_block(False)
                if not closed:
                    fail(line, "expected end")
            return If(cond, then, els, line)
        if head == "while":
            cond = ExprParser(tokens[1:], line).parse()
            body, closed = self.parse_block(False)
            if not closed:
                fail(line, "expected end")
            return While(cond, body, line)
        if head == "for":
            if len(tokens) < 4 or tokens[1].kind != "ident" or tokens[2].kind != "in":
                fail(line, "expected for name in lines(...)")
            if tokens[1].text in RESERVED:
                fail(line, f"{tokens[1].text} is reserved")
            expr = ExprParser(tokens[3:], line).parse()
            body, closed = self.parse_block(False)
            if not closed:
                fail(line, "expected end")
            return For(tokens[1].text, expr, body, line)
        fail(line, "expected a statement")
        raise AssertionError


def list_elem(typ: str) -> str | None:
    if typ.startswith("list "):
        return typ[5:]
    return None


def _take_type(words: list[str], index: int) -> tuple[str, int]:
    if index >= len(words):
        return "", index
    word = words[index]
    if word == "list":
        elem, nxt = _take_type(words, index + 1)
        return f"list {elem}", nxt
    if word == "map":
        key, after_key = _take_type(words, index + 1)
        val, after_val = _take_type(words, after_key)
        return f"map {key} {val}", after_val
    return word, index + 1


def map_pair(typ: str) -> tuple[str, str] | None:
    if not typ.startswith("map "):
        return None
    words = typ.split()
    key, after_key = _take_type(words, 1)
    val, after_val = _take_type(words, after_key)
    if not key or not val or after_val != len(words):
        return None
    return key, val


class Checker:
    def __init__(self, program: Program):
        self.program = program
        self.fns = {fn.name: fn for fn in program.fns}
        self.structs: dict[str, Struct] = {}
        self.used: set[str] = set()
        self.scopes: list[dict[str, tuple[str, bool]]] = []
        self.reason = False
        self.current: Fn | None = None
        self.types: dict[int, str] = {}

    def note(self, gauge: str, line: int) -> None:
        if gauge not in self.program.gauges:
            fail(line, f"gauge {gauge} is not named")
        self.used.add(gauge)

    def check(self) -> dict[int, str]:
        seen_fn: set[str] = set()
        for fn in self.program.fns:
            if fn.name in seen_fn:
                fail(fn.line, "duplicate function name")
            seen_fn.add(fn.name)
        for struct in self.program.structs:
            if struct.name in self.structs or struct.name in seen_fn:
                fail(struct.line, "duplicate struct name")
            seen_fields: set[str] = set()
            for item in struct.fields:
                if item.name in seen_fields:
                    fail(item.line, f"duplicate field {item.name}")
                seen_fields.add(item.name)
            self.structs[struct.name] = struct
        self.struct_cycles()
        for struct in self.program.structs:
            for item in struct.fields:
                self.check_type(item.typ, item.line)
        for fn in self.program.fns:
            seen = set()
            for param in fn.params:
                if param.name in seen:
                    fail(param.line, f"duplicate parameter {param.name}")
                seen.add(param.name)
                self.check_type(param.typ, param.line)
            if fn.ret is not None:
                self.check_type(fn.ret, fn.line)
            if fn.name != "main" and (not fn.body or not isinstance(fn.body[-1], (Return, Fail))):
                fail(fn.line, "function must end with return")
        for fn in self.program.fns:
            self.current = fn
            self.scopes = [{}]
            for param in fn.params:
                self.scopes[-1][param.name] = (param.typ, False)
            self.stmts(fn.body)
        unused = [name for name in self.program.gauges if name not in self.used]
        if unused:
            fail(1, f"gauge {unused[0]} is unused")
        return self.types

    def struct_cycles(self) -> None:
        visiting: set[str] = set()
        done: set[str] = set()

        def walk(name: str, line: int) -> None:
            if name in done:
                return
            if name in visiting:
                fail(line, "struct cycle")
            visiting.add(name)
            for item in self.structs[name].fields:
                if item.typ in self.structs:
                    walk(item.typ, item.line)
            visiting.remove(name)
            done.add(name)

        for name, struct in self.structs.items():
            walk(name, struct.line)

    def check_type(self, typ: str, line: int) -> None:
        if typ in PRIMITIVES:
            return
        elem = list_elem(typ)
        if elem is not None:
            self.check_type(elem, line)
            return
        pair = map_pair(typ)
        if pair is not None:
            key, val = pair
            if key not in {"i64", "f64", "bytes"}:
                fail(line, "map key needs i64, f64, or bytes")
            self.check_type(val, line)
            return
        if typ in self.structs:
            return
        fail(line, f"unknown type {typ}")

    def stmts(self, rows: list) -> None:
        for row in rows:
            self.stmt(row)

    def stmt(self, row: object) -> None:
        if isinstance(row, Let):
            if row.name in self.scopes[-1]:
                fail(row.line, f"{row.name} is already bound in this block")
            if row.ann is not None:
                self.check_type(row.ann, row.line)
            typ = self.expr(row.expr, row.ann)
            if row.ann is not None and typ != row.ann:
                fail(row.line, f"{row.name} needs {row.ann}")
            if typ in {"bottom", "line"}:
                fail(row.line, "let needs an i64 or bytes value")
            self.scopes[-1][row.name] = (typ, True)
            return
        if isinstance(row, Set):
            found = self.lookup(row.name, row.line)
            if not found[1]:
                fail(row.line, f"{row.name} cannot be assigned")
            typ = self.expr(row.expr, found[0])
            if typ != found[0]:
                fail(row.line, f"{row.name} is {found[0]}")
            return
        if isinstance(row, Write):
            typ = self.expr(row.expr)
            if typ not in {"bytes", "i64", "f64"}:
                fail(row.line, "write needs bytes, i64, or f64")
            if typ == "i64":
                self.note("i64", row.line)
            if typ == "f64":
                self.note("f64", row.line)
            return
        if isinstance(row, Fail):
            typ = self.expr(row.expr)
            if typ not in {"bytes", "i64", "f64"}:
                fail(row.line, "fail needs bytes, i64, or f64")
            if typ == "i64":
                self.note("i64", row.line)
            if typ == "f64":
                self.note("f64", row.line)
            self.types[id(row)] = "bottom"
            return
        if isinstance(row, Return):
            if self.current is None or self.current.name == "main":
                fail(row.line, "main does not return a value")
            typ = self.expr(row.expr, self.current.ret)
            if typ != self.current.ret:
                fail(row.line, f"return needs {self.current.ret}")
            return
        if isinstance(row, If):
            typ = self.expr(row.cond)
            if typ != "i64":
                fail(row.line, "if needs an i64")
            self.scopes.append({})
            self.stmts(row.then)
            self.scopes.pop()
            if row.els is not None:
                self.scopes.append({})
                self.stmts(row.els)
                self.scopes.pop()
            return
        if isinstance(row, While):
            typ = self.expr(row.cond)
            if typ != "i64":
                fail(row.line, "while needs an i64")
            self.scopes.append({})
            self.stmts(row.body)
            self.scopes.pop()
            return
        if isinstance(row, For):
            walked = self.for_binding(row)
            self.scopes.append({row.name: walked})
            self.stmts(row.body)
            self.scopes.pop()
            return
        fail(1, "unknown statement")

    def for_binding(self, row: For) -> tuple[str, bool]:
        call = row.expr
        if isinstance(call, Call) and call.name in {"lines", "bytes"} and len(call.args) == 1:
            arg = self.expr(call.args[0])
            if arg != "bytes":
                fail(row.line, f"{call.name} needs bytes")
            if call.name == "lines":
                self.note("lines", row.line)
                return ("line", False)
            self.note("bytes", row.line)
            return ("i64", False)
        typ = self.expr(row.expr)
        pair = map_pair(typ)
        if pair is not None:
            self.note("map", row.line)
            return (pair[0], False)
        elem = list_elem(typ)
        if elem is None:
            fail(row.line, "for walks lines(bytes), bytes(bytes), a list, or a map")
        self.note("list", row.line)
        return (elem, False)

    def lookup(self, name: str, line: int) -> tuple[str, bool]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        fail(line, f"unknown name {name}")
        raise AssertionError

    def expr(self, expr: object, expect: str | None = None) -> str:
        typ = self.expr_type(expr, expect)
        self.types[id(expr)] = typ
        return typ

    def expr_type(self, expr: object, expect: str | None = None) -> str:
        if isinstance(expr, IntLit):
            self.note("i64", expr.line)
            return "i64"
        if isinstance(expr, FloatLit):
            self.note("f64", expr.line)
            return "f64"
        if isinstance(expr, StrLit):
            return "bytes"
        if isinstance(expr, Name):
            if expr.name == "reason":
                if not self.reason:
                    fail(expr.line, "reason is only in scope after else")
                return "bytes"
            return self.lookup(expr.name, expr.line)[0]
        if isinstance(expr, Field):
            owner = self.expr(expr.recv)
            if owner == "line":
                if expr.field == "text":
                    return "bytes"
                if expr.field == "n":
                    self.note("i64", expr.line)
                    return "i64"
                fail(expr.line, f"unknown field {expr.field}")
            struct = self.structs.get(owner)
            if struct is None:
                fail(expr.line, "value has no fields")
            for item in struct.fields:
                if item.name == expr.field:
                    return item.typ
            fail(expr.line, f"unknown field {expr.field}")
        if isinstance(expr, Call):
            return self.call_type(expr, expect)
        if isinstance(expr, Fail):
            typ = self.expr(expr.expr)
            if typ not in {"bytes", "i64", "f64"}:
                fail(expr.line, "fail needs bytes, i64, or f64")
            if typ == "i64":
                self.note("i64", expr.line)
            if typ == "f64":
                self.note("f64", expr.line)
            return "bottom"
        if isinstance(expr, Unary):
            inner = self.expr(expr.expr)
            if inner == "f64":
                self.note("f64", expr.line)
                return "f64"
            if inner != "i64":
                fail(expr.line, "unary - needs i64 or f64")
            self.note("i64", expr.line)
            return "i64"
        if isinstance(expr, Binary):
            return self.binary_type(expr)
        if isinstance(expr, Else):
            left = self.expr(expr.left, expect)
            previous = self.reason
            self.reason = True
            right_expect = expect
            if right_expect is None and left not in {"bottom", "line"}:
                right_expect = left
            right = self.expr(expr.right, right_expect)
            self.reason = previous
            if right == "bottom":
                if left in {"bottom", "line"}:
                    fail(expr.line, "else needs a value")
                return left
            if left == "bottom":
                return right
            if left != right:
                fail(expr.line, "else branches have different types")
            return left
        fail(1, "unknown expression")
        raise AssertionError

    def binary_type(self, expr: Binary) -> str:
        left = self.expr(expr.left)
        right = self.expr(expr.right)
        if expr.op == "++":
            if left not in {"bytes", "i64", "f64"} or right not in {"bytes", "i64", "f64"}:
                fail(expr.line, "++ needs bytes, i64, or f64")
            if left == "i64" or right == "i64":
                self.note("i64", expr.line)
            if left == "f64" or right == "f64":
                self.note("f64", expr.line)
            return "bytes"
        if expr.op in {"+", "-", "*", "/"}:
            if left == "f64" and right == "f64":
                self.note("f64", expr.line)
                return "f64"
            if left == "i64" and right == "i64":
                self.note("i64", expr.line)
                return "i64"
            fail(expr.line, f"{expr.op} needs i64 or f64")
        if left == "f64" and right == "f64":
            self.note("f64", expr.line)
            return "i64"
        if left != "i64" or right != "i64":
            fail(expr.line, f"{expr.op} needs i64 or f64")
        self.note("i64", expr.line)
        return "i64"

    def call_type(self, expr: Call, expect: str | None) -> str:
        if expr.name == "lines":
            fail(expr.line, "lines() is only legal in for")
        if expr.name == "bytes":
            fail(expr.line, "bytes() is only legal in for")
        if expr.name == "len":
            return self.len_type(expr)
        if expr.name == "at":
            return self.at_type(expr)
        if expr.name == "push":
            return self.push_type(expr)
        if expr.name == "get":
            return self.get_type(expr)
        if expr.name == "put":
            return self.put_type(expr)
        if expr.name == "has":
            return self.has_type(expr)
        if expr.name == "list":
            return self.list_type(expr, expect)
        if expr.name == "map":
            return self.map_type(expr, expect)
        if expr.name == "i64":
            return self.i64_type(expr)
        if expr.name == "f64":
            return self.f64_type(expr)
        if expr.name in BUILTIN:
            gauge, params, ret, _fails = BUILTIN[expr.name]
            self.note(gauge, expr.line)
            if len(expr.args) != len(params):
                fail(expr.line, f"{expr.name} expects {len(params)} arguments")
            for arg, want in zip(expr.args, params):
                got = self.expr(arg, want)
                if got != want:
                    fail(expr.line, f"{expr.name} expects {want}")
            return ret
        struct = self.structs.get(expr.name)
        if struct is not None:
            if len(expr.args) != len(struct.fields):
                fail(expr.line, f"{expr.name} expects {len(struct.fields)} arguments")
            for arg, item in zip(expr.args, struct.fields):
                got = self.expr(arg, item.typ)
                if got != item.typ:
                    fail(expr.line, f"{expr.name} expects {item.typ}")
            return struct.name
        fn = self.fns.get(expr.name)
        if fn is None or fn.name == "main":
            fail(expr.line, f"unknown function {expr.name}")
        if len(expr.args) != len(fn.params):
            fail(expr.line, f"{expr.name} expects {len(fn.params)} arguments")
        for arg, param in zip(expr.args, fn.params):
            got = self.expr(arg, param.typ)
            if got != param.typ:
                fail(expr.line, f"{expr.name} expects {param.typ}")
        return fn.ret or "bottom"

    def len_type(self, expr: Call) -> str:
        if len(expr.args) != 1:
            fail(expr.line, "len expects 1 arguments")
        got = self.expr(expr.args[0])
        if got == "bytes":
            self.note("bytes", expr.line)
            return "i64"
        if list_elem(got) is not None:
            self.note("list", expr.line)
            return "i64"
        if map_pair(got) is not None:
            self.note("map", expr.line)
            return "i64"
        fail(expr.line, "len needs bytes, a list, or a map")
        raise AssertionError

    def at_type(self, expr: Call) -> str:
        if len(expr.args) != 2:
            fail(expr.line, "at expects 2 arguments")
        got = self.expr(expr.args[0])
        idx = self.expr(expr.args[1])
        if idx != "i64":
            fail(expr.line, "at expects i64")
        if got == "bytes":
            self.note("bytes", expr.line)
            return "i64"
        elem = list_elem(got)
        if elem is None:
            fail(expr.line, "at needs bytes or a list")
        self.note("list", expr.line)
        return elem or "bottom"

    def push_type(self, expr: Call) -> str:
        if len(expr.args) != 2:
            fail(expr.line, "push expects 2 arguments")
        got = self.expr(expr.args[0])
        elem = list_elem(got)
        if elem is None:
            fail(expr.line, "push needs a list")
        value = self.expr(expr.args[1], elem)
        if value != elem:
            fail(expr.line, "push expects the list element")
        self.note("list", expr.line)
        return got

    def get_type(self, expr: Call) -> str:
        if len(expr.args) != 2:
            fail(expr.line, "get expects 2 arguments")
        got = self.expr(expr.args[0])
        pair = map_pair(got)
        if pair is None:
            fail(expr.line, "get needs a map")
        key, val = pair
        found = self.expr(expr.args[1], key)
        if found != key:
            fail(expr.line, "get expects the map key")
        self.note("map", expr.line)
        return val

    def put_type(self, expr: Call) -> str:
        if len(expr.args) != 3:
            fail(expr.line, "put expects 3 arguments")
        got = self.expr(expr.args[0])
        pair = map_pair(got)
        if pair is None:
            fail(expr.line, "put needs a map")
        key, val = pair
        found = self.expr(expr.args[1], key)
        if found != key:
            fail(expr.line, "put expects the map key")
        stored = self.expr(expr.args[2], val)
        if stored != val:
            fail(expr.line, "put expects the map value")
        self.note("map", expr.line)
        return got

    def has_type(self, expr: Call) -> str:
        if len(expr.args) != 2:
            fail(expr.line, "has expects 2 arguments")
        got = self.expr(expr.args[0])
        pair = map_pair(got)
        if pair is None:
            fail(expr.line, "has needs a map")
        key, _val = pair
        found = self.expr(expr.args[1], key)
        if found != key:
            fail(expr.line, "has expects the map key")
        self.note("map", expr.line)
        return "i64"

    def map_type(self, expr: Call, expect: str | None) -> str:
        self.note("map", expr.line)
        if len(expr.args) % 2 != 0:
            fail(expr.line, "map needs pairs")
        if not expr.args:
            if expect is None or map_pair(expect) is None:
                fail(expr.line, "map() needs a type")
            return expect or "bottom"
        exp_pair = map_pair(expect) if expect is not None else None
        key_expect = exp_pair[0] if exp_pair is not None else None
        val_expect = exp_pair[1] if exp_pair is not None else None
        key_t = None
        val_t = None
        index = 0
        while index < len(expr.args):
            key = self.expr(expr.args[index], key_expect)
            val = self.expr(expr.args[index + 1], val_expect)
            if key in {"bottom", "line"} or val in {"bottom", "line"}:
                fail(expr.line, "map needs a value")
            if key_t is None:
                key_t = key
                val_t = val
                if key_t not in {"i64", "f64", "bytes"}:
                    fail(expr.line, "map key needs i64, f64, or bytes")
                if key_expect is None:
                    key_expect = key_t
                if val_expect is None:
                    val_expect = val_t
            elif key != key_t or val != val_t:
                fail(expr.line, "map pairs have different types")
            index += 2
        got = f"map {key_t} {val_t}"
        if expect is not None and expect != got:
            fail(expr.line, f"map needs {expect}")
        return got

    def list_type(self, expr: Call, expect: str | None) -> str:
        self.note("list", expr.line)
        if not expr.args:
            if expect is None or list_elem(expect) is None:
                fail(expr.line, "list() needs a type")
            return expect or "bottom"
        elem_expect = list_elem(expect) if expect is not None else None
        elem = None
        for arg in expr.args:
            got = self.expr(arg, elem_expect)
            if got in {"bottom", "line"}:
                fail(expr.line, "list needs a value")
            if elem is None:
                elem = got
                if elem_expect is None:
                    elem_expect = got
            elif got != elem:
                fail(expr.line, "list elements have different types")
        if expect is not None and expect != "list " + (elem or ""):
            fail(expr.line, f"list needs {expect}")
        return "list " + (elem or "")

    def i64_type(self, expr: Call) -> str:
        if len(expr.args) != 1:
            fail(expr.line, "i64 expects 1 arguments")
        got = self.expr(expr.args[0])
        if got == "bytes":
            self.note("i64", expr.line)
            return "i64"
        if got == "f64":
            self.note("f64", expr.line)
            self.note("i64", expr.line)
            return "i64"
        fail(expr.line, "i64 expects bytes or f64")
        raise AssertionError

    def f64_type(self, expr: Call) -> str:
        if len(expr.args) != 1:
            fail(expr.line, "f64 expects 1 arguments")
        got = self.expr(expr.args[0])
        if got != "i64":
            fail(expr.line, "f64 expects i64")
        self.note("f64", expr.line)
        self.note("i64", expr.line)
        return "f64"


@dataclass
class FailTarget:
    flag: str
    reason: str


class Gen:
    def __init__(self, program: Program, types: dict[int, str]):
        self.program = program
        self.types = types
        self.fns = {fn.name: fn for fn in program.fns}
        self.structs = {struct.name: struct for struct in program.structs}
        self.out: list[str] = []
        self.lits: list[bytes] = []
        self.tmp = 0
        self.scopes: list[dict[str, tuple[str, str, bool]]] = []
        self.reason_stack: list[str] = []
        self.fn: Fn | None = None

    def fresh(self, prefix: str) -> str:
        self.tmp += 1
        return f"{prefix}_{self.tmp}"

    def emit(self, text: str) -> None:
        self.out.append(text)

    def lit(self, data: bytes) -> str:
        if not data:
            return "fold_bytes_empty()"
        idx = len(self.lits)
        self.lits.append(data)
        return f"fold_bytes_view(fold_lit_{idx}, {len(data)})"

    def lookup(self, name: str) -> tuple[str, str, bool]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise FoldError(f"codegen lost {name}")

    def ctype(self, typ: str) -> str:
        if typ == "i64":
            return "int64_t"
        if typ == "f64":
            return "double"
        if typ == "bytes":
            return "FoldBytes"
        if typ == "line":
            return "FoldLine"
        if list_elem(typ) is not None:
            return "FoldList"
        if map_pair(typ) is not None:
            return "FoldMap"
        if typ in self.structs:
            return f"fold_ty_{typ}"
        raise FoldError(f"codegen type {typ}")

    def zero(self, typ: str) -> str:
        if typ == "i64":
            return "0"
        if typ == "f64":
            return "0.0"
        if typ == "bytes":
            return "fold_bytes_empty()"
        if typ == "line":
            return "(FoldLine){0}"
        elem = list_elem(typ)
        if elem is not None:
            return f"fold_list_empty({self.stride_of(elem)})"
        pair = map_pair(typ)
        if pair is not None:
            return f"fold_map_empty({self.stride_of(pair[0])}, {self.stride_of(pair[1])})"
        if typ in self.structs:
            return "{0}"
        raise FoldError(f"codegen zero {typ}")

    def stride_of(self, typ: str) -> str:
        if typ == "i64":
            return "sizeof(int64_t)"
        if typ == "f64":
            return "sizeof(double)"
        if typ == "bytes":
            return "sizeof(FoldBytes)"
        if list_elem(typ) is not None:
            return "sizeof(FoldList)"
        if map_pair(typ) is not None:
            return "sizeof(FoldMap)"
        if typ in self.structs:
            return f"sizeof(fold_ty_{typ})"
        raise FoldError(f"codegen stride {typ}")

    def c_f64(self, value: float) -> str:
        bits = struct.unpack("<Q", struct.pack("<d", float(value)))[0]
        return f"fold_f64_bits(0x{bits:016x}ull)"

    def c_i64(self, value: int) -> str:
        if value == I64_MIN:
            return "INT64_MIN"
        return f"(int64_t){value}"

    def guard(self, fail: FailTarget | None, body: str) -> None:
        if fail is None:
            self.emit(body)
            return
        self.emit(f"if (!{fail.flag}) {{ {body} }}")

    def gen(self) -> str:
        for fn in self.program.fns:
            fn.cname = "fold_main" if fn.name == "main" else f"fn_{fn.name}"
            fn.param_c = [(f"p_{fn.name}_{param.name}", param.typ) for param in fn.params]
        typedefs = []
        for name in self.ordered_struct_names():
            fields = []
            for item in self.structs[name].fields:
                fields.append(f"    {self.ctype(item.typ)} f_{item.name};")
            body = "\n".join(fields)
            typedefs.append(f"typedef struct fold_ty_{name} {{\n{body}\n}} fold_ty_{name};")
        prototypes = []
        for fn in self.program.fns:
            prototypes.append(self.signature(fn) + ";")
            self.gen_fn(fn)
        bodies = "\n".join(self.out)
        lits = []
        for idx, data in enumerate(self.lits):
            nums = ", ".join(str(byte) for byte in data)
            lits.append(f"static const uint8_t fold_lit_{idx}[] = {{{nums}}};")
        return "\n".join(typedefs + prototypes + lits) + "\n" + bodies

    def ordered_struct_names(self) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()

        def visit(name: str) -> None:
            if name in seen:
                return
            seen.add(name)
            for item in self.structs[name].fields:
                if item.typ in self.structs:
                    visit(item.typ)
            order.append(name)

        for name in self.structs:
            visit(name)
        return order

    def signature(self, fn: Fn) -> str:
        if fn.name == "main":
            return "int fold_main(void)"
        params = ", ".join(f"{self.ctype(typ)} {name}" for name, typ in fn.param_c) or "void"
        return f"FoldValue {fn.cname}({params})"

    def gen_fn(self, fn: Fn) -> None:
        self.fn = fn
        self.scopes = [{}]
        for param, (cname, typ) in zip(fn.params, fn.param_c):
            self.scopes[-1][param.name] = (typ, cname, False)
        self.emit(self.signature(fn) + " {")
        if fn.name != "main":
            self.emit("fold_enter();")
            self.emit("FoldValue fold_ret;")
            self.emit("memset(&fold_ret, 0, sizeof fold_ret);")
            self.emit("fold_ret.reason = fold_bytes_empty();")
        self.gen_stmts(fn.body)
        if fn.name == "main":
            self.emit("return 0;")
        self.emit("}")

    def gen_stmts(self, rows: list) -> None:
        for row in rows:
            self.gen_stmt(row)

    def gen_stmt(self, row: object) -> None:
        if isinstance(row, Let):
            typ = self.types[id(row.expr)]
            cname = self.fresh("v_" + row.name)
            self.scopes[-1][row.name] = (typ, cname, True)
            self.emit(f"{self.ctype(typ)} {cname} = {self.zero(typ)};")
            self.gen_value(row.expr, cname, typ, None)
            return
        if isinstance(row, Set):
            typ, cname, _assign = self.lookup(row.name)
            tmp = self.fresh("set")
            self.emit(f"{self.ctype(typ)} {tmp} = {self.zero(typ)};")
            self.gen_value(row.expr, tmp, typ, None)
            self.emit(f"{cname} = {tmp};")
            return
        if isinstance(row, Write):
            self.gen_io("fold_write", row.expr)
            return
        if isinstance(row, Fail):
            self.gen_fail(row.expr)
            return
        if isinstance(row, Return):
            typ = self.types[id(row.expr)]
            tmp = self.fresh("ret")
            self.emit(f"{self.ctype(typ)} {tmp} = {self.zero(typ)};")
            self.gen_value(row.expr, tmp, typ, None)
            self.store_return(tmp, typ)
            self.emit("fold_leave();")
            self.emit("return fold_ret;")
            return
        if isinstance(row, If):
            cond = self.fresh("cond")
            self.emit(f"int64_t {cond} = 0;")
            self.gen_value(row.cond, cond, "i64", None)
            self.emit(f"if ({cond}) {{")
            self.scopes.append({})
            self.gen_stmts(row.then)
            self.scopes.pop()
            if row.els is not None:
                self.emit("} else {")
                self.scopes.append({})
                self.gen_stmts(row.els)
                self.scopes.pop()
            self.emit("}")
            return
        if isinstance(row, While):
            self.emit("for (;;) {")
            cond = self.fresh("cond")
            self.emit(f"int64_t {cond} = 0;")
            self.gen_value(row.cond, cond, "i64", None)
            self.emit(f"if (!{cond}) {{ break; }}")
            self.scopes.append({})
            self.gen_stmts(row.body)
            self.scopes.pop()
            self.emit("}")
            return
        if isinstance(row, For):
            if not isinstance(row.expr, Call) or row.expr.name not in {"lines", "bytes"}:
                walked = self.types[id(row.expr)]
                if map_pair(walked) is not None:
                    self.gen_for_map(row)
                else:
                    self.gen_for_list(row)
                return
            src = self.fresh("src")
            index = self.fresh("i")
            self.emit(f"FoldBytes {src} = fold_bytes_empty();")
            self.gen_value(row.expr.args[0], src, "bytes", None)
            if row.expr.name == "bytes":
                self.emit(f"for (size_t {index} = 0; {index} < {src}.n; {index}++) {{")
                cname = self.fresh("v_" + row.name)
                self.scopes.append({row.name: ("i64", cname, False)})
                self.emit(f"int64_t {cname} = (int64_t){src}.p[{index}];")
                self.emit(f"(void){cname};")
                self.gen_stmts(row.body)
                self.scopes.pop()
                self.emit("}")
                return
            lines = self.fresh("lines")
            self.emit(f"FoldLines {lines};")
            self.emit(f"fold_lines({src}, &{lines});")
            self.emit(f"for (size_t {index} = 0; {index} < {lines}.count; {index}++) {{")
            cname = self.fresh("v_" + row.name)
            self.scopes.append({row.name: ("line", cname, False)})
            self.emit(f"FoldLine {cname} = {lines}.items[{index}];")
            self.emit(f"(void){cname};")
            self.gen_stmts(row.body)
            self.scopes.pop()
            self.emit("}")
            self.emit(f"fold_lines_free(&{lines});")
            return
        raise FoldError("codegen statement")

    def gen_io(self, fn: str, expr: object) -> None:
        typ = self.types[id(expr)]
        tmp = self.fresh("io")
        if typ == "i64":
            self.emit(f"int64_t {tmp} = 0;")
            self.gen_value(expr, tmp, "i64", None)
            self.emit(f"{fn}(fold_dec({tmp}));")
            return
        if typ == "f64":
            self.emit(f"double {tmp} = 0.0;")
            self.gen_value(expr, tmp, "f64", None)
            self.emit(f"{fn}(fold_dec_f64({tmp}));")
            return
        self.emit(f"FoldBytes {tmp} = fold_bytes_empty();")
        self.gen_value(expr, tmp, "bytes", None)
        self.emit(f"{fn}({tmp});")

    def gen_fail(self, expr: object) -> None:
        typ = self.types[id(expr)]
        tmp = self.fresh("bad")
        if typ == "i64":
            self.emit(f"int64_t {tmp} = 0;")
            self.gen_value(expr, tmp, "i64", None)
            self.unwind(f"fold_dec({tmp})")
            return
        if typ == "f64":
            self.emit(f"double {tmp} = 0.0;")
            self.gen_value(expr, tmp, "f64", None)
            self.unwind(f"fold_dec_f64({tmp})")
            return
        self.emit(f"FoldBytes {tmp} = fold_bytes_empty();")
        self.gen_value(expr, tmp, "bytes", None)
        self.unwind(tmp)

    def unwind(self, reason: str) -> None:
        if self.fn is None or self.fn.name == "main":
            self.emit(f"fold_fail({reason});")
            return
        self.emit(f"fold_ret.failed = 1; fold_ret.reason = {reason}; fold_leave(); return fold_ret;")

    def store_return(self, tmp: str, typ: str) -> None:
        if typ == "i64":
            self.emit(f"fold_ret.i64 = {tmp};")
        elif typ == "f64":
            self.emit(f"fold_ret.f64 = {tmp};")
        elif typ == "bytes":
            self.emit(f"fold_ret.bytes = {tmp};")
        elif list_elem(typ) is not None:
            self.emit(f"fold_ret.list = {tmp};")
        elif map_pair(typ) is not None:
            self.emit(f"fold_ret.map = {tmp};")
        else:
            self.emit(f"fold_ret.obj = fold_box(&{tmp}, sizeof {tmp});")

    def gen_value(self, expr: object, dest: str, typ: str, fail: FailTarget | None) -> None:
        if isinstance(expr, IntLit):
            self.guard(fail, f"{dest} = {self.c_i64(expr.value)};")
            return
        if isinstance(expr, FloatLit):
            self.guard(fail, f"{dest} = {self.c_f64(expr.value)};")
            return
        if isinstance(expr, StrLit):
            self.guard(fail, f"{dest} = {self.lit(expr.value)};")
            return
        if isinstance(expr, Name):
            if expr.name == "reason":
                self.guard(fail, f"{dest} = {self.reason_stack[-1]};")
                return
            _typ, cname, _assign = self.lookup(expr.name)
            self.guard(fail, f"{dest} = {cname};")
            return
        if isinstance(expr, Field):
            recv_typ = self.types[id(expr.recv)]
            tmp = self.fresh("obj")
            self.emit(f"{self.ctype(recv_typ)} {tmp} = {self.zero(recv_typ)};")
            self.gen_value(expr.recv, tmp, recv_typ, fail)
            member = expr.field if recv_typ == "line" else f"f_{expr.field}"
            self.guard(fail, f"{dest} = {tmp}.{member};")
            return
        if isinstance(expr, Else):
            flag = self.fresh("failed")
            reason = self.fresh("reason")
            tmp = self.fresh("else")
            self.emit(
                f"{{ int {flag} = 0; FoldBytes {reason} = fold_bytes_empty(); "
                f"{self.ctype(typ)} {tmp} = {self.zero(typ)};"
            )
            self.gen_value(expr.left, tmp, typ, FailTarget(flag, reason))
            self.emit(f"if ({flag}) {{")
            self.emit(f"(void){reason};")
            self.reason_stack.append(reason)
            self.gen_value(expr.right, dest, self.types[id(expr.right)] if self.types[id(expr.right)] != "bottom" else typ, fail)
            self.reason_stack.pop()
            self.emit(f"}} else {{ {dest} = {tmp}; }} }}")
            return
        if isinstance(expr, Fail):
            self.gen_fail(expr.expr)
            return
        if isinstance(expr, Unary):
            inner_t = self.types[id(expr.expr)]
            inner = self.fresh("neg")
            self.emit(f"{self.ctype(inner_t)} {inner} = {self.zero(inner_t)};")
            self.guard_block(fail, lambda: self.gen_value(expr.expr, inner, inner_t, fail))
            fn = "fold_fneg" if inner_t == "f64" else "fold_neg"
            self.guard_block(fail, lambda: self.fold_result(f"{fn}({inner})", dest, inner_t, fail))
            return
        if isinstance(expr, Binary) and expr.op == "++":
            left = self.fresh("catl")
            right = self.fresh("catr")
            self.emit(f"FoldBytes {left} = fold_bytes_empty(); FoldBytes {right} = fold_bytes_empty();")
            self.side_bytes(expr.left, left, fail)
            self.side_bytes(expr.right, right, fail)
            self.guard(fail, f"{dest} = fold_cat({left}, {right});")
            return
        if isinstance(expr, Binary) and expr.op in {"+", "-", "*", "/"}:
            left_t = self.types[id(expr.left)]
            right_t = self.types[id(expr.right)]
            left = self.fresh("al")
            right = self.fresh("ar")
            self.emit(f"{self.ctype(left_t)} {left} = {self.zero(left_t)};")
            self.emit(f"{self.ctype(right_t)} {right} = {self.zero(right_t)};")
            self.guard_block(fail, lambda: self.gen_value(expr.left, left, left_t, fail))
            self.guard_block(fail, lambda: self.gen_value(expr.right, right, right_t, fail))
            if left_t == "f64":
                fn = {"+": "fold_fadd", "-": "fold_fsub", "*": "fold_fmul", "/": "fold_fdiv"}[expr.op]
                out_t = "f64"
            else:
                fn = {"+": "fold_add", "-": "fold_sub", "*": "fold_mul", "/": "fold_div"}[expr.op]
                out_t = "i64"
            self.guard_block(fail, lambda: self.fold_result(f"{fn}({left}, {right})", dest, out_t, fail))
            return
        if isinstance(expr, Binary):
            left_t = self.types[id(expr.left)]
            left = self.fresh("cl")
            right = self.fresh("cr")
            self.emit(f"{self.ctype(left_t)} {left} = {self.zero(left_t)};")
            self.emit(f"{self.ctype(left_t)} {right} = {self.zero(left_t)};")
            self.guard_block(fail, lambda: self.gen_value(expr.left, left, left_t, fail))
            self.guard_block(fail, lambda: self.gen_value(expr.right, right, left_t, fail))
            self.guard(fail, f"{dest} = ({left} {expr.op} {right}) ? (int64_t)1 : (int64_t)0;")
            return
        if isinstance(expr, Call):
            self.gen_call(expr, dest, typ, fail)
            return
        raise FoldError("codegen expression")

    def gen_call(self, expr: Call, dest: str, typ: str, fail: FailTarget | None) -> None:
        if expr.name == "len":
            self.gen_len(expr, dest, fail)
            return
        if expr.name == "at":
            self.gen_at(expr, dest, fail)
            return
        if expr.name == "push":
            self.gen_push(expr, dest, fail)
            return
        if expr.name == "get":
            self.gen_get(expr, dest, fail)
            return
        if expr.name == "put":
            self.gen_put(expr, dest, fail)
            return
        if expr.name == "has":
            self.gen_has(expr, dest, fail)
            return
        if expr.name == "list":
            self.gen_list(expr, dest, fail)
            return
        if expr.name == "map":
            self.gen_map(expr, dest, fail)
            return
        if expr.name == "i64":
            self.gen_i64_call(expr, dest, fail)
            return
        if expr.name == "f64":
            self.gen_f64_call(expr, dest, fail)
            return
        if expr.name in BUILTIN:
            self.gen_builtin(expr, dest, fail)
            return
        if expr.name in self.structs:
            self.gen_struct(expr, dest, fail)
            return
        fn = self.fns[expr.name]
        args = []
        for arg, param in zip(expr.args, fn.params):
            tmp = self.fresh("arg")
            self.emit(f"{self.ctype(param.typ)} {tmp} = {self.zero(param.typ)};")
            self.gen_value(arg, tmp, param.typ, fail)
            args.append(tmp)
        joined = ", ".join(args)
        self.guard_block(fail, lambda: self.fold_result(f"{fn.cname}({joined})", dest, typ, fail))

    def guard_block(self, fail: FailTarget | None, emit_body) -> None:
        if fail is not None:
            self.emit(f"if (!{fail.flag}) {{")
        emit_body()
        if fail is not None:
            self.emit("}")

    def side_bytes(self, expr: object, dest: str, fail: FailTarget | None) -> None:
        typ = self.types[id(expr)]
        if typ == "bytes":
            self.guard_block(fail, lambda: self.gen_value(expr, dest, "bytes", fail))
            return
        tmp = self.fresh("num")
        if typ == "f64":
            self.emit(f"double {tmp} = 0.0;")
            self.guard_block(fail, lambda: self.gen_value(expr, tmp, "f64", fail))
            self.guard(fail, f"{dest} = fold_dec_f64({tmp});")
            return
        self.emit(f"int64_t {tmp} = 0;")
        self.guard_block(fail, lambda: self.gen_value(expr, tmp, "i64", fail))
        self.guard(fail, f"{dest} = fold_dec({tmp});")

    def fold_result(self, call: str, dest: str, typ: str, fail: FailTarget | None) -> None:
        fv = self.fresh("fv")
        self.emit(f"FoldValue {fv} = {call};")
        self.emit(f"if ({fv}.failed) {{")
        if fail is None:
            self.unwind(f"{fv}.reason")
        else:
            self.emit(f"{fail.flag} = 1; {fail.reason} = {fv}.reason;")
        self.emit("} else {")
        if typ in self.structs:
            self.emit(f"if ({fv}.obj != NULL) {{ memcpy(&{dest}, {fv}.obj, sizeof {dest}); }}")
        else:
            if map_pair(typ) is not None:
                slot = "map"
            elif list_elem(typ) is not None:
                slot = "list"
            else:
                slot = typ
            self.emit(f"{dest} = {fv}.{slot};")
        self.emit("}")

    def gen_for_list(self, row: For) -> None:
        typ = self.types[id(row.expr)]
        elem = list_elem(typ) or "i64"
        src = self.fresh("src")
        index = self.fresh("i")
        self.emit(f"FoldList {src} = {self.zero(typ)};")
        self.gen_value(row.expr, src, typ, None)
        self.emit(f"for (size_t {index} = 0; {index} < {src}.count; {index}++) {{")
        cname = self.fresh("v_" + row.name)
        self.scopes.append({row.name: (elem, cname, False)})
        self.emit(f"{self.ctype(elem)} {cname} = {self.zero(elem)};")
        self.emit(f"if ({src}.items != NULL) {{ memcpy(&{cname}, {src}.items + {index} * {src}.stride, sizeof {cname}); }}")
        self.emit(f"(void){cname};")
        self.gen_stmts(row.body)
        self.scopes.pop()
        self.emit("}")

    def key_kind(self, typ: str) -> str:
        if typ == "i64":
            return "FOLD_KEY_I64"
        if typ == "f64":
            return "FOLD_KEY_F64"
        if typ == "bytes":
            return "FOLD_KEY_BYTES"
        raise FoldError(f"codegen map key {typ}")

    def gen_for_map(self, row: For) -> None:
        typ = self.types[id(row.expr)]
        pair = map_pair(typ)
        key_t = pair[0] if pair is not None else "i64"
        src = self.fresh("src")
        index = self.fresh("i")
        self.emit(f"FoldMap {src} = {self.zero(typ)};")
        self.gen_value(row.expr, src, typ, None)
        self.emit(f"for (size_t {index} = 0; {index} < {src}.count; {index}++) {{")
        cname = self.fresh("v_" + row.name)
        self.scopes.append({row.name: (key_t, cname, False)})
        self.emit(f"{self.ctype(key_t)} {cname} = {self.zero(key_t)};")
        self.emit(
            f"if ({src}.keys != NULL) {{ memcpy(&{cname}, {src}.keys + {index} * {src}.key_stride, sizeof {cname}); }}"
        )
        self.emit(f"(void){cname};")
        self.gen_stmts(row.body)
        self.scopes.pop()
        self.emit("}")

    def gen_len(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        arg_t = self.types[id(expr.args[0])]
        tmp = self.fresh("len")
        if arg_t == "bytes":
            self.emit(f"FoldBytes {tmp} = fold_bytes_empty();")
            self.gen_value(expr.args[0], tmp, "bytes", fail)
            self.guard_block(fail, lambda: self.fold_result(f"fold_len({tmp})", dest, "i64", fail))
            return
        if map_pair(arg_t) is not None:
            self.emit(f"FoldMap {tmp} = {self.zero(arg_t)};")
            self.gen_value(expr.args[0], tmp, arg_t, fail)
            self.guard_block(fail, lambda: self.fold_result(f"fold_map_len({tmp})", dest, "i64", fail))
            return
        self.emit(f"FoldList {tmp} = {self.zero(arg_t)};")
        self.gen_value(expr.args[0], tmp, arg_t, fail)
        self.guard_block(fail, lambda: self.fold_result(f"fold_list_len({tmp})", dest, "i64", fail))

    def gen_at(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        if self.types[id(expr.args[0])] == "bytes":
            src = self.fresh("text")
            idx = self.fresh("idx")
            self.emit("FoldBytes " + src + " = fold_bytes_empty();")
            self.emit("int64_t " + idx + " = 0;")
            self.gen_value(expr.args[0], src, "bytes", fail)
            self.gen_value(expr.args[1], idx, "i64", fail)

            def byte_body() -> None:
                self.emit(
                    "if (" + idx + " < 0 || (uint64_t)" + idx + " >= " + src + ".n) {"
                )
                if fail is None:
                    self.unwind("fold_bytes_empty()")
                else:
                    self.emit(fail.flag + " = 1; " + fail.reason + " = fold_bytes_empty();")
                self.emit("} else {")
                self.emit(dest + " = (int64_t)" + src + ".p[" + idx + "];")
                self.emit("}")

            self.guard_block(fail, byte_body)
            return
        elem = self.types[id(expr)]
        lst = self.fresh("lst")
        idx = self.fresh("idx")
        self.emit(f"FoldList {lst} = {self.zero('list ' + elem)};")
        self.emit(f"int64_t {idx} = 0;")
        self.gen_value(expr.args[0], lst, "list " + elem, fail)
        self.gen_value(expr.args[1], idx, "i64", fail)

        def body() -> None:
            self.emit(f"if (!fold_list_index({lst}, {idx})) {{")
            if fail is None:
                self.unwind("fold_bytes_empty()")
            else:
                self.emit(f"{fail.flag} = 1; {fail.reason} = fold_bytes_empty();")
            self.emit("} else {")
            self.emit(
                f"memcpy(&{dest}, {lst}.items + (size_t){idx} * {lst}.stride, sizeof {dest});"
            )
            self.emit("}")

        self.guard_block(fail, body)

    def gen_push(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        list_t = self.types[id(expr)]
        elem = list_elem(list_t) or "i64"
        src = self.fresh("src")
        item = self.fresh("item")
        self.emit(f"FoldList {src} = {self.zero(list_t)};")
        self.emit(f"{self.ctype(elem)} {item} = {self.zero(elem)};")
        self.gen_value(expr.args[0], src, list_t, fail)
        self.gen_value(expr.args[1], item, elem, fail)
        self.guard(fail, f"{dest} = fold_list_push({src}, &{item}, {self.stride_of(elem)});")

    def gen_get(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        map_t = self.types[id(expr.args[0])]
        pair = map_pair(map_t)
        key_t = pair[0] if pair is not None else "i64"
        src = self.fresh("map")
        key = self.fresh("key")
        index = self.fresh("at")
        self.emit(f"FoldMap {src} = {self.zero(map_t)};")
        self.emit(f"{self.ctype(key_t)} {key} = {self.zero(key_t)};")
        self.emit(f"size_t {index} = 0;")
        self.gen_value(expr.args[0], src, map_t, fail)
        self.gen_value(expr.args[1], key, key_t, fail)

        def body() -> None:
            self.emit(f"if (!fold_map_find({src}, &{key}, {self.key_kind(key_t)}, &{index})) {{")
            if fail is None:
                self.unwind("fold_bytes_empty()")
            else:
                self.emit(f"{fail.flag} = 1; {fail.reason} = fold_bytes_empty();")
            self.emit("} else {")
            self.emit(
                f"memcpy(&{dest}, {src}.vals + {index} * {src}.val_stride, sizeof {dest});"
            )
            self.emit("}")

        self.guard_block(fail, body)

    def gen_put(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        map_t = self.types[id(expr)]
        pair = map_pair(map_t)
        key_t = pair[0] if pair is not None else "i64"
        val_t = pair[1] if pair is not None else "i64"
        src = self.fresh("map")
        key = self.fresh("key")
        val = self.fresh("val")
        self.emit(f"FoldMap {src} = {self.zero(map_t)};")
        self.emit(f"{self.ctype(key_t)} {key} = {self.zero(key_t)};")
        self.emit(f"{self.ctype(val_t)} {val} = {self.zero(val_t)};")
        self.gen_value(expr.args[0], src, map_t, fail)
        self.gen_value(expr.args[1], key, key_t, fail)
        self.gen_value(expr.args[2], val, val_t, fail)
        self.guard(
            fail,
            f"{dest} = fold_map_put({src}, &{key}, &{val}, {self.key_kind(key_t)});",
        )

    def gen_has(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        map_t = self.types[id(expr.args[0])]
        pair = map_pair(map_t)
        key_t = pair[0] if pair is not None else "i64"
        src = self.fresh("map")
        key = self.fresh("key")
        self.emit(f"FoldMap {src} = {self.zero(map_t)};")
        self.emit(f"{self.ctype(key_t)} {key} = {self.zero(key_t)};")
        self.gen_value(expr.args[0], src, map_t, fail)
        self.gen_value(expr.args[1], key, key_t, fail)
        self.guard(fail, f"{dest} = fold_map_has({src}, &{key}, {self.key_kind(key_t)});")

    def gen_map(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        typ = self.types[id(expr)]
        pair = map_pair(typ)
        key_t = pair[0] if pair is not None else "i64"
        val_t = pair[1] if pair is not None else "i64"
        built = self.fresh("map")
        self.emit(f"FoldMap {built} = {self.zero(typ)};")

        def fill() -> None:
            index = 0
            while index < len(expr.args):
                key = self.fresh("mk")
                val = self.fresh("mv")
                self.emit(f"{self.ctype(key_t)} {key} = {self.zero(key_t)};")
                self.emit(f"{self.ctype(val_t)} {val} = {self.zero(val_t)};")
                self.gen_value(expr.args[index], key, key_t, fail)
                self.gen_value(expr.args[index + 1], val, val_t, fail)
                self.guard(
                    fail,
                    f"{built} = fold_map_put({built}, &{key}, &{val}, {self.key_kind(key_t)});",
                )
                index += 2
            self.guard(fail, f"{dest} = {built};")

        self.guard_block(fail, fill)

    def gen_list(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        typ = self.types[id(expr)]
        elem = list_elem(typ) or "i64"
        stride = self.stride_of(elem)
        if not expr.args:
            self.guard(fail, f"{dest} = fold_list_empty({stride});")
            return
        count = len(expr.args)
        buf = self.fresh("items")
        self.emit(f"uint8_t *{buf} = NULL;")

        def fill() -> None:
            self.emit(f"{buf} = fold_list_alloc({count}, {stride});")
            for index, arg in enumerate(expr.args):
                tmp = self.fresh("el")
                self.emit(f"{self.ctype(elem)} {tmp} = {self.zero(elem)};")
                self.gen_value(arg, tmp, elem, fail)
                self.guard(fail, f"memcpy({buf} + {index} * ({stride}), &{tmp}, {stride});")
            self.guard(
                fail,
                f"{dest}.items = {buf}; {dest}.count = {count}; {dest}.stride = {stride};",
            )

        self.guard_block(fail, fill)

    def gen_i64_call(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        arg_t = self.types[id(expr.args[0])]
        tmp = self.fresh("conv")
        if arg_t == "f64":
            self.emit(f"double {tmp} = 0.0;")
            self.gen_value(expr.args[0], tmp, "f64", fail)
            self.guard_block(fail, lambda: self.fold_result(f"fold_i64_from_f64({tmp})", dest, "i64", fail))
            return
        self.emit(f"FoldBytes {tmp} = fold_bytes_empty();")
        self.gen_value(expr.args[0], tmp, "bytes", fail)
        self.guard_block(fail, lambda: self.fold_result(f"fold_i64({tmp})", dest, "i64", fail))

    def gen_f64_call(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        tmp = self.fresh("conv")
        self.emit(f"int64_t {tmp} = 0;")
        self.gen_value(expr.args[0], tmp, "i64", fail)
        self.guard_block(fail, lambda: self.fold_result(f"fold_f64_from_i64({tmp})", dest, "f64", fail))

    def gen_struct(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        struct = self.structs[expr.name]
        pairs = []
        for arg, item in zip(expr.args, struct.fields):
            tmp = self.fresh("sf")
            self.emit(f"{self.ctype(item.typ)} {tmp} = {self.zero(item.typ)};")
            self.gen_value(arg, tmp, item.typ, fail)
            pairs.append((item.name, tmp))

        def assign() -> None:
            for name, tmp in pairs:
                self.emit(f"{dest}.f_{name} = {tmp};")

        self.guard_block(fail, assign)

    def gen_builtin(self, expr: Call, dest: str, fail: FailTarget | None) -> None:
        args = []
        _gauge, params, ret, fails = BUILTIN[expr.name]
        for arg, typ in zip(expr.args, params):
            tmp = self.fresh("b")
            self.emit(f"{self.ctype(typ)} {tmp} = {self.zero(typ)};")
            self.gen_value(arg, tmp, typ, fail)
            args.append(tmp)
        call = f"fold_{expr.name}({', '.join(args)})"
        if expr.name == "argc":
            self.guard(fail, f"{dest} = {call};")
            return
        if not fails:
            self.guard(fail, f"{dest} = {call};")
            return
        self.guard_block(fail, lambda: self.fold_result(call, dest, ret, fail))


def parse_source(text: str, require_main: bool = True) -> Program:
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        lines.append((number, lex_line(line, number)))
    return Parser(lines).parse(require_main)


def prepare_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    return source_text(text.encode("utf-8"))


def resolve_use(origin: Path, raw: str, line: int) -> Path:
    text = raw.replace("\\", "/")
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        fail(line, "use path must stay beside the source")
    parts = text.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail(line, "use path must stay beside the source")
    for part in parts:
        if not all(ch.isalnum() or ch in "._-" for ch in part):
            fail(line, "use path must stay beside the source")
    parent = origin.parent.resolve()
    path = parent.joinpath(*parts).resolve()
    if path != parent and parent not in path.parents:
        fail(line, "use path must stay beside the source")
    return path


def merge_program(dst: Program, src: Program) -> None:
    for name in src.gauges:
        if name not in dst.gauges:
            dst.gauges.append(name)
    known_structs = {struct.name for struct in dst.structs}
    known_fns = {fn.name for fn in dst.fns}
    for struct in src.structs:
        if struct.name in known_structs or struct.name in known_fns:
            fail(struct.line, "duplicate struct name")
        known_structs.add(struct.name)
        dst.structs.append(struct)
    for fn in src.fns:
        if fn.name in known_fns or fn.name in known_structs:
            fail(fn.line, "duplicate function name")
        known_fns.add(fn.name)
        dst.fns.append(fn)


def load_program(
    text: str,
    origin: Path | None = None,
    loading: tuple[Path, ...] = (),
    seen: set[Path] | None = None,
) -> Program:
    if seen is None:
        seen = set()
    if origin is not None:
        origin = origin.resolve()
        if origin in loading:
            raise FoldError("use cycle")
        seen.add(origin)
    program = parse_source(prepare_text(text), require_main=not loading)
    for use in program.uses:
        if origin is None:
            fail(use.line, "use needs a source file")
        path = resolve_use(origin, use.path, use.line)
        if path in loading or path == origin:
            fail(use.line, "use cycle")
        if path in seen:
            continue
        if not path.is_file():
            fail(use.line, "missing use")
        try:
            child = load_program(source_text(path.read_bytes()), path, loading + (origin,), seen)
        except FoldError as exc:
            message = str(exc)
            if message.startswith(path.name):
                raise
            raise FoldError(f"{path.name}: {message}") from exc
        merge_program(program, child)
    return program


def shared_import() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    dll = build / "sensepin.dll"
    runtime = root / "runtime.c"
    header = root / "runtime.h"
    newest = max(runtime.stat().st_mtime, header.stat().st_mtime)
    candidates = (build / "sensepin.lib", build / "sensepin.dll.a")
    ready = dll.is_file() and dll.stat().st_mtime >= newest and any(item.is_file() for item in candidates)
    if not ready:
        proc = subprocess.run(
            ["clang", "-O2", "-shared", "-DFOLD_BUILD_DLL", "-o", "sensepin.dll", str(runtime)],
            cwd=build,
            capture_output=True,
        )
        if proc.returncode != 0:
            sys.stderr.buffer.write(proc.stderr)
            sys.stderr.buffer.write(proc.stdout)
            raise SystemExit(proc.returncode)
    for lib in candidates:
        if lib.is_file():
            return dll, lib
    raise SystemExit("clang did not write an import library beside sensepin.dll")


def stage_dll(exe: Path) -> Path:
    dll, lib = shared_import()
    exe.parent.mkdir(parents=True, exist_ok=True)
    dest = exe.parent / dll.name
    if dest.resolve() != dll.resolve():
        shutil.copyfile(dll, dest)
    return lib


def compile_text(text: str, origin: Path | None = None) -> str:
    try:
        program = load_program(text, origin)
        types = Checker(program).check()
        generated = Gen(program, types).gen()
    except RecursionError as exc:
        raise FoldError("source is too deep") from exc
    return (
        "#define FOLD_USE_DLL\n"
        "#include \"runtime.h\"\n"
        "#include <string.h>\n"
        "\n"
        + generated
        + "\nint main(int argc, char **argv) {\n"
        "    fold_init(argc, argv);\n"
        "    return fold_main();\n"
        "}\n"
    )


def compile_file(source: Path, c_path: Path, exe: Path | None) -> None:
    try:
        c_text = compile_text(source_text(source.read_bytes()), source)
    except FoldError as exc:
        print(f"{source}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OSError as exc:
        print(f"{source}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_text(c_text, encoding="utf-8")
    if exe is None:
        return
    lib = stage_dll(exe)
    fold_dir = Path(__file__).resolve().parent
    proc = subprocess.run(
        ["clang", "-O2", "-I", str(fold_dir), "-o", str(exe), "--", str(c_path), str(lib)],
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.buffer.write(proc.stdout)
        raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a Sensepin program to C.")
    parser.add_argument("source")
    parser.add_argument("-o", required=True, dest="c_path")
    parser.add_argument("--exe")
    args = parser.parse_args()
    compile_file(Path(args.source), Path(args.c_path), Path(args.exe) if args.exe else None)


if __name__ == "__main__":
    main()
