"""Final index dump (fixed struct) + sample extraction test."""
import json, struct
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()
A, B, S, N = 0x760, 0x3573c8, 40, 87529

pos = 0x3573c8
for _ in range(57):
    pos = d.find(b"\x00", pos) + 1
names = []
while len(names) < N:
    e = d.find(b"\x00", pos)
    names.append((pos, d[pos:e]))
    pos = e + 1

h2n = {}
for off, nm in names:
    h2n[xxhash.xxh64(nm).intdigest()] = nm

with open(r"D:\UncleDecodeCZN\decoded\file_index.jsonl", "w", encoding="utf-8") as w:
    gcount = {}
    for i in range(N):
        o = A + i * S
        f0, f1, f2, f3, f4, f5, f6, f7, flagA, grpB, fC = struct.unpack_from("<8I2HI", d, o)
        nm = h2n[(f1 << 32) | f0]
        gcount[grpB] = gcount.get(grpB, 0) + 1
        w.write(json.dumps({"i": i, "name": nm.decode("utf-8", "replace"),
                            "in_off": f2, "f3": f3, "stored": f4, "raw": f5,
                            "f6": f6, "name_off": f7, "flag": flagA, "group": grpB,
                            "fC": fC}, ensure_ascii=False) + "\n")
print("wrote file_index.jsonl")
print("group histogram:", sorted(gcount.items()))
print("flag histogram:", {})
# f3/fC stats
st = {}
for i in range(0, N, 13):
    f = struct.unpack_from("<8I2HI", d, A + i * S)
    st.setdefault("f3", set()).add(f[3]); st.setdefault("fC", set()).add(f[10]); st.setdefault("f6", set()).add(f[6])
print({k: sorted(list(v))[:6] for k, v in st.items()})
