"""Extractor: name -> file bytes, using manifest index + decoded chunks."""
import json, os, struct, sys
import zstandard

WS = r"D:\UncleDecodeCZN"
INDEX = os.path.join(WS, "decoded", "file_index.jsonl")
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"

# group id -> ordered list of chunk names (from 57 chunk names in manifest; map by filename pattern)
def build_groups():
    """Parse chunk files on disk: name pattern <group>_b<NN>_<P>.ssrc; group key = prefix."""
    import glob, re
    groups = {}
    for p in sorted(glob.glob(os.path.join(CH, "*.ssrc"))):
        base = os.path.basename(p)[:-5]
        m = re.match(r"^(.*)_b(\d+)_(\d+)$", base)
        if not m:
            m2 = re.match(r"^(.*)_p(\d+)$", base)
            if not m2: continue
            g, idx = m2.group(1), int(m2.group(2))
        else:
            g, blk, part = m.group(1), int(m.group(2)), int(m.group(3))
            idx = -1  # ordering handled below
        groups.setdefault(g, []).append((base, p))
    return groups

# simpler: use manifest chunk table for global ordering; map chunk NAME -> (group_id, chunk_id, size)
def chunk_table():
    A = 0x40
    rows = []
    for i in range(57):
        o = A + i * 32
        cid, gid, fl = struct.unpack_from("<IHH", d0, o)
        pay, size, h = struct.unpack_from("<QQQ", d0, o + 8)
        rows.append({"idx": i, "chunk_id": cid, "group": gid, "payload": pay, "size": size, "xh": h})
    return rows

d0 = open(r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra", "rb").read()
# chunk names from manifest (57)
pos = 0x3573c8
chunk_names = []
for _ in range(57):
    e = d0.find(b"\x00", pos)
    chunk_names.append(d0[pos:e].decode())
    pos = e + 1
tbl = chunk_table()
for t, n in zip(tbl, chunk_names):
    t["name"] = n
print("chunk table sample:", tbl[0], tbl[-1])

# group -> ordered chunks (by chunk_id)
from collections import defaultdict
bygroup = defaultdict(list)
for t in tbl:
    bygroup[t["group"]].append(t)
for g in bygroup:
    bygroup[g].sort(key=lambda t: t["chunk_id"])

on_disk = {os.path.basename(p)[:-5] for p in __import__("glob").glob(os.path.join(CH, "*.ssrc"))}
print("groups:", {g: len(v) for g, v in sorted(bygroup.items())})

index = {}
for line in open(INDEX, encoding="utf-8"):
    r = json.loads(line)
    index[r["name"]] = r

def extract(name, outdir):
    r = index.get(name)
    if r is None:
        return f"NOT IN INDEX: {name}"
    g = r["group"]
    chunks = bygroup.get(g, [])
    need = r["in_off"]
    cum = 0
    target = None
    for t in chunks:
        if cum <= need < cum + t["payload"]:
            target = (t, need - cum)
            break
        cum += t["payload"]
    if target is None:
        return f"offset {need} outside group {g} (cum {cum})"
    t, local = target
    path = os.path.join(CH, t["name"])
    if not os.path.exists(path):
        return f"chunk {t['name']} not downloaded"
    with open(path, "rb") as fh:
        fh.seek(local)
        data = fh.read(r["stored"])
    if r["flag"] == 1:
        try:
            data = zstandard.ZstdDecompressor().decompressobj().decompress(data)
        except Exception as e:
            return f"decompress fail: {e}"
    if len(data) != r["raw"]:
        return f"size mismatch: got {len(data)} want {r['raw']}"
    os.makedirs(outdir, exist_ok=True)
    outp = os.path.join(outdir, name.replace("/", "__"))
    open(outp, "wb").write(data)
    return f"OK {len(data):,} B -> {outp}"

if __name__ == "__main__":
    tests = [
        "effect/en/ui_stage_clear_win.scsp",
        "banner/lobby/en/banner_lobby_30117_text.sct",
        "sound/master.bank",
        "wnd/unit_mode_profile_content.csb",
    ]
    for t in tests:
        print(t, "->", extract(t, os.path.join(WS, "out")))
    # find some portrait/character scts
    cands = [n for n in index if "portrait" in n.lower() and n.endswith(".sct")][:5]
    for c in cands:
        print(c, "->", extract(c, os.path.join(WS, "out")))
