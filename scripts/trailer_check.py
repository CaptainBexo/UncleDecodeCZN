"""Confirm chunk trailer layout + manifest hash8 vs xxh64(payload)."""
import os, struct, sys
import xxhash
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

P = Pack()
CH = P.chunks_dir
name = "base_b00_0.ssrc"
p = os.path.join(CH, name)
dd = open(p, "rb").read()
tail = dd[-16:]
print("trailer hex:", tail.hex())
print("trailer ascii:", tail[:4], "id:", struct.unpack_from("<I", tail, 4)[0], "hash:", hex(struct.unpack_from("<Q", tail, 8)[0]))
payload = dd[:-16]
h = xxhash.xxh64(payload).intdigest()
print("xxh64(payload):", hex(h), "== trailer?", h == struct.unpack_from("<Q", tail, 8)[0])
print("file size:", len(dd), "payload:", len(payload))

# manifest chunk table entry for this chunk
for c in P.chunks:
    if c.get("name") == name:
        print("manifest entry: cid=", c["cid"], "gid=", c["gid"], "pay=", c["pay"], "size=", c["size"], "xh=", hex(c["xh"]))
        print("manifest xh == xxh64(payload)?", c["xh"] == h)
        break