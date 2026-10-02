"""Build complete file index: f7=name offset test + full record dump + extraction verify."""
import json, struct, zstandard
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
DEC = r"D:\UncleDecodeCZN\decoded"
d = open(MAN, "rb").read()

A, B, S, N = 0x760, 0x3573c8, 40, 87529
NAMEBLOB = 0x357800  # approx file-names start; refine: after 57 chunk names from 0x3573c8
pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
NAMEBLOB = pos
print(f"names blob @{NAMEBLOB:#x}")

def name_at(off):
    p = NAMEBLOB + off
    e = d.find(b"\x00", p)
    return d[p:e]

# --- 1) f7 test on a few records with known resolutions
recs = []
for i in range(N):
    o = A + i * S
    f = struct.unpack_from("<IHHIIIIII", d, o)  # fixme: need 8u32+u16+u16+u32
    recs.append(f)
# correct unpack: <8IHI
recs = [struct.unpack_from("<8IHI", d, A + i * S) for i in range(N)]

for label, i in [("lang_en idx0", 1466), ("lang_en idx1", 16241), ("base rec0", 0), ("base rec1", 1)]:
    f = recs[i]
    nm = name_at(f[7])
    h = xxhash.xxh64(nm).intdigest()
    print(f"{label} rec#{i}: name={nm[:70]!r}")
    print(f"   f0/f1 vs xxh64: lo={f[0]:08x} hi={f[1]:08x} | exp lo={h & 0xffffffff:08x} hi={h >> 32:08x}")

# f7 == name offset check for all
bad = 0
for i in range(0, N, 101):
    nm = name_at(recs[i][7])
    if not nm or any(c != 0 and c < 0x20 for c in nm):
        bad += 1
print("f7-derived names bad:", bad, "of", len(range(0, N, 101)))

# unique name offsets?
offs = set(r[7] for r in recs)
print("unique f7 offsets:", len(offs), "of", N)

# names blob size = max f7 + len(name)
mx = max(r[7] for r in recs)
print("max f7:", mx, "blob end:", hex(NAMEBLOB + mx + 100))
print("bytes at names-blob end region:", d[NAMEBLOB + mx: NAMEBLOB + mx + 80])
