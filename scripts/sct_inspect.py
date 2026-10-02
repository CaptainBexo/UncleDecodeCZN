"""Dump full name list + inspect SCT2 texture format."""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack
from collections import Counter

OUT = r"D:\UncleDecodeCZN\extract"
os.makedirs(OUT, exist_ok=True)

P = Pack()

# full name list cached
NAMES_JSON = r"D:\UncleDecodeCZN\decoded\names_all.json"
if os.path.exists(NAMES_JSON):
    names = json.load(open(NAMES_JSON))
else:
    # walk name blob: follow name_off pointers instead (robust)
    d = P.d
    base = P.name_base
    names = []
    for f in P.recs:
        no = f[7]
        e = d.find(b"\x00", base + no)
        names.append(d[base + no:e].decode("utf-8", "replace"))
    json.dump(names, open(NAMES_JSON, "w"))
print("total names:", len(names))

# dir inventory for image-related
top = Counter()
for n in names:
    top[n.split("/")[0]] += 1
print("top dirs:", top.most_common(25))

img_ext = Counter()
for n in names:
    ex = os.path.splitext(n)[1]
    if ex in (".sct", ".atlas", ".png", ".csb", ".scsp", ".jpg", ".webp"):
        img_ext[ex] += 1
print("image-ish ext:", img_ext.most_common())

# save a sample of portrait + card names
for pref in ("face/portrait/", "card_illustration/", "background/", "encounter_illustration/", "img/"):
    lst = [n for n in names if n.startswith(pref)][:8]
    print(f"\n{pref} ({sum(1 for n in names if n.startswith(pref))}):")
    for n in lst:
        print("  ", n)

# extract 1030.sct
b = P.extract("face/portrait/1030.sct")
open(os.path.join(OUT, "1030.sct"), "wb").write(b)
print("\n1030.sct:", len(b), "head:", b[:16].hex())

# header interp
magic = b[:4]
u = struct.unpack_from("<12I", b, 4)
print("magic", magic, "u32s[4:]:", u)
# scan inner magics
for sig, lab in [(b"\x89PNG", "PNG"), (b"DDS ", "DDS"), (b"PVR", "PVR"), (b"\xabKTX", "KTX"),
                 (b"KTX2", "KTX2"), (b"\x28\xb5\x2f\xfd", "zstd"), (b"\x78\x9c", "zlib9c"),
                 (b"\x78\x01", "zlib01"), (b"\x78\xda", "zlibda"), (b"ETC1", "ETC1"),
                 (b"ASTC", "ASTC"), (b"\x13\xab\xa1", "ASTC-magic")]:
    j = b.find(sig)
    if j != -1:
        print(f"  inner {lab}: @{j:#x}")
# entropy of payload after 64
import math
payload = b[0x40:]
if payload:
    freq = Counter(payload[:1 << 20])
    ent = -sum((c / len(payload[:1 << 20])) * math.log2(c / len(payload[:1 << 20])) for c in freq.values())
    print("payload entropy (first 1MB):", round(ent, 3))