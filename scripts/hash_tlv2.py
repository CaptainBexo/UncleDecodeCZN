"""Retest 'hash' TLV with correct slicing + brute variants."""
import sys, os, struct, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack
import xxhash, lz4.block

P = Pack()
for t in ["face/portrait/1030.sct", "img/btn_dark_exit.sct"]:
    b = P.extract(t)
    j = b.find(b"hash")
    v = b[j + 6: j + 6 + 16]
    doff = struct.unpack_from("<I", b, 12)[0]
    unc, comp = struct.unpack_from("<II", b, doff)
    print(f"\n{t} hash={v.hex()} doff={doff} unc={unc:,} comp={comp:,} len={len(b):,}", flush=True)
    try:
        raw_lz4 = lz4.block.decompress(b[doff + 8: doff + 8 + comp], uncompressed_size=unc)
    except Exception as e:
        print("  lz4 fail:", e, flush=True)
        raw_lz4 = b""
    zeroed = bytearray(b); zeroed[j + 6: j + 6 + 16] = b"\x00" * 16
    cands = {
        "xxh3_128(file)": xxhash.xxh3_128(b).digest(),
        "xxh3_128(zeroed)": xxhash.xxh3_128(bytes(zeroed)).digest(),
        "xxh3_128(lz4_out)": xxhash.xxh3_128(raw_lz4).digest(),
        "xxh3_128(from0x50)": xxhash.xxh3_128(b[0x50:]).digest(),
        "xxh3_128(header0x24..0x48)": xxhash.xxh3_128(b[0x24:0x48]).digest(),
        "md5(lz4_out)": hashlib.md5(raw_lz4).digest(),
        "md5(file)": hashlib.md5(b).digest(),
        "md5(zeroed)": hashlib.md5(bytes(zeroed)).digest(),
        "blake2b16(file)": hashlib.blake2b(b, digest_size=16).digest(),
        "sha256_16(lz4_out)": hashlib.sha256(raw_lz4).digest()[:16],
        "xxh128_seed1(lz4_out)": xxhash.xxh3_128(raw_lz4, seed=1).digest(),
    }
    print(f"\n{t} hash={v.hex()}")
    for k, d in cands.items():
        print(f"   {k:28s} {d.hex()} {'<<< MATCH' if d[:16] == v else ''}")