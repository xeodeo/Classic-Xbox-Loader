"""
analyze_oc3.py — análisis enfocado: callers de timing + constantes exactas
"""
import struct, builtins

OUT = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\analyze_oc3.txt"
_f  = open(OUT, 'w', encoding='utf-8')
_p  = builtins.print
def print(*a, **kw): kw['file'] = _f; _p(*a, **kw)

path = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
with open(path, 'rb') as f:
    data = f.read()

base_addr    = struct.unpack_from('<I', data, 0x104)[0]
num_sections = struct.unpack_from('<I', data, 0x11C)[0]
sect_hdrs_va = struct.unpack_from('<I', data, 0x120)[0]
hdrs_off     = sect_hdrs_va - base_addr

sections = []
for i in range(num_sections):
    b = hdrs_off + i * 56
    flags      = struct.unpack_from('<I', data, b+0)[0]
    va         = struct.unpack_from('<I', data, b+4)[0]
    virt_size  = struct.unpack_from('<I', data, b+8)[0]
    raw_offset = struct.unpack_from('<I', data, b+12)[0]
    raw_size   = struct.unpack_from('<I', data, b+16)[0]
    name_va    = struct.unpack_from('<I', data, b+20)[0]
    name_off   = name_va - base_addr
    end        = data.find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    is_code    = bool(flags & 0x04)
    sections.append(dict(idx=i, name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size, is_code=is_code))

CODE_SECTIONS = [s for s in sections if s['is_code']]

def off_to_sec(off):
    for s in sections:
        if s['raw_offset'] <= off < s['raw_offset'] + s['raw_size']:
            return s
    return None

def off_to_va(off):
    s = off_to_sec(off)
    return (s['va'] + (off - s['raw_offset'])) if s else None

def ctx(off, label, before=16, after=48):
    s  = off_to_sec(off)
    va = off_to_va(off)
    print(f"\n  [{s['name'] if s else '?'}]  {label}  file=0x{off:X}  VA=0x{va:08X}" if va else
          f"\n  [?]  {label}  file=0x{off:X}")
    chunk = data[max(0, off-before):off+after]
    base  = max(0, off-before)
    for row in range(0, len(chunk), 16):
        h = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        print(f"    {base+row:08X}: {h}{'  <<<' if base+row <= off < base+row+16 else ''}")

# ── 1. Buscar SOLO MOV reg,imm32 y PUSH imm32 con valores de frecuencia exactos ──
# Frecuencias exactas conocidas del Xbox:
FREQS = {
    733_333_333: "733MHz",
    800_000_000: "800MHz",
    850_000_000: "850MHz",
    900_000_000: "900MHz",
    913_000_000: "913MHz",
    950_000_000: "950MHz",
    1_000_000_000: "1GHz",
    # Derivadas comunes: ticks por frame (60fps, 30fps, etc.)
    733_333_333 // 60: "733MHz/60fps",
    733_333_333 // 30: "733MHz/30fps",
    733_333_333 // 24: "733MHz/24fps",
    733_333_333 // 1000: "733MHz/1ms",
}

print("=== 1. Busqueda de constantes de frecuencia exactas (MOV/PUSH imm32) ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 4):
        b0 = data[i]
        # MOV r32, imm32:  B8-BF xx xx xx xx
        # PUSH imm32:      68 xx xx xx xx
        # MOV [mem], imm32: C7 /0 xx xx xx xx  (2+ byte opcode)
        if b0 in (0x68, 0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF):
            v = struct.unpack_from('<I', data, i+1)[0]
            if v in FREQS:
                ctx(i, f"{FREQS[v]} ({v:,})")
        elif b0 == 0xC7 and (data[i+1] & 0x38) == 0:  # MOV [r/m], imm32
            # imm32 starts at i+2 (if ModRM is simple) or further
            # try at i+2 (reg indirect no disp) and i+6 (disp32)
            for extra in (2, 3, 6, 7):
                if i + extra + 4 <= len(data):
                    v = struct.unpack_from('<I', data, i+extra)[0]
                    if v in FREQS:
                        ctx(i, f"MOV[mem],{FREQS[v]} ({v:,}) @+{extra}")
                        break

# ── 2. Callers de las 2 funciones de timing conocidas ──
print("\n=== 2. Callers de freq_init (VA=0x17966) y RDTSC_store (VA=0x17951) ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 4):
        if data[i] == 0xE8:
            caller_va = off_to_va(i)
            if caller_va is None: continue
            rel = struct.unpack_from('<i', data, i+1)[0]
            target_va = caller_va + 5 + rel
            if target_va == 0x17966:
                ctx(i, f"CALL freq_init")
            elif target_va == 0x17951:
                ctx(i, f"CALL RDTSC_store")

# ── 3. RDTSC en secciones de codigo (con contexto amplio) ──
print("\n=== 3. RDTSC en secciones de codigo ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 1):
        if data[i] == 0x0F and data[i+1] == 0x31:
            ctx(i, "RDTSC", before=24, after=64)

# ── 4. Constante 733,333,333 en TODO el archivo (cualquier alineacion) ──
print("\n=== 4. Constante 733,333,333 en todo el archivo ===")
needle = struct.pack('<I', 733_333_333)
start, found = 0, 0
while True:
    idx = data.find(needle, start)
    if idx == -1: break
    ctx(idx, "733,333,333")
    start = idx + 1
    found += 1
print(f"  Total: {found}")

print("\nDone.")
_f.close()
_p(f"Output: {OUT}")
