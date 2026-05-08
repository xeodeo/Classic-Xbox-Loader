import struct

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

def va2off(va):
    for s in sections:
        if s['va'] <= va < s['va'] + s['virt_size']:
            return s['raw_offset'] + (va - s['va'])
    return -1

def dump(label, file_off, count=128):
    print(f"\n--- {label}  (file=0x{file_off:X}  VA=0x{file_off - sections[0]['raw_offset'] + sections[0]['va']:X}) ---")
    chunk = data[file_off:file_off+count]
    for row in range(0, len(chunk), 16):
        h = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        print(f"  {file_off+row:08X}: {h}")

# --- Code AFTER each CALL site ---

# Demo_Attract CALL ends at file 0x3BAD + 5 = 0x3BB2
dump("Codigo DESPUES de Demo_Attract CALL", 0x3BB2, 96)

# Valve_Leader: find exact CALL end
# sequence ends at 0x3C79 + 20 = 0x3C8D
dump("Codigo DESPUES de Valve_Leader CALL", 0x3C8D, 96)

# --- Target function bodies ---

# Demo_Attract CALL target: E8 FE 0A 00 00 at file 0x3BAD
# CALL VA = .text VA + (0x3BAD - .text raw) = 0x11000 + (0x3BAD - 0x1000) = 0x13BAD
# rel32 = 0x00000AFE  → target VA = 0x13BAD + 5 + 0x0AFE = 0x146B0
demo_target_va  = 0x146B0
valve_target_va = 0x14880  # from earlier: E8 F3 0B 00 00 at 0x3C88 → 0x13C88+5+0x0BF3=0x14880

demo_target_off  = va2off(demo_target_va)
valve_target_off = va2off(valve_target_va)

dump(f"FUNCION TARGET Demo_Attract  (VA=0x{demo_target_va:X})", demo_target_off, 128)
dump(f"FUNCION TARGET Valve_Leader  (VA=0x{valve_target_va:X})", valve_target_off, 128)

# Also: what is MOV EDX,[ESI+0x4C] loading?  And what is [ESI+0x1C4]?
# Check if there's a "wait/poll" loop near the call sites
# Scan 256 bytes before each call for JMP-back patterns (short backward jumps)
print("\n--- Buscando loops (JMP hacia atras) cerca de Demo_Attract CALL (0x3B9E-0x3C50) ---")
window = data[0x3B9E:0x3C50]
for i, b in enumerate(window):
    file_pos = 0x3B9E + i
    if b == 0xEB:  # JMP short
        rel = window[i+1] if i+1 < len(window) else 0
        rel_signed = rel if rel < 128 else rel - 256
        target = file_pos + 2 + rel_signed
        print(f"  JMP short @ 0x{file_pos:X}  rel={rel_signed:+d}  target=0x{target:X}  {'<-- LOOP BACK' if rel_signed < 0 else ''}")
    elif b == 0x74 or b == 0x75:  # JE/JNE short
        rel = window[i+1] if i+1 < len(window) else 0
        rel_signed = rel if rel < 128 else rel - 256
        target = file_pos + 2 + rel_signed
        if rel_signed < 0:
            op = 'JE' if b==0x74 else 'JNE'
            print(f"  {op} short @ 0x{file_pos:X}  rel={rel_signed:+d}  target=0x{target:X}  <-- LOOP BACK")
    elif b == 0xE9:  # JMP near
        if i+4 < len(window):
            rel = struct.unpack_from('<i', window, i+1)[0]
            target = file_pos + 5 + rel
            if rel < 0:
                print(f"  JMP near  @ 0x{file_pos:X}  rel={rel:+d}  target=0x{target:X}  <-- LOOP BACK")

print("\nDone.")
