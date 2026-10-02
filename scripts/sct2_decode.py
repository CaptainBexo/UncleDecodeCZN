"""SCT2 payload decode attempts + multi-file header compare."""
import os, struct, sys, zlib, json
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

P = Pack()
OUT = r"D:\UncleDecodeCZN\extract"
os.makedirs(OUT, exist_ok=True)

def u32s(b, off, n, base=0):
    return [(hex(o + base), struct.unpack_from("<I", b, o)[0]) for o in range(off, off + 4 * n, 4)]

targets = [
    "face/portrait/1052_front.sct",
    "card_illustration/start_1061_02.sct",
    "common/icon_item.sct" if False else "img/btn_dark_exit.sct",
]
names = json.load(open(r"D:\UncleDecodeCZN\decoded\names_all.json"))
# find some extra sct files
extra = [n for n in names if n and n.endswith(".sct") and n.startswith("face/")][:6]
print("face sct sample:", extra)

files = []
for t in targets + extra:
    try:
        b = P.extract(t)
        files.append((t, b))
    except Exception as e:
        print("ERR", t, e)

for t, b in files[:8]:
    print(f"\n=== {t}: {len(b):,} ===")
    if b[:4] != b"SCT2":
        print("  not SCT2:", b[:8].hex())
        continue
    n = len(b)
    print("  u32[1..12]:", [v for _, v in u32s(b, 4, 12)])
    # search & try decompress
    for sig, lab in [(b"\x78\x9c", "zlib"), (b"\x78\x01", "zlib-01"), (b"\x78\xda", "zlib-da"),
                     (b"\x28\xb5\x2f\xfd", "zstd"), (b"\x5d\x00\x00", "lzma?")]:
        j = b.find(sig)
        while j != -1:
            try:
                if lab == "zstd":
                    import zstandard as zstd
                    out = zstd.ZstdDecompressor().decompress(b[j:])
                else:
                    out = zlib.decompress(b[j:])
                print(f"  {lab} @{j:#x} -> decompressed {len(out):,} bytes, head {out[:8].hex()}")
                open(os.path.join(OUT, os.path.basename(t) + f".{lab}.raw"), "wb").write(out)
                break
            except Exception as e:
                j = b.find(sig, j + 1)
    # tail u32s
    print("  tail u32:", [hex(struct.unpack_from('<I', b, len(b)-4*i)[0]) for i in (2, 1)])