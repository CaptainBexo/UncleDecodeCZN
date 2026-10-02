"""Probe CZN .ssrc chunks: entropy, magic, structure. Read-only."""
import glob, math, os, sys
from collections import Counter

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"

def H(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

files = sorted(glob.glob(os.path.join(CH, "*.ssrc")))
print(f"{len(files)} chunks, total {sum(os.path.getsize(f) for f in files):,} B\n")

probe = [f for f in files if os.path.getsize(f) < 20_000_000] + \
        [f for f in files if os.path.getsize(f) > 200_000_000][:2]
for f in probe:
    sz = os.path.getsize(f)
    with open(f, "rb") as fh:
        head = fh.read(2_000_000)
        fh.seek(max(0, sz - 64))
        tail = fh.read(64)
    print(f"{os.path.basename(f)}  size={sz:,}")
    print(f"  H(head2M)={H(head):.4f}  head64={head[:64].hex()}")
    print(f"  tail64={tail.hex()}")

# signature scan in first 8MB of a big chunk + all small chunks
sigs = {
    b"\x1f\x8b\x08": "gzip", b"\x28\xb5\x2f\xfd": "zstd",
    b"\x04\x22\x4d\x18": "lz4", b"\xfd7zXZ": "xz",
    b"PLPcK": "PLPcK", b"PK\x03\x04": "zip", b"BKHD": "fmod",
    b"\x78\x9c": "zlib9c", b"\x78\xda": "zlibda", b"\x78\x01": "zlib01",
}
for f in probe:
    with open(f, "rb") as fh:
        d = fh.read(8_000_000)
    hits = {n: d.count(s) for s, n in sigs.items() if d.count(s)}
    print(f"{os.path.basename(f)}: {hits or 'no known sigs'}")

# block-structure guess: check for periodic 8-byte values in header
f0 = os.path.join(CH, "lang_en_b00_0.ssrc")
with open(f0, "rb") as fh:
    d = fh.read(512)
print("\nlang_en_b00_0 first 512B hex:")
for i in range(0, 512, 32):
    print(f"{i:04x}: {d[i:i+32].hex()}")
