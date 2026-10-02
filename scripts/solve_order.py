"""Solve TRUE chunk order in base group via tiling + first-entry matching."""
import os, struct, json
import zstandard as zstd
from collections import defaultdict

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
MAGIC = b"\x28\xb5\x2f\xfd"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

tbl = []
for i in range(57):
    o = 0x40 + i * 32
    cid, gid, fl = struct.unpack_from("<IHH", d, o)
    pay, size, xh = struct.unpack_from("<QQQ", d, o + 8)
    tbl.append({"cid": cid, "gid": gid, "pay": pay, "size": size})
names = []
pos = 0x3573c8
for _ in range(57):
    e = d.find(b"\x00", pos); names.append(d[pos:e].decode()); pos = e + 1
for t, n in zip(tbl, names):
    t["name"] = n

recs = [struct.unpack_from("<8I2HI", d, A + i * S) for i in range(N)]
base = [r for r in recs if r[9] == 12]
print("base records:", len(base))

# tiling check
sb = sorted(base, key=lambda r: r[2])
gaps_bad = 0
for a, b in zip(sb, sb[1:]):
    end = (a[2] + a[4] + 15) & ~15
    if b[2] != end:
        gaps_bad += 1
        if gaps_bad < 6:
            print(f"  tiling gap: {a[2]:,}+{a[4]:,} -> {end:,} but next {b[2]:,} (diff {b[2]-end})")
print("tiling violations:", gaps_bad, "of", len(sb) - 1)

# boundary set
bounds = set()
for r in base:
    bounds.add(r[2])
    bounds.add((r[2] + r[4] + 15) & ~15)
print("last entry end:", max(bounds))

# match chunk first bytes
def first_entry(path):
    dd = open(path, "rb").read(24_000_000)
    if dd[:4] == MAGIC:
        try:
            dobj = zstd.ZstdDecompressor().decompressobj()
            out = dobj.decompress(dd)
            unc = len(dd) - len(dobj.unused_data) if False else None
            return ("zstd", len(out), out)
        except Exception:
            return ("zstd?", None, None)
    return ("raw", None, dd[:8])

bases = {}
for t in tbl:
    if t["gid"] != 12:
        continue
    p = os.path.join(CH, t["name"])
    if not os.path.exists(p):
        continue
    kind, outlen, head = first_entry(p)
    if kind == "zstd" and outlen:
        cand = [r for r in base if r[8] == 1 and r[5] == outlen and r[2] + r[4] <= max(bounds)]
        # narrow: any whose (stored) gives base = in_off and tiling-consistent
        opts = sorted({r[2] for r in cand})
        bases[t["name"]] = ("zstd", outlen, opts[:5])
        print(f"{t['name']:32s} first frame out={outlen:,} candidate bases: {[hex(o) for o in opts[:4]]} ({len(opts)})")
    else:
        print(f"{t['name']:32s} raw head={head.hex() if hasattr(head,'hex') else head}")

json.dump({k: (v[0], v[1], v[2]) for k, v in bases.items()}, open(r"D:\UncleDecodeCZN\decoded\chunk_first.json", "w"))