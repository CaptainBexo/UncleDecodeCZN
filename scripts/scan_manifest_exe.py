"""Deep scan manifest.ssra + new exe build for SSRA keywords."""
import math, re
from collections import Counter

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
EXE = r"E:\Games\ChaosZeroNightmare\bin\ssr-stove-shield.exe"

d = open(MAN, "rb").read()
print(f"manifest {len(d):,} B")

# long ascii runs anywhere
runs = [m.group().decode("latin1") for m in re.finditer(rb"[\x20-\x7e]{8,80}", d)]
print("ascii runs >=8:", len(runs))
for s in runs[:40]:
    print("   ", repr(s))

for pat in [b"\x28\xb5\x2f\xfd", b"\x1f\x8b\x08", b"SSRC", b"ssrc", b"base_b",
            b"lang_en", b"bin_x86_64", b".sct", b"PLPcK", b"zstd", b"\x78\x9c"]:
    print(f"{pat!r}: {d.count(pat)}")

def H(b):
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

print("\nentropy per 256KB block (first 12 + last 4):")
nblk = len(d) // (256*1024)
idx = list(range(min(12, nblk))) + list(range(max(0, nblk-4), nblk))
for i in idx:
    b = d[i*256*1024:(i+1)*256*1024]
    print(f"  blk{i:3d} H={H(b):.3f} head={b[:12].hex()}")

print("\n=== exe keyword scan ===")
e = open(EXE, "rb").read()
for pat in [b"pigz", b"pcrevsz", b"spdi", b"res.bin", b"text.bin", b"data.indices",
            b"PLPcK", b"fs_pack", b"cdbm", b"manifest.ssra", b"SSRA", b"pcrev",
            b".ssrc", b"%s_%04u.ssrc", b"grp", b"GRP"]:
    c = e.count(pat)
    if c:
        off = e.find(pat)
        ctx = re.sub(rb"[^\x20-\x7e]", b".", e[max(0,off-50):off+70]).decode()
        print(f"{pat!r}: {c} first@{off:#x} ...{ctx}...")
