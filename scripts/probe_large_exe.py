"""Probe base_large parts + scan exe strings for chunk/synth pipeline."""
import os, re

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
EXE = r"E:\Games\ChaosZeroNightmare\bin\ssr-stove-shield.exe"

for n in ["base_large_b7ed1933_p0.ssrc", "base_large_b7ed1933_p1.ssrc"]:
    p = os.path.join(CH, n)
    d = open(p, "rb").read(256)
    print(n, "size", os.path.getsize(p))
    print("  head256:", d[:128].hex())
    print("  ascii:", re.sub(rb"[^\x20-\x7e]", b".", d[:128]).decode())
    with open(p, "rb") as f:
        f.seek(-64, 2)
        print("  tail64:", f.read(64).hex())

print("\n=== exe string scan ===")
data = open(EXE, "rb").read()
print("exe size", len(data))
pats = [b"ssrc", b"SSRC", b"synth", b"chunks_relative", b"prepare", b".ssrc",
        b"base_large", b"chunks", b"synthesize", b"prepared"]
for pat in pats:
    offs, i = [], data.find(pat)
    while i != -1 and len(offs) < 12:
        offs.append(i); i = data.find(pat, i + 1)
    print(f"\n{pat!r}: {len(offs)} shown")
    for o in offs[:8]:
        ctx = data[max(0, o-60):o+80]
        s = re.sub(rb"[^\x20-\x7e]", b".", ctx).decode()
        print(f"  @{o:#x}: ...{s}...")
