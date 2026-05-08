import struct, sys

path = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default.xbe"
with open(path, 'rb') as f:
    data = f.read()

print(f"Tamano: {len(data):,} bytes")
print(f"Magic:  {data[:4]}")

ENTRY_XOR_RETAIL = 0xA8FC57AB
ENTRY_XOR_DEBUG  = 0x94859D4B

base_addr    = struct.unpack_from('<I', data, 0x104)[0]
cert_va      = struct.unpack_from('<I', data, 0x118)[0]
num_sections = struct.unpack_from('<I', data, 0x11C)[0]
sect_hdrs_va = struct.unpack_from('<I', data, 0x120)[0]
ep_xored     = struct.unpack_from('<I', data, 0x128)[0]

ep_r = (ep_xored ^ ENTRY_XOR_RETAIL) & 0xFFFFFFFF
ep_d = (ep_xored ^ ENTRY_XOR_DEBUG)  & 0xFFFFFFFF
dist_r = abs(ep_r - base_addr)
dist_d = abs(ep_d - base_addr)
if dist_r <= dist_d and dist_r < 0x2000000:
    entry_point = ep_r; build = "Retail"
else:
    entry_point = ep_d; build = "Debug"

print(f"Base addr : 0x{base_addr:08X}")
print(f"Entry pt  : 0x{entry_point:08X}  ({build})")
print(f"Secciones : {num_sections}")

cert_off = cert_va - base_addr
if 0 <= cert_off + 88 < len(data):
    try:
        title = data[cert_off+8:cert_off+88].decode('utf-16-le').rstrip('\x00')
        print(f"Titulo    : {title}")
    except: pass

sections = []
hdrs_off = sect_hdrs_va - base_addr
for i in range(num_sections):
    base = hdrs_off + i*56
    flags      = struct.unpack_from('<I', data, base+0)[0]
    va         = struct.unpack_from('<I', data, base+4)[0]
    virt_size  = struct.unpack_from('<I', data, base+8)[0]
    raw_offset = struct.unpack_from('<I', data, base+12)[0]
    raw_size   = struct.unpack_from('<I', data, base+16)[0]
    name_va    = struct.unpack_from('<I', data, base+20)[0]
    name_off   = name_va - base_addr
    end        = data.find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    is_code    = bool(flags & 0x04)
    sections.append(dict(name=name, flags=flags, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size, is_code=is_code))
    print(f"  [{name:12s}]  VA=0x{va:08X}  raw_off=0x{raw_offset:X}  size={raw_size:7,}  {'CODE' if is_code else 'data'}")

def offset_to_va(offset):
    for s in sections:
        if s['raw_offset'] <= offset < s['raw_offset']+s['raw_size']:
            return s['va'] + (offset - s['raw_offset'])
    return -1

def va_to_offset(va):
    for s in sections:
        if s['va'] <= va < s['va']+s['virt_size']:
            return s['raw_offset']+(va-s['va'])
    if base_addr <= va < base_addr+0x1000:
        return va - base_addr
    return -1

VIDEO_PATTERNS = [
    b'.xmv', b'.XMV', b'.bik', b'.BIK', b'.wmv',
    b'intro', b'Intro', b'INTRO',
    b'movie', b'Movie', b'MOVIE',
    b'logo',  b'Logo',  b'LOGO',
    b'splash', b'Splash', b'opening', b'Opening',
    b'attract', b'startup', b'preroll',
    b'Bink', b'bink', b'BINK',
]

print("\n=== STRING SEARCH ===")
found_strings = {}
for pat in VIDEO_PATTERNS:
    pos = 0
    while True:
        idx = data.find(pat, pos)
        if idx == -1: break
        pos = idx + 1
        s_start = idx
        lim = max(0, idx-128)
        while s_start > lim and data[s_start-1] not in (0,) and 0x20 <= data[s_start-1] < 0x80:
            s_start -= 1
        s_end = idx
        while s_end < len(data) and data[s_end] != 0:
            s_end += 1
        full = data[s_start:s_end].decode('ascii', errors='replace')
        if len(full) >= 4 and s_start not in found_strings:
            found_strings[s_start] = full
            sect_name = next((s['name'] for s in sections if s['raw_offset'] <= s_start < s['raw_offset']+s['raw_size']), '?')
            str_va = offset_to_va(s_start)
            print(f"  0x{s_start:X}  VA=0x{str_va:08X}  [{sect_name}]  \"{full}\"")
            if str_va != -1:
                push_bytes = bytes([0x68]) + struct.pack('<I', str_va)
                for cs in sections:
                    if not cs['is_code']: continue
                    cd = data[cs['raw_offset']:cs['raw_offset']+cs['raw_size']]
                    p2 = 0
                    while True:
                        ri = cd.find(push_bytes, p2)
                        if ri == -1: break
                        p2 = ri+1
                        push_file_off = cs['raw_offset']+ri
                        push_va = cs['va']+ri
                        found_call = False
                        for j in range(ri+5, min(ri+5+64, len(cd))):
                            b0 = cd[j]; b1 = cd[j+1] if j+1<len(cd) else 0
                            if b0 == 0xE8 and j+4 < len(cd):
                                rel32 = struct.unpack_from('<i', cd, j+1)[0]
                                tgt = (cs['va']+j+5+rel32)&0xFFFFFFFF
                                print(f"    --> PUSH file=0x{push_file_off:X} VA=0x{push_va:08X}  +  CALL -> 0x{tgt:08X}  [{j+5-ri} bytes NOP]")
                                found_call = True; break
                            if b0 == 0xFF and b1 == 0x15:
                                addr = struct.unpack_from('<I', cd, j+2)[0]
                                print(f"    --> PUSH file=0x{push_file_off:X} VA=0x{push_va:08X}  +  CALL [0x{addr:08X}]  [{j+6-ri} bytes NOP]")
                                found_call = True; break
                            if b0 == 0xFF and b1 in (0xD0,0xD1,0xD2,0xD3):
                                print(f"    --> PUSH file=0x{push_file_off:X} VA=0x{push_va:08X}  +  CALL reg  [{j+2-ri} bytes NOP]")
                                found_call = True; break
                        if not found_call:
                            print(f"    --> PUSH file=0x{push_file_off:X} VA=0x{push_va:08X}  (sin CALL cercana)")

print("\n=== ENTRY POINT CALLS (primeras 20) ===")
ep_off = va_to_offset(entry_point)
print(f"Entry point @ file offset 0x{ep_off:X}")
if ep_off != -1:
    i = ep_off; lim = ep_off+2048; cn = 0
    while i < min(lim, len(data)) and cn < 20:
        b = data[i]; b1 = data[i+1] if i+1<len(data) else 0
        if b == 0xC3: print("  RET encontrado, fin del escaneo"); break
        if b == 0xE8 and i+4 < len(data):
            rel = struct.unpack_from('<i', data, i+1)[0]
            cur_va = (entry_point + (i - ep_off)) & 0xFFFFFFFF
            tgt = (cur_va + 5 + rel) & 0xFFFFFFFF
            cn += 1
            print(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  -> 0x{tgt:08X}")
            i += 5
        elif b == 0xFF and b1 == 0x15 and i+5<len(data):
            addr = struct.unpack_from('<I', data, i+2)[0]
            cur_va = (entry_point + (i - ep_off)) & 0xFFFFFFFF
            cn += 1
            print(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  -> [0x{addr:08X}] (indirect)")
            i += 6
        elif b == 0xFF and b1 in (0xD0,0xD1,0xD2,0xD3):
            reg = ['EAX','ECX','EDX','EBX'][b1-0xD0]
            cur_va = (entry_point + (i - ep_off)) & 0xFFFFFFFF
            cn += 1
            print(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  CALL {reg}")
            i += 2
        else:
            i += 1

print("\nDone.")
