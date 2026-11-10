"""Sensepin compiler. The contract is SPEC.md. Python is the factory. C is the vessel.

The public name is Sensepin. This file stays foldc.py. Sources use .sensepin.
"""

from __future__ import annotations

import argparse
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
}
RESERVED = KEYWORDS | {"argc", "arg", "open", "lines", "i64"}
GAUGES = {"args", "file", "lines", "i64"}
BUILTIN = {
    "argc": ("args", [], "i64", False),
    "arg": ("args", ["i64"], "bytes", True),
    "open": ("file", ["bytes", "i64", "bytes", "bytes", "bytes"], "bytes", True),
    "i64": ("i64", ["bytes"], "i64", True),
}


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
class StrLit:
    value: bytes
    line: int


@dataclass
class Name:
    name: str
    line: int


@dataclass
class Field:
    name: str
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
class Program:
    gauges: list[str]
    fns: list
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
        if ch in "()=+-<>!,.:":
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
        left = self.unary()
        while self.peek() is not None and self.peek().kind in {"+", "-"}:
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
        tok = self.take()
        if tok.kind == "number":
            value = int(tok.text)
            if value > I64_MAX:
                fail(tok.line, "integer does not fit in i64")
            return IntLit(value, tok.line)
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
        if tok.kind == "ident":
            if self.match("("):
                args = []
                if not self.match(")"):
                    while True:
                        args.append(self.expr())
                        if self.match(")"):
                            break
                        if not self.match(","):
                            fail(self.line, "expected , or )")
                return Call(tok.text, args, tok.line)
            if self.match("."):
                field = self.take()
                if field.kind != "ident":
                    fail(tok.line, "expected a field name")
                return Field(tok.text, field.text, tok.line)
            return Name(tok.text, tok.line)
        fail(tok.line, f"unexpected {tok.text}")
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

    def parse(self) -> Program:
        row = self.peek()
        if row is None or row[1][0].kind != "phase":
            fail(row[0] if row else 1, "expected phase console")
        _, tokens = self.take()
        if len(tokens) != 2 or tokens[1].text != "console":
            fail(tokens[0].line, "v0 phase is console")
        gauges = []
        while self.peek() is not None and self.peek()[1][0].kind == "gauge":
            _, tokens = self.take()
            if len(tokens) != 2 or tokens[1].kind != "ident":
                fail(tokens[0].line, "expected a gauge name")
            name = tokens[1].text
            if name not in GAUGES:
                fail(tokens[1].line, f"unknown gauge {name}")
            if name in gauges:
                fail(tokens[1].line, f"gauge {name} is named twice")
            gauges.append(name)
        fns = []
        while self.peek() is not None:
            fns.append(self.parse_fn())
        if not any(fn.name == "main" for fn in fns):
            fail(1, "missing fn main")
        return Program(gauges, fns, 1)

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
                    typ = parser.take()
                    if typ.kind != "ident" or typ.text not in {"i64", "bytes"}:
                        fail(line, "expected type i64 or bytes")
                    params.append(Param(ident.text, typ.text, line))
                    if parser.match(")"):
                        break
                    if not parser.match(","):
                        fail(line, "expected , or )")
            if not parser.match("->"):
                fail(line, "expected ->")
            typ = parser.take()
            if typ.kind != "ident" or typ.text not in {"i64", "bytes"}:
                fail(line, "expected return type i64 or bytes")
            ret = typ.text
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
            if len(tokens) < 4 or tokens[1].kind != "ident" or tokens[2].kind != "=":
                fail(line, "expected let name = expr")
            if tokens[1].text in RESERVED:
                fail(line, f"{tokens[1].text} is reserved")
            return Let(tokens[1].text, ExprParser(tokens[3:], line).parse(), line)
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


class Checker:
    def __init__(self, program: Program):
        self.program = program
        self.fns = {fn.name: fn for fn in program.fns}
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
        for fn in self.program.fns:
            seen = set()
            for param in fn.params:
                if param.name in seen:
                    fail(param.line, f"duplicate parameter {param.name}")
                seen.add(param.name)
            if fn.name != "main" and (not fn.body or not isinstance(fn.body[-1], Return)):
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

    def stmts(self, rows: list) -> None:
        for row in rows:
            self.stmt(row)

    def stmt(self, row: object) -> None:
        if isinstance(row, Let):
            if row.name in self.scopes[-1]:
                fail(row.line, f"{row.name} is already bound in this block")
            typ = self.expr(row.expr)
            if typ in {"bottom", "line"}:
                fail(row.line, "let needs an i64 or bytes value")
            self.scopes[-1][row.name] = (typ, True)
            return
        if isinstance(row, Set):
            found = self.lookup(row.name, row.line)
            if not found[1]:
                fail(row.line, f"{row.name} cannot be assigned")
            typ = self.expr(row.expr)
            if typ != found[0]:
                fail(row.line, f"{row.name} is {found[0]}")
            return
        if isinstance(row, Write):
            typ = self.expr(row.expr)
            if typ not in {"bytes", "i64"}:
                fail(row.line, "write needs bytes or i64")
            if typ == "i64":
                self.note("i64", row.line)
            return
        if isinstance(row, Fail):
            typ = self.expr(row.expr)
            if typ not in {"bytes", "i64"}:
                fail(row.line, "fail needs bytes or i64")
            if typ == "i64":
                self.note("i64", row.line)
            self.types[id(row)] = "bottom"
            return
        if isinstance(row, Return):
            if self.current is None or self.current.name == "main":
                fail(row.line, "main does not return a value")
            typ = self.expr(row.expr)
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
        if isinstance(row, For):
            if not isinstance(row.expr, Call) or row.expr.name != "lines" or len(row.expr.args) != 1:
                fail(row.line, "for walks lines(bytes)")
            arg = self.expr(row.expr.args[0])
            if arg != "bytes":
                fail(row.line, "lines needs bytes")
            self.note("lines", row.line)
            self.scopes.append({row.name: ("line", False)})
            self.stmts(row.body)
            self.scopes.pop()
            return
        fail(1, "unknown statement")

    def lookup(self, name: str, line: int) -> tuple[str, bool]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        fail(line, f"unknown name {name}")
        raise AssertionError

    def expr(self, expr: object) -> str:
        typ = self.expr_type(expr)
        self.types[id(expr)] = typ
        return typ

    def expr_type(self, expr: object) -> str:
        if isinstance(expr, IntLit):
            self.note("i64", expr.line)
            return "i64"
        if isinstance(expr, StrLit):
            return "bytes"
        if isinstance(expr, Name):
            if expr.name == "reason":
                if not self.reason:
                    fail(expr.line, "reason is only in scope after else")
                return "bytes"
            return self.lookup(expr.name, expr.line)[0]
        if isinstance(expr, Field):
            owner = self.lookup(expr.name, expr.line)
            if owner[0] != "line":
                fail(expr.line, f"{expr.name} has no fields")
            if expr.field == "text":
                return "bytes"
            if expr.field == "n":
                self.note("i64", expr.line)
                return "i64"
            fail(expr.line, f"unknown field {expr.field}")
        if isinstance(expr, Call):
            if expr.name == "lines":
                fail(expr.line, "lines() is only legal in for")
            if expr.name in BUILTIN:
                gauge, params, ret, _fails = BUILTIN[expr.name]
                self.note(gauge, expr.line)
                if len(expr.args) != len(params):
                    fail(expr.line, f"{expr.name} expects {len(params)} arguments")
                for arg, expect in zip(expr.args, params):
                    got = self.expr(arg)
                    if got != expect:
                        fail(expr.line, f"{expr.name} expects {expect}")
                return ret
            fn = self.fns.get(expr.name)
            if fn is None or fn.name == "main":
                fail(expr.line, f"unknown function {expr.name}")
            if len(expr.args) != len(fn.params):
                fail(expr.line, f"{expr.name} expects {len(fn.params)} arguments")
            for arg, param in zip(expr.args, fn.params):
                got = self.expr(arg)
                if got != param.typ:
                    fail(expr.line, f"{expr.name} expects {param.typ}")
            return fn.ret or "bottom"
        if isinstance(expr, Fail):
            typ = self.expr(expr.expr)
            if typ not in {"bytes", "i64"}:
                fail(expr.line, "fail needs bytes or i64")
            if typ == "i64":
                self.note("i64", expr.line)
            return "bottom"
        if isinstance(expr, Unary):
            inner = self.expr(expr.expr)
            if inner != "i64":
                fail(expr.line, "unary - needs i64")
            self.note("i64", expr.line)
            return "i64"
        if isinstance(expr, Binary):
            left = self.expr(expr.left)
            right = self.expr(expr.right)
            if expr.op == "++":
                if left not in {"bytes", "i64"} or right not in {"bytes", "i64"}:
                    fail(expr.line, "++ needs bytes or i64")
                if left == "i64" or right == "i64":
                    self.note("i64", expr.line)
                return "bytes"
            if left != "i64" or right != "i64":
                fail(expr.line, f"{expr.op} needs i64")
            self.note("i64", expr.line)
            return "i64"
        if isinstance(expr, Else):
            left = self.expr(expr.left)
            previous = self.reason
            self.reason = True
            right = self.expr(expr.right)
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


@dataclass
class FailTarget:
    flag: str
    reason: str


class Gen:
    def __init__(self, program: Program, types: dict[int, str]):
        self.program = program
        self.types = types
        self.fns = {fn.name: fn for fn in program.fns}
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
        return "int64_t" if typ == "i64" else "FoldBytes"

    def zero(self, typ: str) -> str:
        return "0" if typ == "i64" else "fold_bytes_empty()"

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
        prototypes = []
        for fn in self.program.fns:
            prototypes.append(self.signature(fn) + ";")
            self.gen_fn(fn)
        bodies = "\n".join(self.out)
        lits = []
        for idx, data in enumerate(self.lits):
            nums = ", ".join(str(byte) for byte in data)
            lits.append(f"static const uint8_t fold_lit_{idx}[] = {{{nums}}};")
        return "\n".join(prototypes + lits) + "\n" + bodies

    def signature(self, fn: Fn) -> str:
        if fn.name == "main":
            return "int fold_main(void)"
        ret = self.ctype(fn.ret or "i64")
        params = ", ".join(f"{self.ctype(typ)} {name}" for name, typ in fn.param_c) or "void"
        return f"{ret} {fn.cname}({params})"

    def gen_fn(self, fn: Fn) -> None:
        self.fn = fn
        self.scopes = [{}]
        for param, (cname, typ) in zip(fn.params, fn.param_c):
            self.scopes[-1][param.name] = (typ, cname, False)
        self.emit(self.signature(fn) + " {")
        if fn.name != "main":
            self.emit("fold_enter();")
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
            self.gen_io("fold_fail", row.expr)
            return
        if isinstance(row, Return):
            typ = self.types[id(row.expr)]
            tmp = self.fresh("ret")
            self.emit(f"{self.ctype(typ)} {tmp} = {self.zero(typ)};")
            self.gen_value(row.expr, tmp, typ, None)
            if self.fn is not None and self.fn.name != "main":
                self.emit("fold_leave();")
            self.emit(f"return {tmp};")
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
        if isinstance(row, For):
            src = self.fresh("src")
            lines = self.fresh("lines")
            index = self.fresh("i")
            self.emit(f"FoldBytes {src} = fold_bytes_empty();")
            self.gen_value(row.expr.args[0], src, "bytes", None)
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
            self.emit(f"free({lines}.items);")
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
        self.emit(f"FoldBytes {tmp} = fold_bytes_empty();")
        self.gen_value(expr, tmp, "bytes", None)
        self.emit(f"{fn}({tmp});")

    def gen_value(self, expr: object, dest: str, typ: str, fail: FailTarget | None) -> None:
        if isinstance(expr, IntLit):
            self.guard(fail, f"{dest} = {self.c_i64(expr.value)};")
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
            _typ, cname, _assign = self.lookup(expr.name)
            self.guard(fail, f"{dest} = {cname}.{expr.field};")
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
            self.gen_io("fold_fail", expr.expr)
            return
        if isinstance(expr, Unary):
            inner = self.fresh("neg")
            self.emit(f"int64_t {inner} = 0;")
            self.guard_block(fail, lambda: self.gen_value(expr.expr, inner, "i64", fail))
            self.guard_block(fail, lambda: self.fold_result(f"fold_neg({inner})", dest, "i64", fail))
            return
        if isinstance(expr, Binary) and expr.op == "++":
            left = self.fresh("catl")
            right = self.fresh("catr")
            self.emit(f"FoldBytes {left} = fold_bytes_empty(); FoldBytes {right} = fold_bytes_empty();")
            self.side_bytes(expr.left, left, fail)
            self.side_bytes(expr.right, right, fail)
            self.guard(fail, f"{dest} = fold_cat({left}, {right});")
            return
        if isinstance(expr, Binary) and expr.op in {"+", "-"}:
            left = self.fresh("al")
            right = self.fresh("ar")
            self.emit(f"int64_t {left} = 0; int64_t {right} = 0;")
            self.guard_block(fail, lambda: self.gen_value(expr.left, left, "i64", fail))
            self.guard_block(fail, lambda: self.gen_value(expr.right, right, "i64", fail))
            fn = "fold_add" if expr.op == "+" else "fold_sub"
            self.guard_block(fail, lambda: self.fold_result(f"{fn}({left}, {right})", dest, "i64", fail))
            return
        if isinstance(expr, Binary):
            left = self.fresh("cl")
            right = self.fresh("cr")
            self.emit(f"int64_t {left} = 0; int64_t {right} = 0;")
            self.guard_block(fail, lambda: self.gen_value(expr.left, left, "i64", fail))
            self.guard_block(fail, lambda: self.gen_value(expr.right, right, "i64", fail))
            self.guard(fail, f"{dest} = ({left} {expr.op} {right}) ? (int64_t)1 : (int64_t)0;")
            return
        if isinstance(expr, Call):
            if expr.name in BUILTIN:
                self.gen_builtin(expr, dest, fail)
                return
            fn = self.fns[expr.name]
            args = []
            for arg, param in zip(expr.args, fn.params):
                tmp = self.fresh("arg")
                self.emit(f"{self.ctype(param.typ)} {tmp} = {self.zero(param.typ)};")
                self.gen_value(arg, tmp, param.typ, fail)
                args.append(tmp)
            joined = ", ".join(args)
            self.guard(fail, f"{dest} = {fn.cname}({joined});")
            return
        raise FoldError("codegen expression")

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
        self.emit(f"int64_t {tmp} = 0;")
        self.guard_block(fail, lambda: self.gen_value(expr, tmp, "i64", fail))
        self.guard(fail, f"{dest} = fold_dec({tmp});")

    def fold_result(self, call: str, dest: str, typ: str, fail: FailTarget | None) -> None:
        fv = self.fresh("fv")
        field = "i64" if typ == "i64" else "bytes"
        self.emit(f"FoldValue {fv} = {call};")
        self.emit(f"if ({fv}.failed) {{")
        if fail is None:
            self.emit(f"fold_fail({fv}.reason);")
        else:
            self.emit(f"{fail.flag} = 1; {fail.reason} = {fv}.reason;")
        self.emit("} else {")
        self.emit(f"{dest} = {fv}.{field};")
        self.emit("}")

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


def parse_source(text: str) -> Program:
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        lines.append((number, lex_line(line, number)))
    return Parser(lines).parse()


def compile_text(text: str) -> str:
    try:
        program = parse_source(source_text(text.encode("utf-8")))
        types = Checker(program).check()
        generated = Gen(program, types).gen()
    except RecursionError as exc:
        raise FoldError("source is too deep") from exc
    runtime = (Path(__file__).resolve().parent / "runtime.c").read_text(encoding="utf-8")
    marker = "/*FOLD_PROGRAM*/"
    if marker not in runtime:
        raise FoldError("runtime is missing the program marker")
    return runtime.replace(marker, generated, 1)


def compile_file(source: Path, c_path: Path, exe: Path | None) -> None:
    try:
        c_text = compile_text(source_text(source.read_bytes()))
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
    proc = subprocess.run(
        ["clang", "-O2", "-o", str(exe), "--", str(c_path)],
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
