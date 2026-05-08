"""
analyze_oc4.py — busca callers del wrapper RDTSC en D3D y contexto de uso
"""
import struct, builtins

OUT = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\analyze_oc4.txt"
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

def off_to_sec(off):
    for s in sections:
        if s['raw_offset'] <= off < s['raw_offset'] + s['raw_size']:
            return s
    return None

def off_to_va(off):
    s = off_to_sec(off)
    return (s['va'] + (off - s['raw_offset'])) if s else None

def ctx(off, label, before=8, after=80):
    s  = off_to_sec(off)
    va = off_to_va(off)
    print(f"\n  [{s['name'] if s else '?'}]  {label}  file=0x{off:X}  VA=0x{va:08X}" if va else
          f"\n  [?]  {label}  file=0x{off:X}")
    chunk = data[max(0, off-before):off+after]
    base  = max(0, off-before)
    for row in range(0, len(chunk), 16):
        h = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        print(f"    {base+row:08X}: {h}{'  <<<' if base+row <= off < base+row+16 else ''}")

# Funciones de timing conocidas
# D3D RDTSC wrapper: VA=0x2F2F0  (0F 31 C3 — RDTSC; RET)
# .text RDTSC_store: función empieza en VA=0x1794D
# .text freq_init:   función empieza en VA=0x1795E

TARGET_VAS = {
    0x2F2F0:  "D3D_RDTSC",
    0x1794D:  "RDTSC_store",
    0x1795E:  "freq_init",
    0x17966:  "freq_init+8",   # por si acaso hay CALLs al medio
}

print("=== Callers de funciones RDTSC/timing (buscando en TODAS las secciones) ===")
total = 0
for s in sections:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 4):
        if data[i] == 0xE8:
            caller_va = off_to_va(i)
            if caller_va is None: continue
            rel = struct.unpack_from('<i', data, i+1)[0]
            target_va = caller_va + 5 + rel
            if target_va in TARGET_VAS:
                ctx(i, f"CALL {TARGET_VAS[target_va]} (VA=0x{target_va:X})")
                total += 1
print(f"\nTotal callers encontrados: {total}")

# Buscar tambien CALLs indirectos a D3D_RDTSC via tabla (FF 15 / FF 10 / FF D0)
print("\n=== Busqueda adicional: JMP/CALL indirecto cerca de VA=0x2F2F0 ===")
# Buscar la VA 0x2F2F0 almacenada como DWORD en datos
needle = struct.pack('<I', 0x0002F2F0)
start = 0
while True:
    idx = data.find(needle, start)
    if idx == -1: break
    ctx(idx, "VA=0x2F2F0 en datos")
    start = idx + 1

# Mostrar el codigo completo del D3D RDTSC wrapper y los 200 bytes DESPUES
print("\n=== D3D RDTSC wrapper y codigo siguiente (200 bytes) ===")
rdtsc_d3d_file = 0x1F470
ctx(rdtsc_d3d_file, "D3D_RDTSC", before=4, after=200)

# Mostrar codigo completo de freq_init con mas contexto
print("\n=== freq_init completa y codigo siguiente (150 bytes) ===")
ctx(0x795E, "freq_init start", before=4, after=150)

# Buscar patrones: comparacion de delta RDTSC contra valor fijo
# Patron tipico: sub eax,edx  cmp eax,IMM32  jg/jl
# Buscamos CMP EAX/ECX/EDX, imm32 (3D/81) con valor entre 1M y 100M ticks
# (equivale a 1ms-100ms a 733MHz o 1GHz)
print("\n=== CMP reg, imm32 con valores 1M-100M (posibles timeouts de timing) ===")
count = 0
for s in sections:
    if not s['is_code']: continue
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 4):
        b0 = data[i]
        imm = None
        # 3D imm32  → CMP EAX, imm32
        if b0 == 0x3D:
            imm = struct.unpack_from('<I', data, i+1)[0]
        # 81 /7 imm32 → CMP r/m32, imm32
        elif b0 == 0x81 and (data[i+1] & 0x38) == 0x38:
            imm = struct.unpack_from('<I', data, i+2)[0]
        if imm is not None and 1_000_000 <= imm <= 200_000_000:
            count += 1
            if count <= 40:
                ctx(i, f"CMP *,{imm:,}  ({imm/913e6*1000:.2f}ms @913MHz / {imm/733e6*1000:.2f}ms @733MHz)")
print(f"\nTotal CMP con valores timing: {count}")

print("\nDone.")
_f.close()
_p(f"Output: {OUT}")
