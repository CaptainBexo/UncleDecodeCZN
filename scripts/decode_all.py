"""Decompress all .ssrc chunks (concatenated zstd frames + 16B SSRC trailer)."""
import glob, os, sys, time
import zstandard as zstd

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
OUT = r"D:\UncleDecodeCZN\decoded"
os.makedirs(OUT, exist_ok=True)

def decode(fin, fout):
    """Return (frames, out_bytes, head32, trailer_hex)."""
    d = open(fin, "rb").read()
    trailer = d[-16:].hex()
    out = open(fout, "wb")
    frames = 0
    pos_data = d
    while pos_data:
        dobj = zstd.ZstdDecompressor().decompressobj()
        try:
            chunk_out = dobj.decompress(pos_data)
        except zstd.ZstdError:
            break  # trailer / junk
        out.write(chunk_out)
        frames += 1
        nxt = dobj.unused_data
        if not nxt:
            break
        pos_data = nxt
    out.close()
    sz = os.path.getsize(fout)
    head = open(fout, "rb").read(32)
    return frames, sz, head, trailer

for p in sorted(glob.glob(os.path.join(CH, "*.ssrc"))):
    name = os.path.basename(p)[:-5]
    fout = os.path.join(OUT, name + ".bin")
    t0 = time.time()
    frames, sz, head, trailer = decode(p, fout)
    print(f"{name:32s} frames={frames:3d} out={sz:>13,} head={head[:16].hex()} {time.time()-t0:5.1f}s")
