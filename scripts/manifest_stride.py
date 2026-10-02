"""Find file-record stride + test hash algorithms against known values."""
import struct
from collections import Counter
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()

# --- 1) hash algorithm tests on chunk trailer values
CHUNKS = {
    "lang_en_b00_0.ssrc": "6297bb449dde37ea",
    "base_b00_0.ssrc": "237a22352da5aa1f",
    "bin_x86_64_b00_0.ssrc": "cd8b70dbc2d20dd5",
}
for fn, expect in CHUNKS.items():
    raw = open(f"{CH}\\{fn}", "rb").read()
    payload = raw[:-16]
    h = bytes.fromhex(expect)
    res = {}
    res["xxh64(payload)"] = xxhash.xxh64(payload).digest()
    res["xxh64(raw)"] = xxhash.xxh64(raw).digest()
    res["xxh3_64(payload)"] = xxhash.xxh3_64(payload).digest()
    res["xxh3_64(raw)"] = xxhash.xxh3_64(raw).digest()
    res["xxh3_64(whole-16).BE"] = xxhash.xxh3_64(payload).digest()[::-1]
    match = [k for k, v in res.items() if v == h or v[::-1] == h]
    print(f"{fn}: expect {h.hex()} -> match: {match}")
    if not match:
        for k, v in res.items():
            print(f"   {k} = {v.hex()}")

# --- 2) file-record stride detection in 0x760..0x3573c8
A, B = 0x760, 0x3573c8
region = d[A:B]
sig = b"\x01\x00\x0c\x00"
offs = []
i = region.find(sig)
while i != -1:
    offs.append(i + A)
    i = region.find(sig, i + 1)
print(f"\n`01 00 0c 00` occurrences in file-record region: {len(offs)}")
sp = Counter(b - a for a, b in zip(offs, offs[1:]))
print("top spacings:", sp.most_common(8))

sig2 = b"\x01\x00\x02\x00"
offs2 = []
i = region.find(sig2)
while i != -1:
    offs2.append(i + A)
    i = region.find(sig2, i + 1)
print(f"`01 00 02 00` count: {len(offs2)}")
sp2 = Counter(b - a for a, b in zip(offs2, offs2[1:]))
print("top spacings:", sp2.most_common(8))

# --- 3) assume stride S: look for monotonic u32 field (name offsets) in first 2000 records
for S in (36, 40, 44, 48):
    n = (B - A) // S
    best = None
    for fo in range(0, S - 4, 4):
        vals = [struct.unpack_from("<I", d, A + i * S + fo)[0] for i in range(min(n, 3000))]
        mono = sum(1 for a, b in zip(vals, vals[1:]) if b >= a)
        if best is None or mono > best[1]:
            best = (fo, mono, vals[:4])
    print(f"stride {S}: n={n}, best mono field offset +{best[0]} ({best[1]}/{2999} rising), first vals {best[2]}")

# --- 4) md5 of decompressed file vs manifest
import hashlib
dec = open(r"D:\UncleDecodeCZN\decoded\lang_en_b00_0.bin", "rb").read()
f1 = dec[:1787]
for label, blob in [("file1787", f1), ("file1787-hdr?", f1[8:]), ("file1787-body?", f1[0x30:])]:
    mm = hashlib.md5(blob).digest()
    print(f"md5 {label}: {mm.hex()} in manifest? {d.find(mm) != -1}")
