import struct, shutil

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
dst = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default_patched.xbe"

shutil.copy2(src, dst)
with open(dst, 'rb') as f:
    data = bytearray(f.read())

applied = 0
failed  = []

def nop(label, seq):
    global applied
    idx = bytes(data).find(seq)
    if idx == -1:
        failed.append(label)
        return
    data[idx:idx+len(seq)] = b'\x90' * len(seq)
    print(f"  OK  [{label}]  NOP x{len(seq)} @ 0x{idx:X}")
    applied += 1

print("=== Patch v3 — solo logos (sin tocar init) ===\n")

# Valve logo intro
nop("Valve_Leader.xmv CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x64, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xF3, 0x0B, 0x00, 0x00]))

# Demo attract loop
nop("Demo_Attract.xmv CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x84, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xFE, 0x0A, 0x00, 0x00]))

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nParches: {applied}/2", "OK" if not failed else f"— fallaron: {failed}")
print(f"\nArchivo: {dst}")
print("Copia este archivo al Xbox como 'default.xbe' y prueba.")
