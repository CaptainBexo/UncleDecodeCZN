"""Inspect overlapping entries near stream start of base group."""
import struct
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
names = []
while len(names) < N:
    e = d.find(b"\x00", pos)
    names.append(d[pos:e])
    pos = e + 1
h2n = {xxhash.xxh64(nm).intdigest(): nm for nm in names}

recs = []
for i in range(N):
    f = struct.unpack_from("<8I2HI", d, A + i * S)
    nm = h2n.get((f[1] << 32) | f[0], b"?")
    recs.append((f, nm))

base = [(f, nm) for f, nm in recs if f[9] == 12]
low = sorted([(f, nm) for f, nm in base if f[2] < 400_000], key=lambda t: t[0][2])
print(f"records with in_off < 400k: {len(low)}")
for f, nm in low[:40]:
    print(f"  in_off={f[2]:>8,} stored={f[4]:>8,} raw={f[5]:>8,} flag={f[8]} f3={f[3]} name={nm.decode('utf-8','replace')[:60]}")