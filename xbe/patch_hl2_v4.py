import struct, shutil, hashlib

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
dst = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default_patched.xbe"

shutil.copy2(src, dst)
with open(dst, 'rb') as f:
    data = bytearray(f.read())

ENTRY_XOR_RETAIL = 0xA8FC57AB
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
    end        = bytes(data).find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    sections.append(dict(idx=i, name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size,
                         is_code=bool(flags&0x04)))

applied = 0
failed  = []
dirty_sections = set()  # sections we modified (need digest recalc)

def nop(label, seq):
    global applied
    idx = bytes(data).find(seq)
    if idx == -1:
        failed.append(label)
        return
    data[idx:idx+len(seq)] = b'\x90' * len(seq)
    # record which section was modified
    for s in sections:
        if s['raw_offset'] <= idx < s['raw_offset']+s['raw_size']:
            dirty_sections.add(s['name'])
            break
    print(f"  OK  [{label}]  NOP x{len(seq)} @ 0x{idx:X}")
    applied += 1

print("=== Patch v4 — con recalculo SHA-1 de secciones ===\n")

# Valve logo
nop("Valve_Leader CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x64, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xF3, 0x0B, 0x00, 0x00]))

# Demo attract
nop("Demo_Attract CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x84, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xFE, 0x0A, 0x00, 0x00]))

# Recalculate SHA-1 section digests for all modified sections
print(f"\n--- Recalculando SHA-1 para secciones modificadas: {dirty_sections} ---")
for s in sections:
    if s['name'] not in dirty_sections:
        continue
    raw = bytes(data[s['raw_offset']:s['raw_offset']+s['raw_size']])
    new_digest = hashlib.sha1(raw).digest()
    digest_off = hdrs_off + s['idx']*56 + 0x24
    old_digest = bytes(data[digest_off:digest_off+20])
    data[digest_off:digest_off+20] = new_digest
    print(f"  [{s['name']}]  SHA-1 viejo: {old_digest.hex()}")
    print(f"  [{s['name']}]  SHA-1 nuevo: {new_digest.hex()}")

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nParches aplicados : {applied}")
if failed: print(f"Fallidos: {failed}")
print(f"\nArchivo: {dst}")
print("Copia como 'default.xbe' al Xbox.")
