"""Final wrap rule verification + position table build."""
import json, os, struct
from collections import Counter, defaultdict
import zstandard as zstd
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

# names
pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
names = []
while len(names) < N:
    e = d.find(b"\x00", pos)
    names.append(d[pos:e].decode("utf-8", "replace"))
    pos = e + 1
h2n = {xxhash.xxh64(n.encode()).intdigest(): n for n in names}

recs = []
for i in range(N):
    f = struct.unpack_from("<8I2HI", d, A + i * S)
    nm = h2n.get((f[1] << 32) | f[0], "?")
    recs.append((i, f, nm))

def show(label, name):
    for i, f, nm in recs:
        if nm == name:
            in_off, f3, stored, raw, f6, name_off, flag, grp, fC = (
                f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9], f[10])
            print(f"{label}: rec#{i} in_off={in_off:,} f3={f3} stored={stored:,} raw={raw:,} "
                  f"f6={f6} flag={flag} grp={grp} fC={fC}")
            print(f"   real(pre)={in_off:,}  real(post)={in_off + (1<<32):,}")
            return in_off, f3, stored, raw, flag
    print(f"{label}: NOT FOUND")
    return None

show("master.bank ", "sound/master.bank")
show("csb         ", "wnd/unit_mode_profile_content.csb")
show("1030.sct    ", "face/portrait/1030.sct")

# b00 first frames
walk = json.load(open(r"D:\UncleDecodeCZN\decoded\chunk_walk.json"))
fr = walk["base_b00_0.ssrc"]["frames"]
print("\nb00 first 3 frames (off, in_len, out_len):", fr[:3])
raws = walk["base_b00_0.ssrc"]["raws"]
print("b00 first 3 raw regions (off, next):", [(hex(a), hex(b)) for a, b in raws[:3]])
print("b00 raws count:", len(raws))

# f3 stats for records matching b20 frames (post-wrap known)
b20 = walk["base_b20_0.ssrc"]["frames"]
b20b = 4568804416
ok = 0; bad = 0
samp = [b20[k] for k in range(0, min(400, len(b20)), 7)]
for off, in_len, out_len in samp:
    real = b20b + off
    wrapped = real - (1 << 32)
    hits = [(i, f3v) for i, f, nm in recs for f3v in [f[3]]
            if f[2] == wrapped and f[4] == in_len and f[5] == out_len]
    if hits:
        ok += 1
        for i, f3v in hits:
            if f3v != 1:
                bad += 1
    else:
        bad += 1
print(f"\nb20 wrapped-offset record check: ok={ok} bad={bad}")
print("sample wrapped in_off values:", [hex((b20b + o) - (1 << 32)) for o, _, _ in samp[:5]])