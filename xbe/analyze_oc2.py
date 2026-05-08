import struct, sys, builtins

OUT = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\analyze_oc2.txt"
_f  = open(OUT, 'w', encoding='utf-8')
_p  = builtins.print
def print(*a, **kw): kw['file'] = _f; _p(*a, **kw)

# ─────────────────────────────────────────────────────────────────────────────

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
print("Secciones de codigo:", [s['name'] for s in CODE_SECTIONS])

def off_to_sec(off):
    for s in sections:
        if s['raw_offset'] <= off < s['raw_offset'] + s['raw_size']:
            return s
    return None

def off_to_va(off):
    s = off_to_sec(off)
    return (s['va'] + (off - s['raw_offset'])) if s else None

def ctx(off, label, before=12, after=28):
    s   = off_to_sec(off)
    va  = off_to_va(off)
    print(f"\n  [{s['name'] if s else '?'}]  {label}  file=0x{off:X}  VA=0x{va:08X}" if va else
          f"\n  [?]  {label}  file=0x{off:X}")
    chunk = data[max(0, off-before):off+after]
    base  = max(0, off-before)
    for row in range(0, len(chunk), 16):
        h = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        print(f"    {base+row:08X}: {h}{'  <<<' if base+row <= off < base+row+16 else ''}")

# 1. Constantes 600-1200 MHz en secciones de codigo
print("\n=== 1. Constantes 600-1200 MHz en secciones de codigo ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 3):
        v = struct.unpack_from('<I', data, i)[0]
        if 600_000_000 <= v <= 1_200_000_000:
            ctx(i, f"const={v:,}")

# 2. Constante 733MHz en todas las secciones
print("\n=== 2. Constante 733,333,333 en TODAS las secciones ===")
needle = struct.pack('<I', 733_333_333)
start, found = 0, 0
while True:
    idx = data.find(needle, start)
    if idx == -1: break
    ctx(idx, "733,333,333")
    start = idx + 1
    found += 1
print(f"  Total: {found}")

# 3. Callers de funciones de timing (VA 0x17951 y 0x17966)
print("\n=== 3. Callers de funciones de timing ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 4):
        if data[i] == 0xE8:
            rel = struct.unpack_from('<i', data, i+1)[0]
            caller_va = off_to_va(i)
            if caller_va is None: continue
            target_va = caller_va + 5 + rel
            if target_va in (0x17951, 0x17966):
                label = "RDTSC_store" if target_va == 0x17951 else "freq_init"
                ctx(i, f"CALL->{label}  target=0x{target_va:X}")

# 4. RDTSC en secciones de codigo
print("\n=== 4. RDTSC en secciones de codigo ===")
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 1):
        if data[i] == 0x0F and data[i+1] == 0x31:
            ctx(i, "RDTSC")

# 5. DIV/IDIV en secciones de codigo (primeros 30)
print("\n=== 5. DIV/IDIV en secciones de codigo ===")
count = 0
for s in CODE_SECTIONS:
    for i in range(s['raw_offset'], s['raw_offset'] + s['raw_size'] - 1):
        if data[i] == 0xF7:
            modrm = data[i+1]
            if (modrm >> 3) & 7 in (6, 7):
                count += 1
                if count <= 30:
                    ctx(i, f"{'DIV' if (modrm>>3)&7==6 else 'IDIV'}")
print(f"  Total: {count}")

print("\nDone.")
_f.close()
_p(f"Output guardado en: {OUT}")
