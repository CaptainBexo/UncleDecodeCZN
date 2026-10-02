"""Test 'hash' TLV candidate algorithms on 1030.sct."""
import sys, os, struct, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack
import xxhash

P = Pack()
targets = ["face/portrait/1030.sct", "img/btn_dark_exit.sct", "card_illustration/start_1061_02.sct"]
for t in targets:
    b = P.extract(t)
    # find TLVs: scan for b"hash" occurrence
    j = b.find(b"hash")
    # value starts after b"hash"
    v = b[j+4:j+4+16]
    print(f"\n{t}: hash TLV = {v.hex()} (at {j:#x})")
    cands = {}
    cands["xxh3_128(file)"] = xxhash.xxh3_128(b).digest()
    cands["xxh3_128(0x24:)"] = xxhash.xxh3_128(b[0x24:]).digest()
    cands["xxh3_128(0x50:)"] = xxhash.xxh3_128(b[0x50:]).digest()
    cands["md5(file)"] = hashlib.md5(b).digest()
    cands["md5(0x50:)"] = hashlib.md5(b[0x50:]).digest()
    cands["sha1_16(file)"] = hashlib.sha1(b).digest()[:16]
    # the lz4 payload region
    do = struct.unpack_from("<I", b, 12)[0]
    cands[f"xxh3_128(data@{do})"] = xxhash.xxh3_128(b[do:]).digest()
    doff = struct.unpack_from("<I", b, 12)[0]
    if doff + 8 <= len(b):
        comp = struct.unpack_from("<I", b, doff + 4)[0]
        try:
            import lz4.block
            raw = lz4.block.decompress(b[doff+8:doff+8+comp])
            cands["xxh3_128(lz4_out)"] = xxhash.xxh3_128(raw).digest()
            cands["md5(lz4_out)"] = hashlib.md5(raw).digest()
        except Exception:
            pass
    for k, d in cands.items():
        m = "MATCH!" if d[:16] == v else ""
        print(f"   {k:26s} {d.hex()[:32]} {m}")