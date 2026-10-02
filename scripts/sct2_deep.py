"""Fix names via blob walk + hash match; hexdump SCT2; exe strings for SCT2/scsp/atlas."""
import os, struct, json, itertools
import xxhash
import sys
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

P = Pack()
d = P.d

# --- names blob walk from 0x3577bb
start = 0x3577bb
names = []
pos = start
while len(names) < len(P.recs):
    e = d.find(b"\x00", pos)
    if e == -1:
        break
    nm = d[pos:e]
    if not nm:
        # skip empty
        pos = e + 1
        continue
    names.append(nm.decode("utf-8", "replace"))
    pos = e + 1
print("walked names:", len(names), "end pos:", hex(pos))

h2n = {}
for nm in names:
    h2n[xxhash.xxh64(nm.encode()).intdigest()] = nm

miss = 0
name_list = [None] * len(P.recs)
for i, f in enumerate(P.recs):
    h = (f[1] << 32) | f[0]
    nm = h2n.get(h)
    if nm is None:
        miss += 1
    name_list[i] = nm
print("hash misses:", miss)
json.dump(name_list, open(r"D:\UncleDecodeCZN\decoded\names_all.json", "w"))

from collections import Counter
top = Counter()
for n in name_list:
    if n:
        top[n.split("/")[0]] += 1
print("top dirs:", top.most_common(20))

# --- SCT2 hexdump
b = open(r"D:\UncleDecodeCZN\extract\1030.sct", "rb").read()
print("\n=== 1030.sct first 0x120 ===")
for o in range(0, 0x120, 16):
    row = b[o:o+16]
    asc = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
    print(f"{o:06x}  {row.hex(' ')}  {asc}")
print("\n...tail 32:", b[-32:].hex())

# --- exe strings
exe = open(r"E:\Games\ChaosZeroNightmare\bin\ssr-stove-shield.exe", "rb").read()
for pat in [b"SCT2", b"scsp", b"SCSP", b".atlas", b"sct2"]:
    hits = []
    j = exe.find(pat)
    while j != -1 and len(hits) < 12:
        ctx = exe[max(0, j-48):j+48]
        txt = "".join(chr(c) if 32 <= c < 127 else " " for c in ctx)
        hits.append((hex(j), txt))
        j = exe.find(pat, j + 1)
    print(f"\n=== exe {pat} ({len(hits)} shown) ===")
    for o, t in hits:
        print(" ", o, "|", t)