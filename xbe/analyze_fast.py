import struct, sys, os

out = []
def p(s=""):
    out.append(str(s))
    print(s)

path = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\default.xbe"
p(f"Tamano archivo: {os.path.getsize(path):,} bytes")

with open(path, 'rb') as f:
    data = f.read()

p(f"Magic: {data[:4]}")

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

p(f"Base addr   : 0x{base_addr:08X}")
p(f"Entry point : 0x{entry_point:08X}  ({build})")
p(f"Num sections: {num_sections}")

# Title
cert_off = cert_va - base_addr
if 0 <= cert_off + 88 < len(data):
    try:
        title = data[cert_off+8:cert_off+88].decode('utf-16-le').rstrip('\x00')
        p(f"Titulo      : {title}")
    except: pass

# Sections
sections = []
hdrs_off = sect_hdrs_va - base_addr
p("\n--- SECCIONES ---")
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
    p(f"  [{name:14s}] VA=0x{va:08X} raw=0x{raw_offset:07X} size={raw_size:8,} {'CODE' if is_code else 'data'}")

def off2va(offset):
    for s in sections:
        if s['raw_offset'] <= offset < s['raw_offset']+s['raw_size']:
            return s['va'] + (offset - s['raw_offset'])
    return -1

def va2off(va):
    for s in sections:
        if s['va'] <= va < s['va']+s['virt_size']:
            return s['raw_offset']+(va-s['va'])
    return -1

# Single-pass string scan — convert data to bytes once, scan for all patterns together
p("\n--- STRING SCAN (video/intro related) ---")
import re

# Case-insensitive regex for known video extensions and keywords
pattern = re.compile(
    b'(?:[\x20-\x7e]{3,})',  # any printable ASCII run >= 3 chars
)

# Targeted search - just look for these specific patterns once each
targets = [b'.xmv', b'.XMV', b'.bik', b'.BIK', b'intro', b'INTRO',
           b'movie', b'MOVIE', b'logo', b'LOGO', b'splash', b'opening',
           b'attract', b'startup', b'Bink', b'bink']

seen = set()
hits = []
for pat in targets:
    pos = 0
    while True:
        idx = data.find(pat, pos)
        if idx == -1: break
        pos = idx + 1
        # extend to full printable string
        s = idx
        while s > 0 and data[s-1] not in (0,) and 0x20 <= data[s-1] < 0x80:
            s -= 1
            if idx - s > 128: break
        e = idx
        while e < len(data) and 0x20 <= data[e] < 0x80:
            e += 1
        full = data[s:e].decode('ascii', errors='replace')
        if len(full) < 4: continue
        key = s
        if key in seen: continue
        seen.add(key)
        str_va = off2va(s)
        sect = next((x['name'] for x in sections if x['raw_offset']<=s<x['raw_offset']+x['raw_size']), '?')
        hits.append((s, str_va, sect, full))

hits.sort()
for (s, str_va, sect, full) in hits:
    p(f"  file=0x{s:X}  VA=0x{str_va:08X}  [{sect}]  \"{full[:80]}\"")
    # Search for PUSH str_va in code sections
    if str_va != -1:
        pb = bytes([0x68]) + struct.pack('<I', str_va)
        for cs in [x for x in sections if x['is_code']]:
            cd = data[cs['raw_offset']:cs['raw_offset']+cs['raw_size']]
            ri = 0
            while True:
                ri = cd.find(pb, ri)
                if ri == -1: break
                pf = cs['raw_offset']+ri
                pv = cs['va']+ri
                # scan for CALL within next 64 bytes
                for j in range(ri+5, min(ri+69, len(cd))):
                    b0=cd[j]; b1=cd[j+1] if j+1<len(cd) else 0
                    if b0==0xE8 and j+4<len(cd):
                        rel=struct.unpack_from('<i',cd,j+1)[0]
                        tgt=(cs['va']+j+5+rel)&0xFFFFFFFF
                        p(f"    PATCH: NOP {j+5-ri} bytes @ file=0x{pf:X}  (PUSH+CALL->0x{tgt:08X})")
                        break
                    if b0==0xFF and b1==0x15:
                        addr=struct.unpack_from('<I',cd,j+2)[0]
                        p(f"    PATCH: NOP {j+6-ri} bytes @ file=0x{pf:X}  (PUSH+CALL[0x{addr:08X}])")
                        break
                    if b0==0xFF and b1 in (0xD0,0xD1,0xD2,0xD3):
                        p(f"    PATCH: NOP {j+2-ri} bytes @ file=0x{pf:X}  (PUSH+CALL reg)")
                        break
                else:
                    p(f"    PUSH @ file=0x{pf:X}  (sin CALL en 64 bytes)")
                ri += 1

# Entry point calls
p(f"\n--- ENTRY POINT CALLS ---")
ep_off = va2off(entry_point)
p(f"EP file offset: 0x{ep_off:X}")
if ep_off != -1:
    i = ep_off; lim = ep_off+2048; cn = 0
    while i < min(lim, len(data)) and cn < 20:
        b = data[i]; b1 = data[i+1] if i+1<len(data) else 0
        cur_va = (entry_point + (i-ep_off)) & 0xFFFFFFFF
        if b == 0xC3:
            p("  RET - fin escaneo"); break
        if b == 0xE8 and i+4<len(data):
            rel=struct.unpack_from('<i',data,i+1)[0]
            tgt=(cur_va+5+rel)&0xFFFFFFFF
            cn+=1
            p(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  -> 0x{tgt:08X}")
            i += 5
        elif b==0xFF and b1==0x15 and i+5<len(data):
            addr=struct.unpack_from('<I',data,i+2)[0]
            cn+=1
            p(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  -> [0x{addr:08X}] indirect")
            i += 6
        elif b==0xFF and b1 in (0xD0,0xD1,0xD2,0xD3):
            reg=['EAX','ECX','EDX','EBX'][b1-0xD0]
            cn+=1
            p(f"  CALL #{cn:2d}  file=0x{i:X}  VA=0x{cur_va:08X}  CALL {reg}")
            i += 2
        else:
            i += 1

# Save output
out_path = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\analysis_result.txt"
with open(out_path, 'w') as f:
    f.write('\n'.join(out))
p(f"\nResultado guardado en: {out_path}")
