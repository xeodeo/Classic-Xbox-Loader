import shutil, struct, os

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default.xbe"
bak = src + ".bak"
dst = src  # patch in place

# Backup
if not os.path.exists(bak):
    shutil.copy2(src, bak)
    print(f"Backup creado: default.xbe.bak")
else:
    print(f"Backup ya existe: default.xbe.bak")

with open(src, 'rb') as f:
    data = bytearray(f.read())

patches = [
    (0x5F904, b"Z:\\LoaderMedia\\Title_Load.xmv\x00"),
    (0x5F924, b"D:\\LoaderMedia\\Valve_Leader.xmv\x00"),
    (0x5F944, b"D:\\LoaderMedia\\Demo_Attract.xmv\x00"),
]

for offset, expected in patches:
    actual = data[offset:offset+len(expected)]
    if actual == expected:
        data[offset:offset+len(expected)] = b'\x00' * len(expected)
        print(f"  OK  0x{offset:X}  zeroed {len(expected)} bytes  ({expected[:-1].decode()})")
    else:
        # Try to find where it actually is (in case offsets shifted)
        found = bytes(data).find(expected[:-1])
        if found != -1:
            data[found:found+len(expected)] = b'\x00' * len(expected)
            print(f"  OK  found at 0x{found:X} (esperado 0x{offset:X})  zeroed {len(expected)} bytes  ({expected[:-1].decode()})")
        else:
            print(f"  SKIP  0x{offset:X}  no coincide: {actual[:16]!r}")

with open(dst, 'wb') as f:
    f.write(data)

print(f"\nListo. {dst}")
print("Prueba el juego. Si falla usa 'default.xbe.bak' para restaurar.")
