"""Sensepin x64 assembler. The bytes are ours. No external assembler."""

from __future__ import annotations

RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI = range(8)
R8, R9, R10, R11, R12, R13, R14, R15 = range(8, 16)


def _rex(w: int, reg: int, rm: int, index: int = 0) -> bytes:
    r = 1 if reg >= 8 else 0
    b = 1 if rm >= 8 else 0
    x = 1 if index >= 8 else 0
    if w or r or b or x:
        return bytes([0x40 | (w << 3) | (r << 2) | (x << 1) | b])
    return b""


def _modrm(mod: int, reg: int, rm: int) -> int:
    return ((mod & 3) << 6) | ((reg & 7) << 3) | (rm & 7)


class Asm:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.jumps: list[tuple[int, str]] = []
        self.rips: list[tuple[int, str]] = []

    def label(self, name: str) -> None:
        if name in self.labels:
            raise RuntimeError(f"duplicate label {name}")
        self.labels[name] = len(self.buf)

    def raw(self, data: bytes) -> None:
        self.buf += data

    def imm8(self, value: int) -> None:
        self.buf.append(value & 0xFF)

    def patch(self, code_rva: int, symbols: dict[str, int]) -> None:
        for at, name in self.jumps:
            target = self.labels[name]
            rel = target - (at + 4)
            self.buf[at : at + 4] = (rel & 0xFFFFFFFF).to_bytes(4, "little")
        for at, name in self.rips:
            target = symbols[name]
            rel = target - (code_rva + at + 4)
            self.buf[at : at + 4] = (rel & 0xFFFFFFFF).to_bytes(4, "little")

    def ret(self) -> None:
        self.imm8(0xC3)

    def nop(self) -> None:
        self.imm8(0x90)

    def push(self, reg: int) -> None:
        self.raw(_rex(0, 0, reg))
        self.imm8(0x50 + (reg & 7))

    def pop(self, reg: int) -> None:
        self.raw(_rex(0, 0, reg))
        self.imm8(0x58 + (reg & 7))

    def mov_reg_imm64(self, reg: int, value: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xB8 + (reg & 7))
        self.buf += (value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")

    def mov_reg_imm32(self, reg: int, value: int) -> None:
        if reg >= 8:
            self.raw(_rex(0, 0, reg))
        self.imm8(0xB8 + (reg & 7))
        self.buf += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def mov_reg_reg(self, dest: int, src: int) -> None:
        self.raw(_rex(1, src, dest))
        self.imm8(0x89)
        self.imm8(_modrm(3, src, dest))

    def _disp(self, disp: int) -> tuple[int, bytes]:
        if -128 <= disp <= 127:
            return 1, bytes([disp & 0xFF])
        return 2, (disp & 0xFFFFFFFF).to_bytes(4, "little")

    def _emit_mem(
        self,
        rex_w: int,
        opcode: bytes,
        reg: int,
        base: int,
        disp: int,
        tail: bytes = b"",
        tight: bool = False,
    ) -> None:
        # RSP and R12 are encoded as rm=4, which means SIB follows. Without
        # that byte the displacement is read as a SIB and the next instruction
        # is eaten.
        if tight:
            mod, raw = self._mem_disp(base, disp)
        else:
            mod, raw = self._disp(disp)
        self.raw(_rex(rex_w, reg, base))
        self.raw(opcode)
        self.imm8(_modrm(mod, reg, base))
        if base in {RSP, R12}:
            self.imm8(0x20 | (base & 7))
        self.raw(raw)
        self.raw(tail)

    def mov_reg_mem(self, dest: int, base: int, disp: int) -> None:
        self._emit_mem(1, b"\x8B", dest, base, disp)

    def mov_mem_reg(self, base: int, disp: int, src: int) -> None:
        self._emit_mem(1, b"\x89", src, base, disp)

    def mov_mem_imm32(self, base: int, disp: int, value: int) -> None:
        self._emit_mem(1, b"\xC7", 0, base, disp, (value & 0xFFFFFFFF).to_bytes(4, "little"))

    def lea_rip(self, dest: int, symbol: str) -> None:
        self.raw(_rex(1, dest, 0))
        self.imm8(0x8D)
        self.imm8(_modrm(0, dest, 5))
        self.rips.append((len(self.buf), symbol))
        self.buf += b"\0\0\0\0"

    def call_rip(self, symbol: str) -> None:
        self.raw(b"\xFF\x15")
        self.rips.append((len(self.buf), symbol))
        self.buf += b"\0\0\0\0"

    def jmp_label(self, name: str) -> None:
        self.imm8(0xE9)
        self.jumps.append((len(self.buf), name))
        self.buf += b"\0\0\0\0"

    def jcc(self, cc: int, name: str) -> None:
        self.raw(bytes([0x0F, 0x80 + cc]))
        self.jumps.append((len(self.buf), name))
        self.buf += b"\0\0\0\0"

    def jz(self, name: str) -> None:
        self.jcc(0x04, name)

    def je(self, name: str) -> None:
        self.jz(name)

    def jnz(self, name: str) -> None:
        self.jcc(0x05, name)

    def jne(self, name: str) -> None:
        self.jnz(name)

    def jo(self, name: str) -> None:
        self.jcc(0x00, name)

    def jl(self, name: str) -> None:
        self.jcc(0x0C, name)

    def jge(self, name: str) -> None:
        self.jcc(0x0D, name)

    def jle(self, name: str) -> None:
        self.jcc(0x0E, name)

    def jg(self, name: str) -> None:
        self.jcc(0x0F, name)

    def jae(self, name: str) -> None:
        self.jcc(0x03, name)

    def jb(self, name: str) -> None:
        self.jcc(0x02, name)

    def ja(self, name: str) -> None:
        self.jcc(0x07, name)

    def jbe(self, name: str) -> None:
        self.jcc(0x06, name)

    def _alu_reg(self, opcode: int, dest: int, src: int) -> None:
        self.raw(_rex(1, dest, src))
        self.imm8(opcode)
        self.imm8(_modrm(3, dest, src))

    def add_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x03, dest, src)

    def sub_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x2B, dest, src)

    def cmp_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x3B, dest, src)

    def and_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x23, dest, src)

    def xor_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x33, dest, src)

    def or_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x0B, dest, src)

    def add_reg_imm8(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x83)
        self.imm8(_modrm(3, 0, dest))
        self.imm8(value)

    def add_reg_imm32(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x81)
        self.imm8(_modrm(3, 0, dest))
        self.buf += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def sub_reg_imm8(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x83)
        self.imm8(_modrm(3, 5, dest))
        self.imm8(value)

    def cmp_reg_imm32(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x81)
        self.imm8(_modrm(3, 7, dest))
        self.buf += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def cmp_reg_imm8(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x83)
        self.imm8(_modrm(3, 7, dest))
        self.imm8(value)

    def add_mem_reg(self, base: int, disp: int, src: int) -> None:
        self._emit_mem(1, b"\x01", src, base, disp)

    def add_mem_imm8(self, base: int, disp: int, value: int) -> None:
        self._emit_mem(1, b"\x83", 0, base, disp, bytes([value & 0xFF]))

    def inc_mem(self, base: int, disp: int) -> None:
        self._emit_mem(1, b"\xFF", 0, base, disp)

    def dec_mem(self, base: int, disp: int) -> None:
        self._emit_mem(1, b"\xFF", 1, base, disp)

    def imul_reg(self, dest: int, src: int) -> None:
        self.raw(_rex(1, dest, src))
        self.raw(b"\x0F\xAF")
        self.imm8(_modrm(3, dest, src))

    def imul_reg_imm8(self, dest: int, src: int, value: int) -> None:
        self.raw(_rex(1, dest, src))
        self.imm8(0x6B)
        self.imm8(_modrm(3, dest, src))
        self.imm8(value)

    def neg_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xF7)
        self.imm8(_modrm(3, 3, reg))

    def idiv_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xF7)
        self.imm8(_modrm(3, 7, reg))

    def cqo(self) -> None:
        self.raw(b"\x48\x99")

    def xor_eax(self) -> None:
        self.raw(b"\x31\xC0")

    def test_reg(self, dest: int, src: int) -> None:
        self.raw(_rex(1, dest, src))
        self.imm8(0x85)
        self.imm8(_modrm(3, dest, src))

    def movzx_reg_byte_mem(self, dest: int, base: int, disp: int = 0) -> None:
        self._emit_mem(0, b"\x0F\xB6", dest, base, disp, tight=True)

    def movzx_reg_byte_reg(self, dest: int, src: int) -> None:
        self.raw(_rex(0, dest, src))
        self.raw(b"\x0F\xB6")
        self.imm8(_modrm(3, dest, src))

    def mov_reg_byte_mem(self, dest: int, base: int, disp: int) -> None:
        self.movzx_reg_byte_mem(dest, base, disp)

    def jmp_sib(self, base: int, index: int) -> None:
        # jmp qword [base + index*8]
        self.raw(_rex(0, 0, base, index))
        self.imm8(0xFF)
        self.imm8(_modrm(0, 4, 4))
        self.imm8(((3 & 3) << 6) | ((index & 7) << 3) | (base & 7))

    def and_rsp_align(self) -> None:
        self.raw(b"\x48\x83\xE4\xF0")

    def sub_rsp_imm32(self, value: int) -> None:
        self.raw(b"\x48\x81\xEC")
        self.buf += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def add_rsp_imm32(self, value: int) -> None:
        self.raw(b"\x48\x81\xC4")
        self.buf += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def int3(self) -> None:
        self.imm8(0xCC)

    def call_label(self, name: str) -> None:
        self.imm8(0xE8)
        self.jumps.append((len(self.buf), name))
        self.buf += b"\0\0\0\0"

    def inc_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xFF)
        self.imm8(_modrm(3, 0, reg))

    def dec_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xFF)
        self.imm8(_modrm(3, 1, reg))

    def mov_reg_rip(self, dest: int, symbol: str) -> None:
        self.raw(_rex(1, dest, 0))
        self.imm8(0x8B)
        self.imm8(_modrm(0, dest, 5))
        self.rips.append((len(self.buf), symbol))
        self.buf += b"\0\0\0\0"

    def setcc(self, cc: int, reg: int) -> None:
        self.raw(_rex(0, 0, reg))
        self.raw(bytes([0x0F, cc]))
        self.imm8(_modrm(3, 0, reg))

    def movzx_reg_word_mem(self, dest: int, base: int, disp: int = 0) -> None:
        self._emit_mem(0, b"\x0F\xB7", dest, base, disp, tight=True)

    def movzx_reg_byte_index(self, dest: int, base: int, index: int) -> None:
        self.raw(_rex(0, dest, base, index))
        self.raw(b"\x0F\xB6")
        self.imm8(_modrm(0, dest, 4))
        self.imm8(((index & 7) << 3) | (base & 7))

    def mov_mem8_reg(self, base: int, disp: int, src: int) -> None:
        self._emit_mem(0, b"\x88", src, base, disp, tight=True)

    def movsxd_reg_mem(self, dest: int, base: int, disp: int = 0) -> None:
        self._emit_mem(1, b"\x63", dest, base, disp, tight=True)

    def and_reg_imm8(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x83)
        self.imm8(_modrm(3, 4, dest))
        self.imm8(value)

    def shl_reg_imm8(self, reg: int, value: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xC1)
        self.imm8(_modrm(3, 4, reg))
        self.imm8(value)

    def shr_reg_imm8(self, reg: int, value: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xC1)
        self.imm8(_modrm(3, 5, reg))
        self.imm8(value)

    def udiv_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xF7)
        self.imm8(_modrm(3, 6, reg))

    def mul_reg(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xF7)
        self.imm8(_modrm(3, 4, reg))

    def adc_reg(self, dest: int, src: int) -> None:
        self._alu_reg(0x13, dest, src)

    def adc_reg_imm8(self, dest: int, value: int) -> None:
        self.raw(_rex(1, 0, dest))
        self.imm8(0x83)
        self.imm8(_modrm(3, 2, dest))
        self.imm8(value)

    def sbb_reg_mem(self, dest: int, base: int, disp: int = 0) -> None:
        self._emit_mem(1, b"\x1B", dest, base, disp, tight=True)

    def clc(self) -> None:
        self.imm8(0xF8)

    def lahf(self) -> None:
        self.imm8(0x9F)

    def sahf(self) -> None:
        self.imm8(0x9E)

    def bsr_reg(self, dest: int, src: int) -> None:
        self.raw(_rex(1, dest, src))
        self.raw(b"\x0F\xBD")
        self.imm8(_modrm(3, dest, src))

    def shl_reg_cl(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xD3)
        self.imm8(_modrm(3, 4, reg))

    def shr_reg_cl(self, reg: int) -> None:
        self.raw(_rex(1, 0, reg))
        self.imm8(0xD3)
        self.imm8(_modrm(3, 5, reg))

    def movq_xmm_reg(self, xmm: int, reg: int) -> None:
        self.raw(b"\x66")
        self.raw(_rex(1, xmm, reg))
        self.raw(b"\x0F\x6E")
        self.imm8(_modrm(3, xmm, reg))

    def movq_reg_xmm(self, reg: int, xmm: int) -> None:
        self.raw(b"\x66")
        self.raw(_rex(1, xmm, reg))
        self.raw(b"\x0F\x7E")
        self.imm8(_modrm(3, xmm, reg))

    def _sse_bin(self, prefix: bytes, opcode: int, dest: int, src: int) -> None:
        self.raw(prefix)
        self.imm8(opcode)
        self.imm8(_modrm(3, dest, src))

    def addsd(self, dest: int, src: int) -> None:
        self._sse_bin(b"\xF2\x0F", 0x58, dest, src)

    def mulsd(self, dest: int, src: int) -> None:
        self._sse_bin(b"\xF2\x0F", 0x59, dest, src)

    def subsd(self, dest: int, src: int) -> None:
        self._sse_bin(b"\xF2\x0F", 0x5C, dest, src)

    def divsd(self, dest: int, src: int) -> None:
        self._sse_bin(b"\xF2\x0F", 0x5E, dest, src)

    def ucomisd(self, dest: int, src: int) -> None:
        self._sse_bin(b"\x66\x0F", 0x2E, dest, src)

    def cvtsi2sd(self, xmm: int, reg: int) -> None:
        self.raw(b"\xF2")
        self.raw(_rex(1, xmm, reg))
        self.raw(b"\x0F\x2A")
        self.imm8(_modrm(3, xmm, reg))

    def cvttsd2si(self, reg: int, xmm: int) -> None:
        self.raw(b"\xF2")
        self.raw(_rex(1, reg, xmm))
        self.raw(b"\x0F\x2C")
        self.imm8(_modrm(3, reg, xmm))

    def mov_rsp_reg(self, disp: int, src: int) -> None:
        self._rsp_mem(0x89, src, disp, 1)

    def mov_rsp_imm32(self, disp: int, value: int) -> None:
        self._rsp_mem(0xC7, 0, disp, 1, (value & 0xFFFFFFFF).to_bytes(4, "little"))

    def _mem_disp(self, base: int, disp: int) -> tuple[int, bytes]:
        if disp == 0 and base not in {RBP, R13}:
            return 0, b""
        return self._disp(disp if disp or base in {RBP, R13} else 0)

    def _rsp_mem(self, opcode: int, reg: int, disp: int, rex_w: int, imm: bytes = b"") -> None:
        mod, raw = self._disp(disp)
        self.raw(_rex(rex_w, reg, RSP))
        self.imm8(opcode)
        self.imm8(_modrm(mod, reg, 4))
        self.imm8(0x24)
        self.raw(raw)
        self.raw(imm)
