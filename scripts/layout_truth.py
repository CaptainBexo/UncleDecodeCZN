"""Resolve true stream layout: find master.bank content in chunks, cum tables, failing bytes."""
import json, os, struct, glob
import zstandard, xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
d = open(MAN, "rb").read()
A, S, N = 0x760, 40, 87529

# manifest chunk table
tbl = []
for i in range(57):
    o = 0x40 + i * 32
    cid, gid, fl = struct.unpack_from("<IHH", d, o)
    pay, size, xh = struct.unpack_from("<QQQ", d, o + 8)
    tbl.append({"i": i, "cid": cid, "gid": gid, "pay": pay, "size": size, "xh": xh})
names = []
pos = 0x3573c8
for _ in range(57):
    e = d.find(b"\x00", pos)
    names.append(d[pos:e].decode())
    pos = e + 1
for t, n in zip(tbl, names):
    t["name"] = n
base = [t for t in tbl if t["gid"] == 12]
print("base chunks in manifest order:")
cum = 0
for t in base:
    print(f"  {t['name']:32s} cid={t['cid']:2d} payload={t['pay']:>12,} cum0={cum:>13,}")
    cum += t["pay"]

# where is master.bank (in_off=3420355760)? find cum interval
need = 3420355760
c2 = 0
for t in base:
    if c2 <= need < c2 + t["pay"]:
        print(f"\nmaster.bank in_off lands in {t['name']} at local {need - c2:,}")
    c2 += t["pay"]

# find base_large_p0 head bytes on disk chunks
p0 = open(CH + r"\base_large_b7ed1933_p0.ssrc", "rb").read(64)
print("\np0 head32:", p0[:32].hex())
for f in glob.glob(CH + r"\base_*.ssrc"):
    dd = open(f, "rb").read()
    j = dd.find(p0[:24])
    if j != -1:
        print(f"  p0-head found in {os.path.basename(f)} @ {j:#x}")

# peek failing record bytes: wnd/unit_mode_profile_content.csb @ in_off, flag=1
recs = [struct.unpack_from("<8I2HI", d, A + i * S) for i in range(N)]
def find(name):
    h = xxhash.xxh64(name.encode()).intdigest()
    for i, f in enumerate(recs):
        if ((f[1] << 32) | f[0]) == h:
            return i, f
    return None, None

def read_at(need, ln):
    c2 = 0
    for t in base:
        if c2 <= need < c2 + t["pay"]:
            local = need - c2
            p = CH + "\\" + t["name"]
            if not os.path.exists(p):
                return f"{t['name']} not downloaded", None
            with open(p, "rb") as fh:
                fh.seek(local)
                avail = min(ln, t["pay"] - local)
                return f"{t['name']}@{local:,} avail={avail:,}", fh.read(avail)
        c2 += t["pay"]
    return "outside", None

i, f = find("wnd/unit_mode_profile_content.csb")
where, blob = read_at(f[2], min(f[4], 128))
print(f"\ncsb rec#{i}: in_off={f[2]:,} stored={f[4]} raw={f[5]} flag={f[8]} at {where}")
print("  hex:", blob[:64].hex())

i, f = find("face/portrait/1030.sct")
where, blob = read_at(f[2], 64)
print(f"\n1030.sct rec#{i}: in_off={f[2]:,} stored={f[4]} raw={f[5]} flag={f[8]} at {where}")
print("  hex:", blob[:64].hex())