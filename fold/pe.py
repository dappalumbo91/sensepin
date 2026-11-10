"""Sensepin PE64 image writer. The bytes of the exe are assembled here."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from x64 import Asm

TEXT_RVA = 0x1000
FILE_ALIGN = 0x200
SECTION_ALIGN = 0x1000
HEADER_SIZE = 0x200
IMAGE_BASE = 0x140000000


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


@dataclass
class Blob:
    name: str
    data: bytearray
    alignment: int = 1


@dataclass
class Image:
    code: Asm = field(default_factory=Asm)
    blobs: list[Blob] = field(default_factory=list)
    imports: list[tuple[str, list[str]]] = field(default_factory=list)

    def blob(self, name: str, data: bytes = b"", alignment: int = 1) -> str:
        if any(item.name == name for item in self.blobs):
            raise RuntimeError(f"duplicate blob {name}")
        self.blobs.append(Blob(name, bytearray(data), alignment))
        return name

    def set_blob(self, name: str, data: bytes) -> None:
        for item in self.blobs:
            if item.name == name:
                item.data = bytearray(data)
                return
        raise RuntimeError(f"missing blob {name}")

    def data_rva(self) -> int:
        return align(TEXT_RVA + len(self.code.buf), SECTION_ALIGN)

    def blob_offset(self, name: str) -> int:
        cursor = 0
        for item in self.blobs:
            cursor = align(cursor, item.alignment)
            if item.name == name:
                return cursor
            cursor += len(item.data)
        raise RuntimeError(f"missing blob {name}")

    def blob_rva(self, name: str) -> int:
        return self.data_rva() + self.blob_offset(name)

    def iat_symbol(self, dll: str, func: str) -> str:
        stem = dll.split(".", 1)[0]
        return f"iat_{stem}_{func}"

    def link(self, entry: str) -> bytes:
        if entry not in self.code.labels:
            raise RuntimeError(f"missing entry {entry}")
        data_rva = self.data_rva()
        data = bytearray()
        symbols: dict[str, int] = {}

        def place(name: str, raw: bytes, alignment: int) -> int:
            nonlocal data
            while len(data) % alignment:
                data.append(0)
            symbols[name] = data_rva + len(data)
            at = len(data)
            data += raw
            return at

        for item in self.blobs:
            place(item.name, bytes(item.data), item.alignment)

        hint_off: dict[tuple[str, str], int] = {}
        for dll, funcs in self.imports:
            place(f"dllname_{dll}", dll.encode("ascii") + b"\0", 2)
            for func in funcs:
                hint = b"\0\0" + func.encode("ascii") + b"\0"
                hint_off[(dll, func)] = place(f"hint_{dll}_{func}", hint, 2)

        for dll, funcs in self.imports:
            while len(data) % 8:
                data.append(0)
            symbols[f"ilt_{dll}"] = data_rva + len(data)
            for func in funcs:
                data += (data_rva + hint_off[(dll, func)]).to_bytes(8, "little")
            data += b"\0" * 8
            while len(data) % 8:
                data.append(0)
            symbols[f"iat_{dll}"] = data_rva + len(data)
            for func in funcs:
                symbols[self.iat_symbol(dll, func)] = data_rva + len(data)
                data += (data_rva + hint_off[(dll, func)]).to_bytes(8, "little")
            data += b"\0" * 8

        while len(data) % 4:
            data.append(0)
        import_at = len(data)
        for dll, _funcs in self.imports:
            data += struct.pack(
                "<IIIII",
                symbols[f"ilt_{dll}"],
                0,
                0,
                symbols[f"dllname_{dll}"],
                symbols[f"iat_{dll}"],
            )
        data += b"\0" * 20
        import_rva = data_rva + import_at
        import_size = 20 * (len(self.imports) + 1)

        code_rva = TEXT_RVA
        for name, off in self.code.labels.items():
            symbols.setdefault(name, code_rva + off)
        self.code.patch(code_rva, symbols)
        entry_rva = code_rva + self.code.labels[entry]
        return _pe(bytes(self.code.buf), bytes(data), entry_rva, data_rva, import_rva, import_size)


def _pe(code: bytes, data: bytes, entry_rva: int, data_rva: int, import_rva: int, import_size: int) -> bytes:
    text_raw_size = align(max(len(code), 1), FILE_ALIGN)
    data_raw_size = align(max(len(data), 1), FILE_ALIGN)
    text_ptr = HEADER_SIZE
    data_ptr = text_ptr + text_raw_size
    size_of_image = align(data_rva + len(data), SECTION_ALIGN)

    opt = bytearray(0xF0)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 4, text_raw_size)
    struct.pack_into("<I", opt, 8, data_raw_size)
    struct.pack_into("<I", opt, 16, entry_rva)
    struct.pack_into("<I", opt, 20, TEXT_RVA)
    struct.pack_into("<Q", opt, 24, IMAGE_BASE)
    struct.pack_into("<I", opt, 32, SECTION_ALIGN)
    struct.pack_into("<I", opt, 36, FILE_ALIGN)
    struct.pack_into("<HH", opt, 40, 6, 0)
    struct.pack_into("<HH", opt, 48, 6, 0)
    struct.pack_into("<I", opt, 56, size_of_image)
    struct.pack_into("<I", opt, 60, HEADER_SIZE)
    struct.pack_into("<HH", opt, 68, 3, 0x0100)
    struct.pack_into("<Q", opt, 72, 0x100000)
    struct.pack_into("<Q", opt, 80, 0x1000)
    struct.pack_into("<Q", opt, 88, 0x100000)
    struct.pack_into("<Q", opt, 96, 0x1000)
    struct.pack_into("<I", opt, 108, 16)
    struct.pack_into("<II", opt, 112 + 8, import_rva, import_size)

    sections = bytearray()
    sections += _section(".text", len(code), TEXT_RVA, text_raw_size, text_ptr, 0x60000020)
    sections += _section(".data", len(data), data_rva, data_raw_size, data_ptr, 0xC0000040)

    headers = bytearray(0x80)
    headers[0:2] = b"MZ"
    struct.pack_into("<I", headers, 0x3C, 0x80)
    headers += b"PE\0\0"
    headers += struct.pack("<HHIIIHH", 0x8664, 2, 0, 0, 0, 0xF0, 0x0023)
    headers += opt
    headers += sections
    if len(headers) > HEADER_SIZE:
        raise RuntimeError(f"headers are {len(headers)} bytes")
    headers += bytes(HEADER_SIZE - len(headers))
    return bytes(headers) + code + bytes(text_raw_size - len(code)) + data + bytes(data_raw_size - len(data))


def _section(name: str, virtual_size: int, virtual_address: int, raw_size: int, raw_ptr: int, chars: int) -> bytes:
    raw = bytearray(40)
    raw[0 : len(name)] = name.encode("ascii")
    struct.pack_into("<IIIIII", raw, 8, virtual_size, virtual_address, raw_size, raw_ptr, 0, 0)
    struct.pack_into("<HHI", raw, 32, 0, 0, chars)
    return bytes(raw)


def hello_image() -> bytes:
    image = Image()
    image.imports = [("kernel32.dll", ["GetStdHandle", "WriteFile", "ExitProcess"])]
    message = b"hi\n"
    image.blob("msg", message)
    image.blob("written", b"\0\0\0\0")
    asm = image.code
    asm.label("start")
    asm.and_rsp_align()
    asm.sub_rsp_imm32(0x100)
    asm.mov_reg_imm32(1, 0xFFFFFFF5)  # RCX = -11
    asm.call_rip(image.iat_symbol("kernel32.dll", "GetStdHandle"))
    asm.mov_reg_reg(3, 0)  # RBX = handle
    asm.mov_reg_reg(1, 3)
    asm.lea_rip(2, "msg")
    asm.mov_reg_imm32(8, len(message))
    asm.lea_rip(9, "written")
    asm.mov_rsp_imm32(0x20, 0)
    asm.call_rip(image.iat_symbol("kernel32.dll", "WriteFile"))
    asm.xor_reg(1, 1)
    asm.call_rip(image.iat_symbol("kernel32.dll", "ExitProcess"))
    asm.int3()
    return image.link("start")


if __name__ == "__main__":
    from pathlib import Path

    dest = Path(__file__).resolve().parent / "build" / "own-hello.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(hello_image())
    print(dest)
    print(dest.stat().st_size)
