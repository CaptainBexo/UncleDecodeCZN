"""Map manifest.ssra layout: name blobs, record arrays, verify with known chunk sizes/hashes."""
import re, struct

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()

# 1) walk names from known start 0x3573ce-ish: find first name start precisely
def walk_names(start, maxn=200000, stop_nonprint_len=0):
    names = []
    pos = start
    while len(names) < maxn and pos < len(d):
        end = d.find(b"\x00", pos)
        if end == -1: break
        s = d[pos:end]
        if not s or any(c < 0x20 or c > 0x7e for c in s):
            break
        names.append((pos, s.decode("latin1")))
        pos = end + 1
    return names, pos

# find start: a name boundary just before "lang_ja_b00_0.ssrc"
anchor = d.find(b"lang_ja_b00_0.ssrc")
start = anchor
while start > 0 and 0x20 <= d[start-1] <= 0x7e:
    start -= 1
names, endpos = walk_names(start)
print(f"name blob walk: start={start:#x} count={len(names)} end={endpos:#x}")
print("first 8:", [n for _, n in names[:8]])
print("last 5:", [n for _, n in names[-5:]])
# where does .ssrc names stop and file names start?
ss = [i for i, (o, n) in enumerate(names) if n.endswith(".ssrc")]
print(f".ssrc names: {len(ss)} (idx {ss[0]}..{ss[-1]})")
fp = ss[-1] + 1
print(f"first non-ssrc after: {names[fp][1]}")
print(f"last names: {[n for _,n in names[-3:]]}")
print(f"bytes at end of blob: {d[endpos:endpos+64].hex()}")
print(f"ascii: {re.sub(rb'[^ -~]', b'.', d[endpos:endpos+64])}")

# 2) search known values
def find_all(pat, limit=6):
    out, i = [], d.find(pat)
    while i != -1 and len(out) < limit:
        out.append(i); i = d.find(pat, i+1)
    return out

known = {
    "size base_b00 (236,720,144)": struct.pack("<Q", 236720144),
    "size base_b00 u32": struct.pack("<I", 236720144),
    "size lang_en_b00 (259,776)": struct.pack("<I", 259776),
    "decomp lang_en_b00 (274,696)": struct.pack("<I", 274696),
    "trailer hash base_b00 (237a22352da5aa1f BE)": bytes.fromhex("237a22352da5aa1f"),
    "trailer hash lang_en_b00 (6297bb449dde37ea)": bytes.fromhex("6297bb449dde37ea"),
    "chunk_id base_b32 (33)": struct.pack("<I", 33),
}
for k, v in known.items():
    offs = find_all(v)
    print(f"{k}: {[hex(o) for o in offs]}")

# 3) header u32/u64 dump
print("\nheader u32s (offset 0..0x60):")
for off in range(4, 0x60, 4):
    v = struct.unpack_from("<I", d, off)[0]
    print(f"  +{off:#04x}: {v:>12,} (0x{v:08x})")
