"""Crack name-hash fields + resolve F8 via known lang_en frames."""
import json, struct, zlib, hashlib
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
FR = r"D:\UncleDecodeCZN\decoded\frames.jsonl"
d = open(MAN, "rb").read()

A, B, S = 0x760, 0x3573c8, 40
N = (B - A) // S
recs = []
for i in range(N):
    off = A + i * S
    f = struct.unpack_from("<8IHI", d, off)  # 8 u32, u16 flag, u16 group, u32
    recs.append((i, off) + f)

# collect names (reuse walker from before; start at file blob after chunk names)
pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
names = []
while len(names) < N:
    end = d.find(b"\x00", pos)
    nm = d[pos:end]
    names.append(nm)
    pos = end + 1
print(f"names: {len(names)}")

# --- multiset test: field F2 (idx 1) and F0 (idx 0) vs candidate hashes of names
F0 = sorted(r[3] for r in recs)
F2 = sorted(r[4] for r in recs)
cands = {
    "xxh32": lambda b: xxhash.xxh32(b).intdigest(),
    "xxh32(seed1)": lambda b: xxhash.xxh32(b, seed=1).intdigest(),
    "xxh64lo": lambda b: xxhash.xxh64(b).intdigest() & 0xFFFFFFFF,
    "xxh64hi": lambda b: xxhash.xxh64(b).intdigest() >> 32,
    "xxh3_64lo": lambda b: xxhash.xxh3_64(b).intdigest() & 0xFFFFFFFF,
    "xxh3_64hi": lambda b: xxhash.xxh3_64(b).intdigest() >> 32,
    "crc32": zlib.crc32,
    "fnv1a": lambda b: __import__("functools").reduce(lambda h, c: ((h ^ c) * 0x01000193) & 0xFFFFFFFF, b, 0x811C9DC5),
}
for cn, fn in cands.items():
    v = sorted(fn(n) for n in names)
    print(f"{cn}: F2 match={v == F2} F0 match={v == F0}")

# also lowercase / nul-terminated variants for xxh32
for cn in ("xxh32", "xxh64lo", "crc32"):
    for variant, tf in [("lower", lambda n: n.lower()), ("+nul", lambda n: n + b"\x00"),
                        ("bslash", lambda n: n.replace(b"/", b"\\"))]:
        fn = cands[cn]
        v = sorted(fn(tf(n)) for n in names)
        if v == F2 or v == F0:
            print(f"MATCH {cn} {variant}: F2={v==F2} F0={v==F0}")

# --- tail hash table: check size and test
tail16 = d[-1400464:]
if len(tail16) == N * 16:
    # find a record with unique (F5,F6) = known frame
    frames = [json.loads(l) for l in open(FR, encoding="utf-8")]
    lang = [f for f in frames if f["chunk"].startswith("lang_en")]
    # cumulative in offsets per group (chunks in id order)
    from collections import defaultdict
    grp_chunks = defaultdict(list)
    for f in frames:
        grp_chunks[f["chunk"]].append(f)
    # pick lang_en_b00 idx0: in_len 1565 out_len 1787 unique?
    cand = [f for f in lang if (f["in_len"], f["out_len"]) == (1565, 1787)]
    print("\ncandidates (1565,1787):", cand)
    for f in cand:
        matches = [r for r in recs if r[7] == f["in_len"] and r[8] == f["out_len"] and r[11] == 2]
        print("records with (F5,F6)=(1565,1787) group2:", len(matches))
        for m in matches[:4]:
            print("   rec", m[0], "fields:", m[3:12])
else:
    print("tail size mismatch:", len(tail16), N * 16)
