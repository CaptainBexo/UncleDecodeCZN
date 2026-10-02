"""Final field resolution: f0 hash test + lang_en record<->frame correlation."""
import json, struct
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
FR = r"D:\UncleDecodeCZN\decoded\frames.jsonl"
d = open(MAN, "rb").read()

A, B, S = 0x760, 0x3573c8, 40
N = (B - A) // S
offs = [A + i * S for i in range(N)]
fld = [struct.unpack_from("<8IHI", d, o) for o in offs]

# names
pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
names = []
while len(names) < N:
    end = d.find(b"\x00", pos)
    names.append(d[pos:end]); pos = end + 1

# f0 test
by_name = {}
bad = 0
for i, nm in enumerate(names):
    h = xxhash.xxh64(nm).intdigest()
    hi, lo = h >> 32, h & 0xFFFFFFFF
    f = fld[i]
    if f[1] != hi:
        bad += 1
        if bad < 5:
            print(f"i={i} name={nm[:60]!r} f1={f[1]:08x} exp_hi={hi:08x}")
print(f"f1==xxh64hi mismatches: {bad}/{N}")
lo_bad = sum(1 for i, nm in enumerate(names) if fld[i][0] != (xxhash.xxh64(nm).intdigest() & 0xFFFFFFFF))
print(f"f0==xxh64lo mismatches: {lo_bad}/{N}")

# lang_en correlation
frames = [json.loads(l) for l in open(FR, encoding="utf-8")]
lang = [f for f in frames if f["chunk"].startswith("lang_en")]
bases_in = {"lang_en_b00_0": 0, "lang_en_b01_0": 259760, "lang_en_b02_0": 440784,
            "lang_en_b03_0": 516976}
# decompressed cumulative per chunk (no padding)
chunks_order = ["lang_en_b00_0", "lang_en_b01_0", "lang_en_b02_0", "lang_en_b03_0"]
out_base = {}
acc = 0
for c in chunks_order:
    out_base[c] = acc
    acc += sum(f["out_len"] for f in lang if f["chunk"] == c)

print("\nchunk, idx | cum_in, in_len, out_len | -> record f2, f4, f5, f7 | f0-f7")
pairs = 0
for f in lang[:14]:
    cum_in = bases_in[f["chunk"]] + f["in_off"]
    matches = [i for i in range(N) if fld[i][2] == cum_in and fld[i][4] == f["in_len"] and fld[i][5] == f["out_len"]]
    for i in matches:
        ff = fld[i]
        print(f"{f['chunk'][-7:]} idx{f['idx']:2d} | in {cum_in:>9,} len {f['in_len']:>8,} out {f['out_len']:>8,} | f2={ff[2]:,} f4={ff[4]:,} f5={ff[5]:,} f7={ff[7]:,} f3={ff[3]} f6={ff[6]} flag={ff[8]} grp={ff[9]}")
        pairs += 1
    if not matches:
        print(f"{f['chunk'][-7:]} idx{f['idx']:2d} | in {cum_in:>9,} len {f['in_len']:>8,} out {f['out_len']:>8,} | NO RECORD MATCH")
print("pairs:", pairs)
