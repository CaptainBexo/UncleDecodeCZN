"""Debug .ssrc frame layout: offsets of zstd magics, gaps, per-frame decode."""
import os, sys
import zstandard as zstd

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
MAGIC = b"\x28\xb5\x2f\xfd"

def magics(d):
    offs, i = [], d.find(MAGIC)
    while i != -1:
        offs.append(i); i = d.find(MAGIC, i + 1)
    return offs

for name in sys.argv[1:]:
    d = open(os.path.join(CH, name), "rb").read()
    offs = magics(d)
    print("=" * 72)
    print(name, f"{len(d):,} B, {len(offs)} zstd magics")
    for k, o in enumerate(offs[:8]):
        dobj = zstd.ZstdDecompressor().decompressobj()
        try:
            out = dobj.decompress(d[o:])
            ok = f"OK out={len(out):,} head={out[:20].hex()}"
        except Exception as e:
            ok = f"ERR {e}"
        prev = d[max(0, o-16):o].hex()
        print(f"  magic#{k} @{o:#x}  prev16={prev}  {ok}")

# focused: lang_en_b00 variations of decode loop
name = "lang_en_b00_0.ssrc"
d = open(os.path.join(CH, name), "rb").read()
print("---- decode loop trace:", name)
pos, it = d, 0
while pos and it < 20:
    dobj = zstd.ZstdDecompressor().decompressobj()
    try:
        out = dobj.decompress(pos)
    except Exception as e:
        print(f"  iter{it}: ERR {e}; pos starts {pos[:16].hex()} len={len(pos)}")
        break
    nxt = dobj.unused_data
    print(f"  iter{it}: out={len(out)} unused={len(nxt) if nxt else 0} nexthead={nxt[:12].hex() if nxt else '-'}")
    if not nxt: break
    pos = nxt; it += 1
