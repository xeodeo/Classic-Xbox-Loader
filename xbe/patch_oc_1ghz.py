"""
patch_oc_1ghz.py — parcha Half-Life 2 Xbox para correr con CPU OC a 1 GHz.

El juego inicializa su timer con 733,333,333 Hz hardcodeado.
Con OC a 1 GHz el RDTSC corre ~36% más rápido pero el divisor sigue siendo
733 MHz, así que el juego cree que el tiempo pasa más rápido → XMV decoder
se desincroniza → freeze en la intro.

Fix: cambiar la constante al frecuencia real del CPU.

Cambiar TARGET_HZ si se quiere parchear para otra frecuencia:
  900 MHz = 900_000_000
  950 MHz = 950_000_000
  1 GHz   = 1_000_000_000  ← default
"""
import struct, shutil, hashlib

TARGET_HZ = 913_000_000     # 913 MHz
ORIG_HZ   = 733_333_333     # 733 MHz original del Xbox

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
    assert len(find_seq) == len(replace_seq), "longitud diferente"
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

print(f"=== OC Patch: {ORIG_HZ:,} Hz  →  {TARGET_HZ:,} Hz ===\n")

orig_bytes   = struct.pack('<I', ORIG_HZ)    # 55 C7 B5 2B
target_bytes = struct.pack('<I', TARGET_HZ)  # 00 CA 9A 3B (para 1 GHz)

# Contexto completo de la instrucción para búsqueda segura:
#   83 60 04 00       AND [EAX+4], 0
#   C7 00 xx xx xx xx MOV [EAX], ORIG_HZ
#   33 C0             XOR EAX, EAX
#   40                INC EAX
#   C2 04 00          RET 4
find_seq    = bytes([0x83, 0x60, 0x04, 0x00, 0xC7, 0x00]) + orig_bytes   + bytes([0x33, 0xC0, 0x40, 0xC2, 0x04, 0x00])
replace_seq = bytes([0x83, 0x60, 0x04, 0x00, 0xC7, 0x00]) + target_bytes + bytes([0x33, 0xC0, 0x40, 0xC2, 0x04, 0x00])

ok = patch("CPU freq init (timer)", find_seq, replace_seq)

if ok:
    print(f"\n  {ORIG_HZ:,} Hz  →  {TARGET_HZ:,} Hz")
    print(f"  bytes: {orig_bytes.hex()}  →  {target_bytes.hex()}")

# --- Recalcular SHA-1 de secciones modificadas ---
if dirty:
    print(f"\n--- Recalculando SHA-1 para: {dirty} ---")
    for s in sections:
        if s['name'] not in dirty:
            continue
        raw    = bytes(data[s['raw_offset']:s['raw_offset'] + s['raw_size']])
        digest = hashlib.sha1(raw).digest()
        off    = hdrs_off + s['idx'] * 56 + 0x24
        data[off:off+20] = digest
        print(f"  [{s['name']}]  SHA-1: {digest.hex()}")

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nArchivo: {dst}")
print("Copia como 'default.xbe' al Xbox y prueba.")
