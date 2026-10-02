"""Print 57-chunk table (name/cid/payload) + empirical stream base per chunk from pairs."""
import json, struct
from collections import defaultdict

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()

tbl = []
for i in range(57):
    o = 0x40 + i * 32
    cid, gid, fl = struct.unpack_from("<IHH", d, o)
    pay, size, xh = struct.unpack_from("<QQQ", d, o + 8)
    tbl.append({"row": i, "cid": cid, "gid": gid, "pay": pay, "size": size})

pos = 0x3573c8
for i in range(57):
    e = d.find(b"\x00", pos)
    tbl[i]["name"] = d[pos:e].decode()
    pos = e + 1

print("rows 0-56:")
for t in tbl:
    print(f"  row{t['row']:2d} cid={t['cid']:3d} gid={t['gid']:2d} pay={t['pay']:>12,} {t['name']}")

# empirical stream base per chunk from matched pairs
pairs = json.load(open(r"D:\UncleDecodeCZN\decoded\map_pairs.json"))
bychunk = defaultdict(list)
for p in pairs:
    base = p["in_off"] - p["local"]
    bychunk[p["chunk"]].append(base)
print("\nempirical stream base per chunk (in_off - frame_local):")
for c, bases in sorted(bychunk.items(), key=lambda kv: kv[1][0]):
    uniq = sorted(set(bases))
    print(f"  {c:32s} n={len(bases):4d} bases={[hex(b) for b in uniq[:3]]}{'...' if len(uniq)>3 else ''}")