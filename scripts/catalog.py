"""Catalog decoded chunks: head/tail + name-pattern density."""
import glob, os, re

DEC = r"D:\UncleDecodeCZN\decoded"
pats = [b".sct", b".atlas", b".scsp", b".js", b"effect/", b"model/", b"img/",
        b"wnd/", b"db/", b".bank", b".mp4", b".sract", b".csb", b"PLPcK",
        b"SCT2", b"text/", b"lang/", b"sound/", b"face/"]

rows = []
for f in sorted(glob.glob(os.path.join(DEC, "*.bin"))):
    d = open(f, "rb").read()
    n = len(d)
    hits = {p.decode(): d.count(p) for p in pats if d.count(p)}
    rows.append((os.path.basename(f), n, d[:24].hex(), hits))

for name, n, head, hits in rows:
    top = sorted(hits.items(), key=lambda kv: -kv[1])[:6]
    print(f"{name:32s} {n:>13,} head={head}")
    print(f"    {top}")
