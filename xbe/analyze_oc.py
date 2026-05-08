"""
analyze_oc.py — busca patrones relacionados con frecuencia de CPU / timing
en el XBE de Half-Life 2 Xbox.

Constantes conocidas del Xbox:
  733 333 333 Hz = 0x2BAF_9800   (frecuencia nominal del CPU)
  733 333 333 Hz como float = ?
  KeTickCount / KeQueryPerformanceFrequency usan 0x2BAF9800 internamente
  El PIT / HPET del MCPX corre a 3 375 000 Hz = 0x33_7A58
  Bus clock = 133 MHz = 0x07_E9_00_00 (aprox)
"""
import struct, re

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
    va         = struct.unpack_from('<I', data, b+4)[0]
    virt_size  = struct.unpack_from('<I', data, b+8)[0]
    raw_offset = struct.unpack_from('<I', data, b+12)[0]
    raw_size   = struct.unpack_from('<I', data, b+16)[0]
    name_va    = struct.unpack_from('<I', data, b+20)[0]
    name_off   = name_va - base_addr
    end        = data.find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    sections.append(dict(name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size))
    print(f"  [{i}] {name:20s}  VA=0x{va:08X}  raw=0x{raw_offset:X}  size=0x{raw_size:X}")

def find_all(needle):
    results = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx == -1: break
        results.append(idx)
        start = idx + 1
    return results

def off_to_va(off):
    for s in sections:
        if s['raw_offset'] <= off < s['raw_offset'] + s['raw_size']:
            return s['va'] + (off - s['raw_offset'])
    return None

def show_ctx(off, label, before=16, after=32):
    va = off_to_va(off)
    va_str = f"VA=0x{va:08X}" if va else "VA=?"
    print(f"\n  >>> {label}  file=0x{off:X}  {va_str}")
    chunk = data[off-before:off+after]
    for row in range(0, len(chunk), 16):
        abs_off = off - before + row
        h = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        marker = " <<<<" if abs_off == off else ""
        print(f"    {abs_off:08X}: {h}{marker}")

print("\n\n=== 1. Constante 733 MHz (0x2BAF9800) ===")
hits = find_all(struct.pack('<I', 733_333_333))
if hits:
    for h in hits: show_ctx(h, "733333333")
else:
    print("  no encontrada como DWORD LE")

print("\n=== 2. Constante 733 MHz como DWORD BE ===")
hits = find_all(struct.pack('>I', 733_333_333))
if hits:
    for h in hits: show_ctx(h, "733333333 BE")
else:
    print("  no encontrada como DWORD BE")

print("\n=== 3. Constante bus 133 MHz (0x07E90000) ===")
hits = find_all(struct.pack('<I', 133_000_000))
for h in hits: show_ctx(h, "133MHz")

print("\n=== 4. Instruccion RDTSC (0F 31) ===")
hits = find_all(b'\x0F\x31')
if hits:
    for h in hits: show_ctx(h, "RDTSC", before=8, after=24)
else:
    print("  no encontrada")

print("\n=== 5. MOV EAX, imm32 con valores cercanos a 733MHz (0x28000000 - 0x30000000) ===")
# B8 xx xx xx xx  MOV EAX, imm32
for off in range(len(data)-4):
    if data[off] == 0xB8:
        v = struct.unpack_from('<I', data, off+1)[0]
        if 0x28000000 <= v <= 0x30000000:
            show_ctx(off, f"MOV EAX,0x{v:08X}")

print("\n=== 6. Importaciones del kernel (XTL/kernel thunks) ===")
# Importaciones del kernel en el XBE: tabla en header offset 0x11C+...
# Kernel image thunks VA @ 0x15C
kt_va = struct.unpack_from('<I', data, 0x15C)[0]
XOR_RETAIL = 0x5B696969
kt_va_real = kt_va ^ XOR_RETAIL
print(f"  Kernel thunk table  (XOR retail): VA=0x{kt_va:08X}  real=0x{kt_va_real:08X}")

print("\n=== 7. Patron DIV/IDIV con registros (timing division) ===")
# F7 /6 (DIV r/m32) or F7 /7 (IDIV r/m32)
div_count = 0
for off in range(len(data)-1):
    b0 = data[off]
    if b0 == 0xF7:
        modrm = data[off+1]
        reg = (modrm >> 3) & 7
        if reg in (6, 7):  # DIV or IDIV
            va = off_to_va(off)
            va_str = f"0x{va:08X}" if va else "?"
            s_name = next((s['name'] for s in sections
                           if s['raw_offset'] <= off < s['raw_offset']+s['raw_size']), '?')
            if div_count < 20:
                print(f"  {'DIV ' if reg==6 else 'IDIV'} @ file=0x{off:X}  VA={va_str}  sec={s_name}")
            div_count += 1
print(f"  Total DIV/IDIV: {div_count}")

print("\nDone.")
