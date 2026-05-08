import struct, shutil, os

src = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
dst = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default_patched.xbe"

shutil.copy2(src, dst)
with open(dst, 'rb') as f:
    data = bytearray(f.read())

applied = 0
failed  = []

def patch_nop(label, find_seq):
    global applied
    idx = bytes(data).find(find_seq)
    if idx == -1:
        failed.append(f"NO ENCONTRADO: {label}")
        return
    n = len(find_seq)
    data[idx:idx+n] = b'\x90' * n
    print(f"  OK  [{label}]  NOP x{n} @ file=0x{idx:X}")
    applied += 1

def patch_replace(label, find_seq, replace_seq):
    global applied
    assert len(find_seq) == len(replace_seq)
    idx = bytes(data).find(find_seq)
    if idx == -1:
        failed.append(f"NO ENCONTRADO: {label}")
        return
    data[idx:idx+len(find_seq)] = replace_seq
    print(f"  OK  [{label}]  patch {len(find_seq)} bytes @ file=0x{idx:X}")
    applied += 1

print("=== XBE Intro Patcher — Half-Life 2 Xbox ===\n")

# ── Patch A: Demo_Attract.xmv ─────────────────────────────────────────────────
patch_nop(
    "Demo_Attract CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x84, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xFE, 0x0A, 0x00, 0x00])
)

# ── Patch B: Valve_Leader.xmv ────────────────────────────────────────────────
patch_nop(
    "Valve_Leader CALL",
    bytes([0x53, 0x52, 0x6A, 0x12,
           0x68, 0x64, 0xFD, 0x06, 0x00,
           0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,
           0xE8, 0xF3, 0x0B, 0x00, 0x00])
)

# ── Patch C: Title_Load.xmv — JBE → JMP ──────────────────────────────────────
patch_replace(
    "Title_Load JBE→JMP",
    bytes([0x0F, 0x86, 0xE6, 0x00, 0x00, 0x00,
           0x6A, 0x00,
           0x68, 0x44, 0xFD, 0x06, 0x00]),
    bytes([0xE9, 0xE7, 0x00, 0x00, 0x00, 0x90,
           0x6A, 0x00,
           0x68, 0x44, 0xFD, 0x06, 0x00])
)

# ── Patch D: Title_Load.xmv segunda referencia ───────────────────────────────
# Secuencia: PUSH EBX, PUSH ECX, PUSH 0x12, PUSH filename,
#            LEA ECX, MOV [ESI+0x2291], BL,  CALL
seq_d = bytes([0x53, 0x51, 0x6A, 0x12,
               0x68, 0x44, 0xFD, 0x06, 0x00,
               0x8D, 0x8E, 0xC4, 0x01, 0x00, 0x00,  # LEA ECX, [ESI+0x1C4]
               0x88, 0x9E, 0x91, 0x22, 0x00, 0x00])  # MOV [ESI+0x2291], BL
idx_d = bytes(data).find(seq_d)
if idx_d != -1:
    after = idx_d + len(seq_d)
    if data[after] == 0xE8:
        total = len(seq_d) + 5  # + CALL rel32
        data[idx_d:idx_d+total] = b'\x90' * total
        print(f"  OK  [Title_Load CALL #2]  NOP x{total} @ file=0x{idx_d:X}")
        applied += 1
    else:
        # show next 8 bytes to diagnose
        nxt = ' '.join(f'{data[after+i]:02X}' for i in range(8))
        failed.append(f"Title_Load CALL #2: byte post-MOV inesperado: {nxt}")
else:
    failed.append("NO ENCONTRADO: Title_Load CALL #2 (secuencia extendida)")

# ── Write ─────────────────────────────────────────────────────────────────────
with open(dst, 'wb') as f:
    f.write(data)

print(f"\n{'='*50}")
print(f"Parches aplicados : {applied}")
if failed:
    print(f"Fallidos/Warnings : {len(failed)}")
    for msg in failed:
        print(f"  ! {msg}")
print(f"\nArchivo parcheado : {dst}")
print("Copia 'default_patched.xbe' al Xbox como 'default.xbe'.")
