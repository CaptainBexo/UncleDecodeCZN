"""Full frame walker per chunk (frames + raw regions) + stream base derivation."""
import os, struct
from collections import Counter, defaultdict
import zstandard as zstd
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
MAGIC = b"\x28\xb5\x2f\xfd"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

recs = []
for i in range(N):
    f = struct.unpack_from("<8I2HI", d, A + i * S)
    recs.append(f)
base_recs = [r for r in recs if r[9] == 12]
by_size = defaultdict(list)
for r in base_recs:
    by_size[(r[8], r[4], r[5])].append(r)  # (flag, stored, raw)

def walk_chunk(path):
    dd = open(path, "rb").read()
    payload = dd[:-16]
    pos, frames, raw_regions = 0, [], []
    while pos < len(payload):
        if payload[pos:pos+4] == MAGIC:
            try:
                dobj = zstd.ZstdDecompressor().decompressobj()
                out = dobj.decompress(payload[pos:])
                in_len = len(payload[pos:]) - len(dobj.unused_data)
            except Exception:
                frames.append((pos, -1, -1, "ERR"))
                break
            frames.append((pos, in_len, len(out), out[:6].hex()))
            pos += in_len
            pos = (pos + 15) & ~15
        else:
            nxt = -1
            q = (pos + 15) & ~15
            while q < len(payload) - 4:
                if payload[q:q+4] == MAGIC:
                    nxt = q
                    break
                q += 16
            raw_regions.append((pos, nxt if nxt != -1 else len(payload)))
            if nxt == -1:
                break
            pos = nxt
    return frames, raw_regions, len(payload)

out = {}
for name in sorted(os.listdir(CH)):
    if not name.startswith("base_"):
        continue
    frames, raws, plen = walk_chunk(os.path.join(CH, name))
    # match frames to records -> base offsets
    bases = Counter()
    unmatched = 0
    for off, in_len, out_len, head in frames:
        if in_len < 0:
            continue
        cand = by_size.get((1, in_len, out_len))
        if cand and len(cand) <= 3:
            for r in cand:
                bases[r[2] - off] += 1
        else:
            unmatched += 1
    top = bases.most_common(3)
    out[name] = {"frames": len(frames), "raws": len(raws), "unmatched": unmatched, "bases": top}
    print(f"{name:32s} plen={plen:>12,} frames={len(frames):5d} raws={len(raws):3d} top bases: {[(hex(b), c) for b, c in top]}")

import json
json.dump({k: {"bases": [[b, c] for b, c in v["bases"]], "frames": v["frames"], "raws": v["raws"]} for k, v in out.items()},
          open(r"D:\UncleDecodeCZN\decoded\chunk_bases2.json", "w"))