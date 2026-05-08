"""
patch_oc_v2.py — parche OC completo para Half-Life 2 Xbox @ 913 MHz

Parches aplicados:
  1. freq_init: constante 733,333,333 → 913,000,000
     (usada por .text, D3D y XMV para inicializar sus timers)

  2. XMV decoder @ 60fps: MOV [ESI+0xBC], 1,093,872 → 1,362,780
     (ticks de inter-frame para 60fps, hardcodeado para 733 MHz)

  3. XMV decoder @ otros fps: MOV EAX, 65,536,000 → 81,592,320
     (numerador del calculo 65536000/fps, hardcodeado para 733 MHz)

Escala aplicada: 913,000,000 / 733,333,333 = 2739/2200 ≈ 1.2455
"""
import struct, shutil, hashlib

TARGET_HZ = 913_000_000
ORIG_HZ   = 733_333_333

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
dst = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default_patched.xbe"

shutil.copy2(src, dst)
with open(dst, 'rb') as f:
    data = bytearray(f.read())

# --- parse XBE header ---
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
    end        = bytes(data).find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    sections.append(dict(idx=i, name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size))

dirty = set()

def patch(label, find_seq, replace_seq):
    assert len(find_seq) == len(replace_seq)
    idx = bytes(data).find(find_seq)
    if idx == -1:
        print(f"  FAIL  [{label}]  secuencia no encontrada")
        return False
    data[idx:idx+len(find_seq)] = replace_seq
    for s in sections:
        if s['raw_offset'] <= idx < s['raw_offset'] + s['raw_size']:
            dirty.add(s['name'])
    print(f"  OK    [{label}]  @ file=0x{idx:X}")
    return True

print(f"=== OC Patch v2: {ORIG_HZ:,} Hz  →  {TARGET_HZ:,} Hz ===\n")

# ── Parche 1: freq_init — constante 733 MHz ──────────────────────────────────
# Funcion en .text que inicializa timer structs con la frecuencia del CPU.
# Llamada por .text, D3D y XMV.
patch("1. freq_init (733→913 MHz)",
    bytes([0x83, 0x60, 0x04, 0x00,              # AND [EAX+4], 0
           0xC7, 0x00]) + struct.pack('<I', ORIG_HZ) +   # MOV [EAX], 733333333
    bytes([0x33, 0xC0, 0x40, 0xC2, 0x04, 0x00]),         # XOR EAX,EAX; INC EAX; RET 4

    bytes([0x83, 0x60, 0x04, 0x00,
           0xC7, 0x00]) + struct.pack('<I', TARGET_HZ) +
    bytes([0x33, 0xC0, 0x40, 0xC2, 0x04, 0x00]))

# ── Parche 2: XMV decoder — valor 60fps hardcodeado ─────────────────────────
# MOV DWORD PTR [ESI+0xBC], 1,093,872
# Seguido de JMP +0x10 (saltea el else-branch).
# Escala: 1,093,872 * 913/733.333 = 1,362,780
XMV_60FPS_ORIG   = 1_093_872   # 0x0010AEF0
XMV_60FPS_TARGET = round(XMV_60FPS_ORIG * TARGET_HZ / ORIG_HZ)  # 1,362,780
print(f"\n  XMV 60fps: {XMV_60FPS_ORIG:,} → {XMV_60FPS_TARGET:,}  (0x{XMV_60FPS_TARGET:08X})")
patch("2. XMV 60fps ticks",
    bytes([0xC7, 0x86, 0xBC, 0x00, 0x00, 0x00]) + struct.pack('<I', XMV_60FPS_ORIG)  + bytes([0xEB, 0x10]),
    bytes([0xC7, 0x86, 0xBC, 0x00, 0x00, 0x00]) + struct.pack('<I', XMV_60FPS_TARGET) + bytes([0xEB, 0x10]))

# ── Parche 3: XMV decoder — numerador del calculo para otros fps ─────────────
# MOV EAX, 65,536,000  →  luego XOR EDX,EDX; DIV [EBP-0x1C]; MOV [ESI+0xBC], EAX
# Escala: 65,536,000 * 913/733.333 = 81,592,320  (exacto: ratio = 2739/2200)
XMV_DIV_ORIG   = 65_536_000   # 0x03E80000
XMV_DIV_TARGET = round(XMV_DIV_ORIG * TARGET_HZ / ORIG_HZ)  # 81,592,320
print(f"  XMV fps divisor: {XMV_DIV_ORIG:,} → {XMV_DIV_TARGET:,}  (0x{XMV_DIV_TARGET:08X})")
patch("3. XMV fps divisor",
    bytes([0xB8]) + struct.pack('<I', XMV_DIV_ORIG)   + bytes([0x33, 0xD2, 0xF7, 0x75, 0xE4]),
    bytes([0xB8]) + struct.pack('<I', XMV_DIV_TARGET) + bytes([0x33, 0xD2, 0xF7, 0x75, 0xE4]))

# ── Recalcular SHA-1 de secciones modificadas ────────────────────────────────
if dirty:
    print(f"\n--- Recalculando SHA-1: {dirty} ---")
    for s in sections:
        if s['name'] not in dirty:
            continue
        raw    = bytes(data[s['raw_offset']:s['raw_offset'] + s['raw_size']])
        digest = hashlib.sha1(raw).digest()
        off    = hdrs_off + s['idx'] * 56 + 0x24
        data[off:off+20] = digest
        print(f"  [{s['name']}]  {digest.hex()}")

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nArchivo: {dst}")
print("Copia como 'default.xbe' al Xbox y prueba.")
