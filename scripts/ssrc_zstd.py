"""Try zstd-decompress .ssrc chunks; walk frames manually if needed."""
import glob, io, os, sys
import zstandard as zstd

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"

def try_stream(d):
    try:
        r = zstd.ZstdDecompressor().stream_reader(io.BytesIO(d))
        out = r.read()
        return ("stream", out)
    except Exception as e:
        return ("err", f"{type(e).__name__}: {e}")

def walk_frames(d):
    """Find zstd magics, decompress frame by frame, tally."""
    MAGIC = b"\x28\xb5\x2f\xfd"
    offs = []
    i = d.find(MAGIC)
    while i != -1:
        offs.append(i)
        i = d.find(MAGIC, i + 1)
    if not offs:
        return None
    total = bytearray()
    ok = 0
    for k, o in enumerate(offs):
        try:
            dobj = zstd.ZstdDecompressor().decompressobj()
            out = dobj.decompress(d[o:])
            total += out
            ok += 1
        except Exception:
            break
    return (ok, len(offs), bytes(total[:64]), len(total))

for name in sys.argv[1:] or ["lang_en_b00_0.ssrc", "lang_en_b01_0.ssrc", "lang_en_b03_0.ssrc", "bin_x86_64_b00_0.ssrc"]:
    p = os.path.join(CH, name)
    d = open(p, "rb").read()
    print("=" * 70)
    print(name, len(d), "B; magics:", d.count(b"\x28\xb5\x2f\xfd"))
    kind, res = try_stream(d)
    if kind == "stream":
        print(f"  stream OK -> {len(res)} B decompressed; head: {res[:80]!r}")
        open(os.path.join(r"D:\UncleDecodeCZN\cache_out", name + ".dec"), "wb").write(res)
    else:
        print("  stream failed:", res)
        w = walk_frames(d)
        print("  walk:", w[0] if w else None, "/", w[1] if w else None, "frames; out:", w[2] if w else None, "total", w[3] if w else None)
