"""Fast walker v3: windowed decompress (no full-buffer copies)."""
import os, struct, json, sys
from collections import Counter, defaultdict
import zstandard as zstd

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
MAGIC = b"\x28\xb5\x2f\xfd"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

recs = [struct.unpack_from("<8I2HI", d, A + i * S) for i in range(N)]
base_recs = [r for r in recs if r[9] == 12]
by_size = defaultdict(list)
for r in base_recs:
    by_size[(r[8], r[4], r[5])].append(r)

def next_aligned_magic(buf, pos):
    nxt = buf.find(MAGIC, pos)
    while nxt != -1 and (nxt & 15):
        nxt = buf.find(MAGIC, nxt + 1)
    return nxt

def decompress_one(payload, pos):
    """Try decompressing a frame at pos with growing windows."""
    for extra in (0, 1 << 16, 1 << 20, 1 << 24):
        nxt = next_aligned_magic(payload, pos + 4)
        end = nxt if nxt != -1 else len(payload)
        end = min(len(payload), end + extra)
        try:
            dobj = zstd.ZstdDecompressor().decompressobj()
            out = dobj.decompress(payload[pos:end])
            unused = len(dobj.unused_data)
            return len(payload[pos:end]) - unused, len(out)
        except Exception:
            continue
    return -1, -1

def walk_chunk(path):
    dd = open(path, "rb").read()
    payload = dd[:-16]
    plen = len(payload)
    pos, frames, raws = 0, [], []
    while pos < plen:
        if payload[pos:pos+4] == MAGIC:
            in_len, out_len = decompress_one(payload, pos)
            if in_len < 0:
                frames.append((pos, -1, -1))
                break
            frames.append((pos, in_len, out_len))
            pos = (pos + in_len + 15) & ~15
        else:
            nxt = next_aligned_magic(payload, pos)
            raws.append((pos, nxt if nxt != -1 else plen))
            if nxt == -1:
                break
            pos = nxt
    return frames, raws, plen

out = {}
for name in sorted(os.listdir(CH)):
    if not name.startswith("base_"):
        continue
    frames, raws, plen = walk_chunk(os.path.join(CH, name))
    bases = Counter()
    for off, in_len, out_len in frames:
        if in_len < 0:
            continue
        cand = by_size.get((1, in_len, out_len))
        if cand and len(cand) <= 3:
            for r in cand:
                bases[r[2] - off] += 1
    top = bases.most_common(3)
    out[name] = {"plen": plen, "frames": frames, "raws": raws,
                 "bases": [[b, c] for b, c in top]}
    print(f"{name:32s} plen={plen:>12,} frames={len(frames):5d} raws={len(raws):3d} bases={[(hex(b), c) for b, c in top]}", flush=True)

json.dump(out, open(r"D:\UncleDecodeCZN\decoded\chunk_walk.json", "w"))
print("DONE")