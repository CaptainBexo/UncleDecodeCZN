"""Inspect multi-part records + failing entries."""
import json, struct
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

recs = [struct.unpack_from("<8I2HI", d, A + i * S) for i in range(N)]

def find(name):
    h = xxhash.xxh64(name.encode()).intdigest()
    out = []
    for i, f in enumerate(recs):
        if ((f[1] << 32) | f[0]) == h:
            out.append((i, f))
    return out

for name in ["sound/master.bank", "wnd/unit_mode_profile_content.csb", "face/portrait/1030.sct"]:
    print("=" * 70)
    print(name)
    for i, f in find(name):
        print(f"  rec#{i}: in_off={f[2]:,} f3={f[3]} stored={f[4]:,} raw={f[5]:,} f6={f[6]} name_off={f[7]} flag={f[8]} group={f[9]} fC={f[10]}")

# records per name
from collections import Counter
h2cnt = Counter((f[1] << 32) | f[0] for f in recs)
multi = [h for h, c in h2cnt.items() if c > 1]
print(f"\nnames with multiple records: {len(multi)}")
print("max records per name:", max(h2cnt.values()))

# distribution of record counts
print(Counter(h2cnt.values()))

# hex peek at failing entries
def peek(f, label):
    path = CH + r"\base_b28_0.ssrc"  # placeholder
    print(label, "would need group/chunk resolve; f2=", f[2])

# check f3 semantics: for multi-record names, f3 values
import itertools
for h in multi[:5]:
    rows = [(i, f) for i, f in enumerate(recs) if ((f[1] << 32) | f[0]) == h]
    print("multi hash", hex(h), [(i, f[3], f[4], f[5], f[8], f[9]) for i, f in rows[:6]])
