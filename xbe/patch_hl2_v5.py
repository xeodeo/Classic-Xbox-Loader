import struct, shutil, hashlib

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
dst = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default_patched.xbe"

shutil.copy2(src, dst)
with open(dst, 'rb') as f:
    data = bytearray(f.read())

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
    name       = data[name_off:end].decode('ascii', errors='replace') if 0 <= name_off < len(data) else '?'
    sections.append(dict(idx=i, name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size))

dirty = set()

def patch(label, find_seq, replace_seq):
    assert len(find_seq) == len(replace_seq)
    idx = bytes(data).find(find_seq)
    if idx == -1:
        print(f"  FAIL  [{label}]")
        return
    data[idx:idx+len(find_seq)] = replace_seq
    for s in sections:
        if s['raw_offset'] <= idx < s['raw_offset'] + s['raw_size']:
            dirty.add(s['name'])
    print(f"  OK  [{label}]  @ 0x{idx:X}")

NOP = 0x90
XAX = bytes([0x33, 0xC0])  # XOR EAX, EAX

print("=== Patch v5 — solo Valve_Leader ===\n")

# Solo Valve_Leader, NOP + EAX=0
patch("Valve_Leader CALL",
      bytes([0x53, 0x52, 0x6A, 0x12,
             0x68, 0x64, 0xFD, 0x06, 0x00,
             0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
             0xE8, 0xF3, 0x0B, 0x00, 0x00]),
      bytes([NOP]*18) + XAX)

# SHA-1
for s in sections:
    if s['name'] not in dirty: continue
    raw    = bytes(data[s['raw_offset']:s['raw_offset'] + s['raw_size']])
    digest = hashlib.sha1(raw).digest()
    off    = hdrs_off + s['idx'] * 56 + 0x24
    data[off:off+20] = digest
    print(f"  SHA-1 [{s['name']}]: {digest.hex()}")

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nArchivo: {dst}")
print("Copia como 'default.xbe' al Xbox y prueba.")
