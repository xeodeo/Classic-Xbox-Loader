#!/usr/bin/env python3
"""
XBE Intro Patcher
Patches Xbox executables (.xbe) to skip intro sequences.

Two strategies are detected automatically:
  1. String references  — finds .xmv/.bik/intro strings referenced in code via PUSH+CALL
  2. Entry point calls  — scans CALLs issued in the first ~2 KB from the entry point

Usage: python xbe_patcher.py
"""
import os
import struct
import shutil
import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QGroupBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QHeaderView, QCheckBox, QSplitter, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# ── XBE constants ──────────────────────────────────────────────────────────────
XBE_MAGIC         = b'XBEH'
ENTRY_XOR_RETAIL  = 0xA8FC57AB
ENTRY_XOR_DEBUG   = 0x94859D4B

# Strings that indicate intro/video content
VIDEO_PATTERNS = [
    b'.xmv', b'.XMV',
    b'.bik', b'.BIK',
    b'.wmv', b'.WMV',
    b'intro', b'Intro', b'INTRO',
    b'movie', b'Movie', b'MOVIE', b'movies', b'Movies',
    b'logo',  b'Logo',  b'LOGO',
    b'splash', b'Splash', b'SPLASH',
    b'attract', b'Attract',
    b'startup', b'Startup',
    b'opening', b'Opening', b'OPENING',
    b'preroll', b'PreRoll',
]

NOP = 0x90

# ── Minimal x86 instruction-length estimator ──────────────────────────────────
# Good enough to walk through code without going totally off the rails.

def _inst_size(data: bytes, i: int) -> int:
    if i >= len(data):
        return 1
    b  = data[i]
    b1 = data[i + 1] if i + 1 < len(data) else 0

    # Single-byte
    if b in (0x90, 0xC3, 0xC9, 0xCB, 0xCC):    return 1
    if 0x40 <= b <= 0x5F:                       return 1   # INC/DEC/PUSH/POP reg
    if b in (0xA4, 0xA5, 0xA6, 0xA7,
             0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF): return 1  # string ops
    # Two-byte
    if b in (0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77,
             0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F): return 2  # Jcc short
    if b == 0x6A:  return 2   # PUSH imm8
    if b == 0xEB:  return 2   # JMP short
    if b in (0x80, 0x83):     return 3   # ALU rm, imm8
    if b in (0xC0, 0xC1):     return 3   # Shift rm, imm8
    if b == 0xC2:             return 3   # RET imm16
    # Five-byte
    if b == 0x68:  return 5   # PUSH imm32
    if b == 0xE8:  return 5   # CALL rel32
    if b == 0xE9:  return 5   # JMP rel32
    if b in (0xA0, 0xA1, 0xA2, 0xA3): return 5  # MOV AL/EAX, [moffs32]
    if 0xB8 <= b <= 0xBF:     return 5   # MOV reg32, imm32
    if b in (0x81,):           return 6  # ALU rm32, imm32 (approximate)
    # ModRM-based (2-byte or more)
    if b in (0x84, 0x85, 0x86, 0x87,
             0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F,
             0x00, 0x01, 0x02, 0x03, 0x08, 0x09, 0x0A, 0x0B,
             0x20, 0x21, 0x22, 0x23, 0x28, 0x29, 0x2A, 0x2B,
             0x30, 0x31, 0x32, 0x33, 0x38, 0x39, 0x3A, 0x3B,
             0xD0, 0xD1, 0xD2, 0xD3):
        mod = (b1 >> 6) & 3
        rm  = b1 & 7
        if mod == 3:  return 2
        if mod == 0:  return 6 if rm == 5 else (3 if rm == 4 else 2)  # [SIB] or [disp32]
        if mod == 1:  return 3 + (1 if rm == 4 else 0)   # disp8
        if mod == 2:  return 6 + (1 if rm == 4 else 0)   # disp32
    if b == 0xFF:
        mod = (b1 >> 6) & 3
        rm  = b1 & 7
        if mod == 3:  return 2
        if mod == 0:  return 6 if rm == 5 else 2
        if mod == 1:  return 3
        if mod == 2:  return 6
    if b == 0x0F:  # Two-byte opcode prefix
        if 0x80 <= b1 <= 0x8F: return 6   # Jcc near
        if 0x90 <= b1 <= 0x9F: return 3   # SETcc
        return 3  # conservative fallback
    if b in (0xF2, 0xF3):
        return 1 + _inst_size(data, i + 1)
    return 1  # unknown — advance 1


# ── XBE parser ────────────────────────────────────────────────────────────────

class XBEParseError(Exception):
    pass


class XBESection:
    __slots__ = ('name', 'flags', 'va', 'virt_size', 'raw_offset', 'raw_size',
                 'is_code', 'is_write')

    def __init__(self, name, flags, va, virt_size, raw_offset, raw_size):
        self.name       = name
        self.flags      = flags
        self.va         = va
        self.virt_size  = virt_size
        self.raw_offset = raw_offset
        self.raw_size   = raw_size
        self.is_code    = bool(flags & 0x04)
        self.is_write   = bool(flags & 0x01)

    def contains_va(self, va: int) -> bool:
        return self.va <= va < self.va + self.virt_size

    def contains_offset(self, off: int) -> bool:
        return self.raw_offset <= off < self.raw_offset + self.raw_size


class XBEParser:
    def __init__(self, data: bytes):
        self.data        = data
        self.base_addr   = 0
        self.entry_point = 0
        self.is_debug    = False
        self.title       = ''
        self.sections: list[XBESection] = []
        self._parse()

    def _parse(self):
        d = self.data
        if len(d) < 0x180:
            raise XBEParseError("Archivo demasiado pequeño")
        if d[:4] != XBE_MAGIC:
            raise XBEParseError(f"Magic inválido: {d[:4]!r} (esperado 'XBEH')")

        self.base_addr = struct.unpack_from('<I', d, 0x104)[0]
        cert_va        = struct.unpack_from('<I', d, 0x118)[0]
        num_sections   = struct.unpack_from('<I', d, 0x11C)[0]
        sect_hdrs_va   = struct.unpack_from('<I', d, 0x120)[0]
        ep_xored       = struct.unpack_from('<I', d, 0x128)[0]

        # Determine build type: try both XOR keys, pick the one whose result
        # lands closest to base_addr (within 32 MB — a generous range).
        ep_r = (ep_xored ^ ENTRY_XOR_RETAIL) & 0xFFFFFFFF
        ep_d = (ep_xored ^ ENTRY_XOR_DEBUG)  & 0xFFFFFFFF
        dist_r = abs(ep_r - self.base_addr)
        dist_d = abs(ep_d - self.base_addr)
        if dist_r <= dist_d and dist_r < 0x2000000:
            self.entry_point = ep_r
            self.is_debug    = False
        else:
            self.entry_point = ep_d
            self.is_debug    = True

        # Parse section headers (each 56 bytes)
        hdrs_off = sect_hdrs_va - self.base_addr
        if hdrs_off < 0 or hdrs_off + num_sections * 56 > len(d):
            raise XBEParseError("Cabeceras de sección fuera de rango")

        for i in range(num_sections):
            base       = hdrs_off + i * 56
            flags      = struct.unpack_from('<I', d, base + 0)[0]
            va         = struct.unpack_from('<I', d, base + 4)[0]
            virt_size  = struct.unpack_from('<I', d, base + 8)[0]
            raw_offset = struct.unpack_from('<I', d, base + 12)[0]
            raw_size   = struct.unpack_from('<I', d, base + 16)[0]
            name_va    = struct.unpack_from('<I', d, base + 20)[0]
            name       = self._cstr_va(name_va)
            self.sections.append(
                XBESection(name, flags, va, virt_size, raw_offset, raw_size))

        # Read game title from certificate (+0x08, UTF-16LE, 40 chars)
        if cert_va >= self.base_addr:
            cert_off = cert_va - self.base_addr
            if cert_off + 0x08 + 80 <= len(d):
                try:
                    raw = d[cert_off + 0x08: cert_off + 0x08 + 80]
                    self.title = raw.decode('utf-16-le').rstrip('\x00')
                except Exception:
                    pass

    def _cstr_va(self, va: int) -> str:
        if va < self.base_addr:
            return ''
        off = va - self.base_addr
        if off >= len(self.data):
            return ''
        end = self.data.find(b'\x00', off)
        if end == -1:
            end = off + 64
        try:
            return self.data[off:min(end, off + 64)].decode('ascii', errors='replace')
        except Exception:
            return ''

    def va_to_offset(self, va: int) -> int:
        for s in self.sections:
            if s.contains_va(va):
                return s.raw_offset + (va - s.va)
        if self.base_addr <= va < self.base_addr + 0x1000:
            return va - self.base_addr
        return -1

    def offset_to_va(self, offset: int) -> int:
        for s in self.sections:
            if s.contains_offset(offset):
                return s.va + (offset - s.raw_offset)
        return -1

    def code_sections(self) -> list[XBESection]:
        return [s for s in self.sections if s.is_code and s.raw_size > 0]


# ── Patch target ──────────────────────────────────────────────────────────────

class PatchTarget:
    """One patchable location in the XBE file."""
    __slots__ = ('strategy', 'description', 'context',
                 'offset', 'size', 'enabled', 'original')

    def __init__(self, strategy: str, description: str, context: str,
                 offset: int, size: int, enabled: bool = True):
        self.strategy    = strategy     # 'string_ref' | 'entry_call'
        self.description = description
        self.context     = context
        self.offset      = offset       # file offset to start NOP-ing
        self.size        = size         # how many bytes to NOP
        self.enabled     = enabled
        self.original    = b''          # saved when patch is applied


# ── Background analysis worker ────────────────────────────────────────────────

class AnalyzeWorker(QThread):
    log_line = pyqtSignal(str, str)              # message, color
    finished = pyqtSignal(list, dict)            # patches, info
    failed   = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            with open(self.path, 'rb') as f:
                data = f.read()

            self._log(f"Cargado: {os.path.basename(self.path)}  ({len(data):,} bytes)", '#9e9e9e')

            parser = XBEParser(data)

            info = {
                'title':    parser.title or '(sin titulo)',
                'build':    'Debug' if parser.is_debug else 'Retail',
                'base':     f"0x{parser.base_addr:08X}",
                'entry':    f"0x{parser.entry_point:08X}",
                'sections': len(parser.sections),
            }

            self._log(f"Titulo : {info['title']}", '#cccccc')
            self._log(f"Build  : {info['build']}  |  Base: {info['base']}  |  Entry: {info['entry']}", '#cccccc')
            sects = ', '.join(
                f"{s.name}({'C' if s.is_code else 'D'})" for s in parser.sections)
            self._log(f"Secciones [{len(parser.sections)}]: {sects}", '#555555')

            patches: list[PatchTarget] = []

            # ── Strategy 1: string references ─────────────────────────────────
            self._log('\n[Estrategia 1] Buscando strings de video en el binario...', '#f7630c')
            s1 = self._find_string_refs(data, parser)
            if s1:
                self._log(f'  → {len(s1)} referencia(s) encontrada(s).', '#107c10')
                patches.extend(s1)
            else:
                self._log('  → Ninguna referencia de string detectada.', '#555555')

            # ── Strategy 2: entry-point calls ─────────────────────────────────
            self._log('\n[Estrategia 2] Escaneando CALLs desde el entry point...', '#f7630c')
            s2 = self._scan_entry_calls(data, parser)
            if s2:
                self._log(f'  → {len(s2)} CALL(s) encontrada(s).', '#107c10')
                patches.extend(s2)
            else:
                self._log('  → No se encontraron CALLs en el entry point.', '#555555')

            if patches:
                self._log(f'\n✅ Total: {len(patches)} objetivo(s) de parche detectados.', '#107c10')
                if s1:
                    self._log('  Recomendacion: usa Estrategia 1 primero (mas precisa).', '#9e9e9e')
                else:
                    self._log('  Recomendacion: prueba las primeras 1-3 CALLs del entry point.', '#9e9e9e')
            else:
                self._log('\n⚠  No se detectaron objetivos. El XBE puede no tener intros parcheables facilmente.', '#f7630c')

            self.finished.emit(patches, info)

        except XBEParseError as e:
            self.failed.emit(f'Error XBE: {e}')
        except Exception as e:
            self.failed.emit(f'Error inesperado: {type(e).__name__}: {e}')

    # ── Strategy 1 helpers ────────────────────────────────────────────────────

    def _find_string_refs(self, data: bytes, parser: XBEParser) -> list[PatchTarget]:
        patches  = []
        seen_str = set()      # deduplicate string offsets
        seen_push = set()     # deduplicate PUSH locations

        for pattern in VIDEO_PATTERNS:
            pos = 0
            while True:
                idx = data.find(pattern, pos)
                if idx == -1:
                    break
                pos = idx + 1

                # Walk back to find the start of the full string
                s_start = idx
                limit   = max(0, idx - 256)
                while s_start > limit and data[s_start - 1] not in (0x00,) and 0x20 <= data[s_start - 1] < 0x80:
                    s_start -= 1
                if s_start in seen_str:
                    continue
                seen_str.add(s_start)

                # Walk forward to the null terminator
                s_end = idx
                while s_end < len(data) and data[s_end] != 0:
                    s_end += 1
                full_str = data[s_start:s_end].decode('ascii', errors='replace')
                if len(full_str) < 4:
                    continue

                str_va = parser.offset_to_va(s_start)
                if str_va == -1:
                    continue

                self._log(f'  String: "{full_str}" @ VA 0x{str_va:08X}', '#555555')

                # Look for PUSH str_va in every code section
                push_bytes = bytes([0x68]) + struct.pack('<I', str_va)
                for sect in parser.code_sections():
                    sect_raw = data[sect.raw_offset: sect.raw_offset + sect.raw_size]
                    p = 0
                    while True:
                        rel_idx = sect_raw.find(push_bytes, p)
                        if rel_idx == -1:
                            break
                        p = rel_idx + 1
                        abs_off = sect.raw_offset + rel_idx
                        if abs_off in seen_push:
                            continue
                        seen_push.add(abs_off)

                        push_va = sect.va + rel_idx

                        # Find the CALL that follows within 64 bytes
                        call_rel, call_sz = self._next_call(sect_raw, rel_idx + 5, 64)
                        if call_rel != -1:
                            patch_start = abs_off
                            patch_end   = sect.raw_offset + call_rel + call_sz
                            patch_size  = patch_end - patch_start
                            call_va     = sect.va + call_rel

                            # Resolve CALL target if possible (only for E8 rel32)
                            call_target = ''
                            if sect_raw[call_rel] == 0xE8 and call_rel + 4 < len(sect_raw):
                                rel32  = struct.unpack_from('<i', sect_raw, call_rel + 1)[0]
                                t_va   = call_va + 5 + rel32
                                call_target = f' → 0x{t_va & 0xFFFFFFFF:08X}'

                            desc    = f'PUSH+CALL — "{full_str[:38]}"'
                            context = (f'PUSH @ VA 0x{push_va:08X} | '
                                       f'CALL @ VA 0x{call_va:08X}{call_target} | '
                                       f'seccion [{sect.name}] | {patch_size} bytes')
                            self._log(f'    PUSH 0x{push_va:08X} + CALL 0x{call_va:08X}{call_target} — {patch_size} bytes a NOP', '#107c10')
                            patches.append(PatchTarget('string_ref', desc, context, patch_start, patch_size))
                        else:
                            # Only the PUSH, no CALL nearby — patch PUSH alone
                            desc    = f'PUSH — "{full_str[:42]}" (sin CALL cercana)'
                            context = f'PUSH @ VA 0x{push_va:08X} | seccion [{sect.name}]'
                            self._log(f'    PUSH 0x{push_va:08X} (sin CALL) — 5 bytes a NOP', '#9e9e9e')
                            patches.append(PatchTarget('string_ref', desc, context, abs_off, 5, enabled=False))

        return patches

    def _next_call(self, code: bytes, start: int, window: int) -> tuple[int, int]:
        """Return (offset_in_section, instr_size) of the next CALL, or (-1, 0)."""
        end = min(start + window, len(code))
        for i in range(start, end):
            b  = code[i]
            b1 = code[i + 1] if i + 1 < len(code) else 0
            if b == 0xE8:                   return i, 5  # CALL rel32
            if b == 0xFF and b1 == 0x15:    return i, 6  # CALL [mem32]
            if b == 0xFF and b1 in (0xD0, 0xD1, 0xD2, 0xD3,
                                    0xD4, 0xD5, 0xD6, 0xD7):
                return i, 2  # CALL reg
        return -1, 0

    # ── Strategy 2 helpers ────────────────────────────────────────────────────

    def _scan_entry_calls(self, data: bytes, parser: XBEParser) -> list[PatchTarget]:
        ep_off = parser.va_to_offset(parser.entry_point)
        if ep_off == -1:
            self._log(f'  Entry point 0x{parser.entry_point:08X} no está en ninguna seccion.', '#c42b1c')
            return []

        patches: list[PatchTarget] = []
        i       = ep_off
        limit   = ep_off + 2048
        call_n  = 0

        while i < min(limit, len(data)) and call_n < 15:
            b  = data[i]
            b1 = data[i + 1] if i + 1 < len(data) else 0

            if b == 0xC3 or b == 0xC9:    # RET / LEAVE — stop
                break

            if b == 0xE8 and i + 4 < len(data):
                rel    = struct.unpack_from('<i', data, i + 1)[0]
                tgt_va = (parser.offset_to_va(i) + 5 + rel) & 0xFFFFFFFF
                call_n += 1
                pre_select = call_n <= 4  # pre-select first 4 as candidates
                desc    = f'CALL #{call_n} (rel32) → 0x{tgt_va:08X}'
                context = f'Offset 0x{i:X} | VA 0x{parser.offset_to_va(i):08X} | destino 0x{tgt_va:08X}'
                self._log(f'  CALL #{call_n} @ 0x{i:X} → 0x{tgt_va:08X}', '#9e9e9e')
                patches.append(PatchTarget('entry_call', desc, context, i, 5, enabled=pre_select))
                i += 5

            elif b == 0xFF and b1 == 0x15 and i + 5 < len(data):
                addr   = struct.unpack_from('<I', data, i + 2)[0]
                call_n += 1
                pre_select = call_n <= 4
                desc    = f'CALL #{call_n} [mem] → [0x{addr:08X}]'
                context = f'Offset 0x{i:X} | VA 0x{parser.offset_to_va(i):08X} | indirecto [0x{addr:08X}]'
                self._log(f'  CALL #{call_n} [mem] @ 0x{i:X} → [0x{addr:08X}]', '#9e9e9e')
                patches.append(PatchTarget('entry_call', desc, context, i, 6, enabled=pre_select))
                i += 6

            elif b == 0xFF and b1 in (0xD0, 0xD1, 0xD2, 0xD3):
                call_n += 1
                reg_names = {0xD0: 'EAX', 0xD1: 'ECX', 0xD2: 'EDX', 0xD3: 'EBX'}
                reg    = reg_names.get(b1, f'r{b1 & 7}')
                desc    = f'CALL #{call_n} reg ({reg})'
                context = f'Offset 0x{i:X} | VA 0x{parser.offset_to_va(i):08X} | CALL {reg}'
                self._log(f'  CALL #{call_n} reg ({reg}) @ 0x{i:X}', '#9e9e9e')
                patches.append(PatchTarget('entry_call', desc, context, i, 2, enabled=False))
                i += 2

            else:
                i += _inst_size(data, i)

        return patches

    def _log(self, msg: str, color: str = '#cccccc'):
        self.log_line.emit(msg, color)


# ── Main window ───────────────────────────────────────────────────────────────

_STYLE = """
QMainWindow, QWidget          { background: #1a1a1a; color: #cccccc; }
QGroupBox                     { border: 1px solid #2a2a2a; border-radius: 6px;
                                margin-top: 8px; padding-top: 10px;
                                font-weight: bold; color: #9e9e9e; font-size: 12px; }
QGroupBox::title              { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton                   { background: #252525; color: #cccccc; border: 1px solid #3a3a3a;
                                border-radius: 5px; padding: 6px 14px; font-size: 12px; }
QPushButton:hover             { background: #2f2f2f; border-color: #555; }
QPushButton:disabled          { background: #1a1a1a; color: #444; border-color: #2a2a2a; }
QPushButton#primary           { background: #107c10; color: white; border: none; }
QPushButton#primary:hover     { background: #13a10e; }
QPushButton#primary:disabled  { background: #0d3d0d; color: #456345; border: none; }
QPushButton#danger            { background: #7a1010; color: white; border: none; }
QPushButton#danger:hover      { background: #a01010; }
QPushButton#warn              { background: #7a4a10; color: white; border: none; }
QPushButton#warn:hover        { background: #9a6010; }
QTableWidget                  { background: #0d0d0d; gridline-color: #222;
                                border: 1px solid #2a2a2a; border-radius: 4px;
                                selection-background-color: #1e3a1e; }
QTableWidget::item            { padding: 3px 6px; }
QHeaderView::section          { background: #1a1a1a; color: #777; border: none;
                                border-bottom: 1px solid #2a2a2a; padding: 4px 6px; }
QTextEdit                     { background: #0d0d0d; color: #cccccc;
                                border: 1px solid #2a2a2a; border-radius: 4px;
                                font-family: Consolas, monospace; font-size: 11px; }
QScrollBar:vertical           { background: #1a1a1a; width: 7px; }
QScrollBar::handle:vertical   { background: #3a3a3a; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel                        { color: #cccccc; }
QCheckBox                     { color: #cccccc; }
QCheckBox::indicator          { width: 14px; height: 14px; border: 1px solid #3a3a3a;
                                background: #252525; border-radius: 3px; }
QCheckBox::indicator:checked  { background: #107c10; border-color: #13a10e; }
QSplitter::handle             { background: #2a2a2a; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XBE Intro Patcher")
        self.setMinimumSize(860, 620)
        self.resize(1060, 740)
        self.setStyleSheet(_STYLE)

        self._xbe_path   = ''
        self._patches:   list[PatchTarget]   = []
        self._checkboxes: list[QCheckBox]    = []
        self._worker:    AnalyzeWorker | None = None

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(16, 14, 16, 14)
        vbox.setSpacing(10)

        # Header
        h_row = QHBoxLayout()
        title_lbl = QLabel("XBE Intro Patcher")
        tf = QFont('Segoe UI', 15)
        tf.setBold(True)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet("color: #107c10;")
        h_row.addWidget(title_lbl)
        h_row.addStretch()
        sub_lbl = QLabel("Detecta y parchea intro-sequences en ejecutables Xbox")
        sub_lbl.setStyleSheet("color: #555; font-size: 11px;")
        h_row.addWidget(sub_lbl)
        vbox.addLayout(h_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #2a2a2a;")
        sep.setFixedHeight(1)
        vbox.addWidget(sep)

        # File selector row
        fr = QHBoxLayout()
        self._path_lbl = QLabel("Ningun archivo seleccionado")
        self._path_lbl.setStyleSheet("color: #555; font-size: 11px; font-family: Consolas;")
        fr.addWidget(self._path_lbl, 1)
        open_btn = QPushButton("  Abrir XBE...")
        open_btn.setObjectName("primary")
        open_btn.setMinimumHeight(34)
        open_btn.clicked.connect(self._open_file)
        fr.addWidget(open_btn)
        vbox.addLayout(fr)

        # Splitter: top (info + table) / bottom (log)
        splitter = QSplitter(Qt.Orientation.Vertical)

        top = QWidget()
        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(0, 0, 0, 0)
        top_h.setSpacing(10)

        # XBE info panel
        info_grp = QGroupBox("Info XBE")
        info_grp.setMinimumWidth(190)
        info_grp.setMaximumWidth(230)
        info_l = QVBoxLayout(info_grp)
        info_l.setSpacing(6)
        self._info: dict[str, QLabel] = {}
        for key in ('Titulo', 'Build', 'Base', 'Entry', 'Secciones'):
            row = QHBoxLayout()
            kl = QLabel(f"{key}:")
            kl.setStyleSheet("color: #666; font-size: 11px;")
            kl.setMinimumWidth(70)
            vl = QLabel("—")
            vl.setStyleSheet("color: #ccc; font-size: 11px; font-family: Consolas;")
            vl.setWordWrap(True)
            row.addWidget(kl)
            row.addWidget(vl, 1)
            info_l.addLayout(row)
            self._info[key] = vl
        info_l.addStretch()
        top_h.addWidget(info_grp)

        # Patch targets table
        tbl_grp = QGroupBox("Objetivos de parche detectados")
        tbl_l = QVBoxLayout(tbl_grp)
        tbl_l.setSpacing(6)

        tbtn_row = QHBoxLayout()
        sel_btn = QPushButton("Seleccionar todo")
        sel_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checkboxes])
        desel_btn = QPushButton("Deseleccionar todo")
        desel_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes])
        tbtn_row.addWidget(sel_btn)
        tbtn_row.addWidget(desel_btn)
        tbtn_row.addStretch()
        tbl_l.addLayout(tbtn_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["✓", "Estrategia", "Descripcion", "Offset arch.", "Bytes"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 32)
        self._table.setColumnWidth(1, 95)
        self._table.setColumnWidth(3, 95)
        self._table.setColumnWidth(4, 60)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { alternate-background-color: #111111; }")
        tbl_l.addWidget(self._table)

        top_h.addWidget(tbl_grp, 1)
        splitter.addWidget(top)

        # Log
        log_grp = QGroupBox("Log de analisis")
        log_l = QVBoxLayout(log_grp)
        log_l.setContentsMargins(6, 6, 6, 6)
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setMinimumHeight(100)
        log_l.addWidget(self._log_box)
        splitter.addWidget(log_grp)
        splitter.setSizes([440, 180])

        vbox.addWidget(splitter, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("  Aplicar parches seleccionados")
        self._apply_btn.setObjectName("primary")
        self._apply_btn.setMinimumHeight(36)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_patches)
        btn_row.addWidget(self._apply_btn)

        self._restore_btn = QPushButton("Restaurar backup (.bak)")
        self._restore_btn.setObjectName("warn")
        self._restore_btn.setMinimumHeight(36)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._restore_backup)
        btn_row.addWidget(self._restore_btn)

        btn_row.addStretch()

        clr_btn = QPushButton("Limpiar log")
        clr_btn.clicked.connect(self._log_box.clear)
        btn_row.addWidget(clr_btn)
        vbox.addLayout(btn_row)

    # ── File open ─────────────────────────────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir XBE", "", "Xbox Executable (*.xbe);;Todos los archivos (*)")
        if not path:
            return
        self._xbe_path = path
        self._path_lbl.setText(path)
        self._patches.clear()
        self._checkboxes.clear()
        self._table.setRowCount(0)
        for v in self._info.values():
            v.setText("—")
        self._apply_btn.setEnabled(False)
        self._restore_btn.setEnabled(os.path.exists(path + '.bak'))

        self._log(f"=== {os.path.basename(path)} ===", '#107c10')
        self._worker = AnalyzeWorker(path)
        self._worker.log_line.connect(self._log)
        self._worker.finished.connect(self._on_analyzed)
        self._worker.failed.connect(lambda e: self._log(f"ERROR: {e}", '#c42b1c'))
        self._worker.start()

    # ── Analysis result ───────────────────────────────────────────────────────

    def _on_analyzed(self, patches: list[PatchTarget], info: dict):
        self._info['Titulo'].setText(info['title'])
        self._info['Build'].setText(info['build'])
        self._info['Base'].setText(info['base'])
        self._info['Entry'].setText(info['entry'])
        self._info['Secciones'].setText(str(info['sections']))

        self._patches     = patches
        self._checkboxes  = []
        self._table.setRowCount(0)

        STRAT_COLOR = {'string_ref': '#13a10e', 'entry_call': '#f7870c'}
        STRAT_LABEL = {'string_ref': 'Str. Ref', 'entry_call': 'Entry CALL'}

        for pt in patches:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, 26)

            # Checkbox (column 0)
            cb = QCheckBox()
            cb.setChecked(pt.enabled)
            cw = QWidget()
            cl = QHBoxLayout(cw)
            cl.addWidget(cb)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 0, cw)
            self._checkboxes.append(cb)

            # Strategy label (column 1)
            st = QTableWidgetItem(STRAT_LABEL.get(pt.strategy, pt.strategy))
            st.setForeground(QColor(STRAT_COLOR.get(pt.strategy, '#ccc')))
            self._table.setItem(row, 1, st)

            # Description (column 2)
            di = QTableWidgetItem(pt.description)
            di.setToolTip(pt.context)
            di.setForeground(QColor('#cccccc'))
            self._table.setItem(row, 2, di)

            # Offset (column 3)
            oi = QTableWidgetItem(f"0x{pt.offset:X}")
            oi.setForeground(QColor('#777'))
            oi.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, oi)

            # Size (column 4)
            si = QTableWidgetItem(f"{pt.size}B")
            si.setForeground(QColor('#777'))
            si.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, si)

        self._apply_btn.setEnabled(bool(patches))

    # ── Apply patches ─────────────────────────────────────────────────────────

    def _apply_patches(self):
        if not self._xbe_path:
            return
        selected = [p for p, cb in zip(self._patches, self._checkboxes) if cb.isChecked()]
        if not selected:
            self._log("No hay parches seleccionados.", '#f7630c')
            return

        # Backup (only if it doesn't already exist)
        bak = self._xbe_path + '.bak'
        if not os.path.exists(bak):
            shutil.copy2(self._xbe_path, bak)
            self._log(f"Backup creado: {os.path.basename(bak)}", '#9e9e9e')
            self._restore_btn.setEnabled(True)

        with open(self._xbe_path, 'rb') as f:
            data = bytearray(f.read())

        ok = 0
        for pt in selected:
            end = pt.offset + pt.size
            if end > len(data):
                self._log(f"  Offset 0x{pt.offset:X} fuera de rango — saltado", '#f7630c')
                continue
            pt.original = bytes(data[pt.offset:end])
            data[pt.offset:end] = bytes([NOP] * pt.size)
            self._log(f"  NOP x{pt.size} @ 0x{pt.offset:X}  |  {pt.description[:55]}", '#107c10')
            ok += 1

        with open(self._xbe_path, 'wb') as f:
            f.write(data)

        self._log(f"\n✅ {ok} parche(s) aplicados — archivo guardado.", '#107c10')
        self._log("Prueba en el Xbox. Si no arranca, usa 'Restaurar backup'.", '#9e9e9e')

    # ── Restore backup ────────────────────────────────────────────────────────

    def _restore_backup(self):
        if not self._xbe_path:
            return
        bak = self._xbe_path + '.bak'
        if not os.path.exists(bak):
            self._log("No hay backup disponible.", '#c42b1c')
            return
        shutil.copy2(bak, self._xbe_path)
        self._log("✅ XBE original restaurado desde backup.", '#107c10')

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, color: str = '#cccccc'):
        self._log_box.append(f'<span style="color:{color};">{msg}</span>')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
