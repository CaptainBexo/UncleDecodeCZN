"""Resolve wrap + exact bases vs cum cid order; verify; then full read test."""
import json, os, struct
from collections import Counter

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()

tbl = {}
for i in range(57):
    o = 0x40 + i * 32
    cid, gid, fl = struct.unpack_from("<IHH", d, o)
    pay, size, xh = struct.unpack_from("<QQQ", d, o + 8)
    tbl[i] = {"cid": cid, "gid": gid, "pay": pay}
names = []
pos = 0x3573c8
for _ in range(57):
    e = d.find(b"\x00", pos); names.append(d[pos:e].decode()); pos = e + 1
for i in range(57):
    tbl[i]["name"] = names[i]

# cum0 per group by cid order
from collections import defaultdict
cum = {}
for gid in range(13):
    c = 0
    for i in range(57):
        t = tbl[i]
        if t["gid"] != gid:
            continue
        cum.setdefault(gid, {})[t["name"]] = c
        c += t["pay"]

walk = json.load(open(r"D:\UncleDecodeCZN\decoded\chunk_walk.json"))
print(f"{'chunk':32s} {'observed_base':>14s} {'cum0':>14s} delta")
for name, w in sorted(walk.items()):
    bases = w["bases"]
    if not bases:
        print(f"{name:32s} (no frames)")
        continue
    # normalize wrapped
    cands = Counter()
    for b, c in bases:
        bb = b if b >= 0 else b + (1 << 32)
        cands[bb] += c
    obs = cands.most_common(1)[0][0]
    mine = cum[12].get(name)
    print(f"{name:32s} {obs:>14,} {mine:>14,} {obs - mine:+,}" if mine is not None else f"{name} {obs:,}")

# Which chunk holds master.bank (in_off 3,420,355,760)? per cid-cum
need = 3420355760
for name, c0 in sorted(cum[12].items(), key=lambda kv: kv[1]):
    t = [t for t in tbl.values() if t["name"] == name][0]
    if c0 <= need < c0 + t["pay"]:
        print(f"\nmaster.bank: cid-order chunk {name} local {need - c0:,}")
    # after wrap: real offset of post-wrap records
    if c0 + t["pay"] > (1 << 32) and c0 < (1 << 32):
        print(f"wrap boundary inside {name} at local {(1<<32) - c0:,}")