"""Scan large chunks for zstd frames + locate known files (csb 20324, 1030.sct 1483818)."""
import io, os
import zstandard as zstd

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
MAGIC = b"\x28\xb5\x2f\xfd"

for name in ["base_large_b7ed1933_p0.ssrc", "base_large_b7ed1933_p1.ssrc", "base_b28_1.ssrc"]:
    d = open(os.path.join(CH, name), "rb").read()
    print("=" * 70)
    print(f"{name} size={len(d):,}")
    offs = []
    i = d.find(MAGIC)
    while i != -1 and len(offs) < 4000:
        offs.append(i)
        i = d.find(MAGIC, i + 1)
    print(f"  zstd magics anywhere: {len(offs)}; first 10 offsets: {[hex(o) for o in offs[:10]]}")
    al = sum(1 for o in offs if o % 16 == 0)
    print(f"  aligned(16) magics: {al}")
    hits = []
    for o in offs[:2000]:
        try:
            dobj = zstd.ZstdDecompressor().decompressobj()
            out = dobj.decompress(d[o:])
            hits.append((o, len(out), out[:12].hex()))
        except Exception:
            pass
    print(f"  decompressable: {len(hits)}")
    for o, ln, hd in hits[:20]:
        print(f"    @{o:#x} out={ln:,} head={hd}")
    for o, ln, hd in hits:
        if ln in (20324, 1483818):
            print(f"    *** FOUND target size {ln} @{o:#x} head={hd}")
    # search for known large raw sizes as sanity
    for probe, label in [(b"RIFF", "RIFF"), (b"BKHD", "BKHD"), (b"FMT ", "FMT "), (b"SCT2", "SCT2")]:
        c = d.count(probe)
        if c:
            print(f"  {label}: {c} occurrences")