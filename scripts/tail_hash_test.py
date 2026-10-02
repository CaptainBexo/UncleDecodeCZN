"""Test tail 16-byte hash table: match stored file hashes, find algorithm + order."""
import struct, hashlib
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()
N = 87529

# tail table size guess
tsz = N * 16
tail = d[-tsz:]
print(f"tail table: {tsz:,} B -> covers {len(tail)//16} entries; first entry: {tail[:16].hex()}")

# locate where high-entropy tail starts (table is big; find via entropy)
import math
from collections import Counter
def H(b):
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
# binary search-ish: entropy of 64KB windows from 0x600000
for off in range(0x600000, len(d)-65536, 65536):
    print(f"  H@{off:#x} = {H(d[off:off+65536]):.3f}")

# k known raw file: lang_en_b00 idx0 (1787 bytes at decoded offset 0)
dec = open(r"D:\UncleDecodeCZN\decoded\lang_en_b00_0.bin", "rb").read()
f0 = dec[:1787]
cands = {
    "xxh3_128(f0)": xxhash.xxh3_128(f0).digest(),
    "xxh128(f0,seed0)": xxhash.xxh128(f0).digest(),
    "md5(f0)": hashlib.md5(f0).digest(),
    "sha256(f0)[:16]": hashlib.sha256(f0).digest()[:16],
    "xxh3_128(dec[0:1787])rev": xxhash.xxh3_128(f0).digest()[::-1],
}
# compressed frame bytes for idx0
raw = open(CH + r"\lang_en_b00_0.ssrc", "rb").read()
frame = raw[0:1565]
cands["xxh3_128(frame)"] = xxhash.xxh3_128(frame).digest()
cands["md5(frame)"] = hashlib.md5(frame).digest()
cands["xxh128(frame)"] = xxhash.xxh128(frame).digest()

for k, v in cands.items():
    p = d.find(v)
    p2 = d.find(v[::-1])
    loc = []
    if p != -1: loc.append(("direct", hex(p), f"entry#{(p - (len(d)-tsz))//16}" if p >= len(d)-tsz else "outside-tail"))
    if p2 != -1: loc.append(("reversed", hex(p2), ""))
    print(f"{k}: {loc}")
