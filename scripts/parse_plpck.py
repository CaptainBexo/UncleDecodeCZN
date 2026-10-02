"""Parse PLPcK index from decoded bin_x86_64 chunk."""
import re, struct, sys

P = r"D:\UncleDecodeCZN\decoded\bin_x86_64_b00_0.bin"
d = open(P, "rb").read()
print("size", len(d))
print("head 128:", d[:128].hex())
print("head ascii:", re.sub(rb"[^\x20-\x7e]", b".", d[:128]).decode())
print(d[:16].hex(), "magic-tag")

# find name-like runs ending with '*'
pat = re.compile(rb"[\x20-\x26\x28-\x7e]{3,200}\*")
first = None
names = []
for m in pat.finditer(d[:3_000_000]):
    s = m.group()[:-1]
    # name-ish: contains / or . and no spaces
    if b" " in s: continue
    if b"." not in s and b"/" not in s: continue
    names.append((m.start(), m.end()))
    if len(names) >= 40: break
print(f"\n{len(names)} name candidates; first 25:")
for off, end in names[:25]:
    print(f"  @{off:#x}: {d[off:end-1].decode('latin1')}")

if names:
    tbl = names[0][0]
    print(f"\nname-table start guess: {tbl:#x} ({tbl})")
    print("bytes before table (last 64):", d[tbl-64:tbl].hex())
    # try sequential parse with 35-byte records
    pos = tbl
    ok = 0
    for i in range(10):
        star = d.find(b"*", pos)
        if star == -1 or star - pos > 300: break
        nm = d[pos:star]
        rec = d[star+1:star+36]
        if len(rec) < 35: break
        rev, = struct.unpack_from("<I", rec, 0)
        h = rec[4:20].hex()
        f20, = struct.unpack_from("<I", rec, 20)
        flag = rec[24]
        f25, = struct.unpack_from("<I", rec, 25)
        f29, = struct.unpack_from("<H", rec, 29)
        f31, = struct.unpack_from("<I", rec, 31)
        print(f"  {nm.decode('latin1')[:60]:60s} rev={rev} hash={h} f20={f20} flag={flag} f25={f25} f29={f29} f31={f31}")
        pos = star + 36
        ok += 1
    print("sequential ok:", ok)
