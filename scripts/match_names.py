"""Match every record to its name via xxh64; figure f7 semantics; dump full index."""
import json, struct
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()
A, B, S, N = 0x760, 0x3573c8, 40, 87529

# walk names with offsets
pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
name_list = []
while len(name_list) < N:
    e = d.find(b"\x00", pos)
    name_list.append((pos, d[pos:e]))
    pos = e + 1
print("names:", len(name_list))

h2n = {}
coll = 0
for off, nm in name_list:
    h = xxhash.xxh64(nm).intdigest()
    if h in h2n: coll += 1
    h2n[h] = (off, nm)
print("hash collisions:", coll)

recs = [struct.unpack_from("<8IHI", d, A + i * S) for i in range(N)]
matched = 0
f7_delta = []
miss = 0
for i, f in enumerate(recs):
    h = (f[1] << 32) | f[0]
    t = h2n.get(h)
    if t is None:
        miss += 1
        if miss < 4:
            print(f"  no name for rec#{i} h={h:016x}")
        continue
    off, nm = t
    matched += 1
    f7_delta.append((f[7], off))
print(f"matched {matched}/{N}, miss {miss}")

# f7 vs true name offset
import statistics
deltas = [off - f7 for f7, off in f7_delta]
from collections import Counter
c = Counter(deltas)
print("delta(top 8):", c.most_common(8))
print("delta min/max:", min(deltas), max(deltas))

# dump index jsonl
with open(r"D:\UncleDecodeCZN\decoded\file_index.jsonl", "w", encoding="utf-8") as w:
    for i, f in enumerate(recs):
        h = (f[1] << 32) | f[0]
        t = h2n.get(h)
        if not t:
            continue
        off, nm = t
        w.write(json.dumps({
            "i": i, "name": nm.decode("utf-8", "replace"),
            "in_off": f[2], "f3": f[3], "stored": f[4], "raw": f[5],
            "f6": f[6], "f7": f[7], "flag": f[8], "group": f[9], "f10": f[10],
        }, ensure_ascii=False) + "\n")
print("saved file_index.jsonl")

# group histogram
gh = Counter(f[9] for f in recs)
print("groups:", sorted(gh.items())[:20], "...")
