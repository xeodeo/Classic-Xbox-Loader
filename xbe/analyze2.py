import struct, sys

path = r"C:\Users\xeodeo\Desktop\Classic Xbox Loader\xbe\Original.xbe"
with open(path, 'rb') as f:
    data = bytearray(f.read())

ENTRY_XOR_RETAIL = 0xA8FC57AB
ENTRY_XOR_DEBUG  = 0x94859D4B

base_addr    = struct.unpack_from('<I', data, 0x104)[0]
num_sections = struct.unpack_from('<I', data, 0x11C)[0]
sect_hdrs_va = struct.unpack_from('<I', data, 0x120)[0]
ep_xored     = struct.unpack_from('<I', data, 0x128)[0]
ep_r = (ep_xored ^ ENTRY_XOR_RETAIL) & 0xFFFFFFFF
ep_d = (ep_xored ^ ENTRY_XOR_DEBUG)  & 0xFFFFFFFF
entry_point = ep_r if abs(ep_r-base_addr) < abs(ep_d-base_addr) else ep_d

sections = []
hdrs_off = sect_hdrs_va - base_addr
for i in range(num_sections):
    b = hdrs_off + i*56
    flags      = struct.unpack_from('<I', data, b+0)[0]
    va         = struct.unpack_from('<I', data, b+4)[0]
    virt_size  = struct.unpack_from('<I', data, b+8)[0]
    raw_offset = struct.unpack_from('<I', data, b+12)[0]
    raw_size   = struct.unpack_from('<I', data, b+16)[0]
    name_va    = struct.unpack_from('<I', data, b+20)[0]
    name_off   = name_va - base_addr
    end        = bytes(data).find(b'\x00', name_off)
    name       = data[name_off:end].decode('ascii', errors='replace') if 0<=name_off<len(data) else '?'
    sections.append(dict(name=name, va=va, virt_size=virt_size,
                         raw_offset=raw_offset, raw_size=raw_size,
                         is_code=bool(flags&0x04)))

def off2va(o):
    for s in sections:
        if s['raw_offset']<=o<s['raw_offset']+s['raw_size']:
            return s['va']+(o-s['raw_offset'])
    return -1
def va2off(va):
    for s in sections:
        if s['va']<=va<s['va']+s['virt_size']:
            return s['raw_offset']+(va-s['va'])
    return -1

# --- find xmv strings in original ---
xmv_strings = []
for pat in [b'.xmv', b'.XMV']:
    pos = 0
    while True:
        idx = bytes(data).find(pat, pos)
        if idx == -1: break
        pos = idx+1
        s = idx
        while s>0 and data[s-1] not in (0,) and 0x20<=data[s-1]<0x80: s-=1
        e = idx
        while e<len(data) and data[e]!=0: e+=1
        full = bytes(data[s:e]).decode('ascii', errors='replace')
        if len(full)>=4:
            va = off2va(s)
            xmv_strings.append((s, va, full))

seen = set()
xmv_unique = [(s,va,f) for s,va,f in xmv_strings if s not in seen and not seen.add(s)]
print(f"XMV strings encontradas: {len(xmv_unique)}")
for s,va,f in xmv_unique:
    print(f"  file=0x{s:X}  VA=0x{va:08X}  \"{f}\"")

# --- for each string VA, search ALL code sections for those 4 bytes ---
print("\n=== REFERENCIAS EN CODIGO (cualquier instruccion) ===")
for str_off, str_va, full_str in xmv_unique:
    if str_va == -1: continue
    va_bytes = struct.pack('<I', str_va)
    print(f"\nBuscando VA 0x{str_va:08X} de \"{full_str}\":")
    for cs in [s for s in sections if s['is_code']]:
        cd = bytes(data[cs['raw_offset']:cs['raw_offset']+cs['raw_size']])
        p = 0
        while True:
            ri = cd.find(va_bytes, p)
            if ri == -1: break
            p = ri+1
            file_off = cs['raw_offset']+ri
            ref_va   = cs['va']+ri
            # dump 12 bytes before and after for context
            ctx_start = max(0, ri-12)
            ctx_end   = min(len(cd), ri+16)
            ctx = cd[ctx_start:ctx_end]
            hex_ctx = ' '.join(f'{b:02X}' for b in ctx)
            # mark position of the VA bytes
            mark = (ri - ctx_start) * 3
            print(f"  file=0x{file_off:X}  VA_ref=0x{ref_va:08X}  [{cs['name']}]")
            print(f"    hex: {hex_ctx}")
            # identify likely opcode
            opcode = cd[ri-1] if ri>0 else 0
            opcode2 = cd[ri-2] if ri>1 else 0
            if opcode == 0x68:
                print(f"    opcode: PUSH imm32")
            elif opcode2 == 0xC7 or opcode == 0xC7:
                print(f"    opcode: MOV [mem], imm32")
            elif opcode in (0xB8,0xB9,0xBA,0xBB,0xBC,0xBD,0xBE,0xBF):
                reg = ['EAX','ECX','EDX','EBX','ESP','EBP','ESI','EDI'][opcode-0xB8]
                print(f"    opcode: MOV {reg}, imm32")
            else:
                print(f"    opcode byte before: 0x{opcode:02X}")

# --- broader context: find the function that plays videos ---
# search for all 3 VA values in sequence (they may be in a table)
print("\n=== BUSQUEDA DE TABLA DE STRINGS ===")
# find if the 3 VAs appear close together in data sections
for ds in [s for s in sections if not s['is_code']]:
    cd = bytes(data[ds['raw_offset']:ds['raw_offset']+ds['raw_size']])
    for str_off, str_va, _ in xmv_unique:
        if str_va==-1: continue
        va_bytes = struct.pack('<I', str_va)
        p=0
        while True:
            ri = cd.find(va_bytes, p)
            if ri==-1: break
            p=ri+1
            file_off = ds['raw_offset']+ri
            ctx = cd[max(0,ri-8):min(len(cd),ri+32)]
            print(f"  Puntero a VA=0x{str_va:08X} en [{ds['name']}] file=0x{file_off:X}")
            print(f"    {' '.join(f'{b:02X}' for b in ctx)}")

# --- entry point context, more bytes ---
print(f"\n=== ENTRY POINT CONTEXTO AMPLIO ===")
ep_off = va2off(entry_point)
print(f"EP=0x{entry_point:08X}  file=0x{ep_off:X}")
if ep_off != -1:
    chunk = bytes(data[ep_off:ep_off+128])
    print("  Primeros 128 bytes del entry point:")
    for row in range(0, len(chunk), 16):
        hex_row = ' '.join(f'{b:02X}' for b in chunk[row:row+16])
        print(f"  {ep_off+row:08X}: {hex_row}")

# --- search for XMVCreateDecoder string or similar ---
print("\n=== BUSQUEDA DE FUNCIONES XMV ===")
for pat in [b'XMVCreate', b'XMVPlay', b'XMVOpen', b'XMVDecode',
            b'PlayMovie', b'StopMovie', b'PlayVideo', b'CMovie',
            b'LoaderMedia', b'movie_play', b'xbmovie']:
    pos=0
    while True:
        idx = bytes(data).find(pat, pos)
        if idx==-1: break
        pos=idx+1
        s=idx; e=idx
        while e<len(data) and data[e]!=0: e+=1
        full = bytes(data[s:e]).decode('ascii', errors='replace')
        sect = next((x['name'] for x in sections if x['raw_offset']<=s<x['raw_offset']+x['raw_size']),'?')
        print(f"  0x{idx:X} [{sect}] \"{full[:80]}\"")

print("\nDone.")
