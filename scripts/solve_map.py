"""Solve base-group physical mapping: match manifest records to decoded frames by sizes."""
import json, struct, os
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
FR = r"D:\UncleDecodeCZN\decoded\frames.jsonl"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

recs = [struct.unpack_from("<8I2HI", d, A + i * S) for i in range(N)]
frames = [json.loads(l) for l in open(FR, encoding="utf-8")]
base_frames = [f for f in frames if f["chunk"].startswith("base_")]
print("base frames:", len(base_frames))

# build frame signature -> frame
sig = {}
for f in base_frames:
    sig.setdefault((f["in_len"], f["out_len"]), []).append(f)

# for base records (group 12), find ones whose (stored,raw) uniquely matches a frame
matches = []
seen = set()
for i, f in enumerate(recs):
    if f[9] != 12 or f[8] != 1:
        continue
    key = (f[4], f[5])
    cand = sig.get(key)
    if cand and len(cand) == 1:
        fr = cand[0]
        matches.append((i, f, fr))
        seen.add(fr["chunk"] + str(fr["idx"]))
    if len(matches) >= 400:
        break
print("unique matches:", len(matches))
for i, f, fr in matches[:12]:
    print(f"rec#{i} in_off={f[2]:>13,} stored={f[4]:>10,} -> {fr['chunk']} idx={fr['idx']} local_off={fr['in_off']}")
json.dump([{ "i": i, "in_off": f[2], "stored": f[4], "chunk": fr["chunk"], "local": fr["in_off"]} for i, f, fr in matches],
          open(r"D:\UncleDecodeCZN\decoded\map_pairs.json", "w"))