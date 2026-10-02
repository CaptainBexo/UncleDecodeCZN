"""Inventory image records: flag distribution, raw-stored candidates."""
import json, os, sys, struct
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

P = Pack()
names = json.load(open(r"D:\UncleDecodeCZN\decoded\names_all.json"))

img_exts = {".sct", ".png", ".webp", ".atlas"}
rows = []
for i, f in enumerate(P.recs):
    nm = names[i]
    if not nm:
        continue
    ext = os.path.splitext(nm)[1]
    if ext in img_exts:
        rows.append((nm, ext, f[3], f[4], f[5], f[8]))  # f3 wrap, stored, raw, flag

print("total image records:", len(rows))
print("by ext:", Counter(r[1] for r in rows))
print("\nflag distribution by ext:")
for ext in img_exts:
    c = Counter(r[5] for r in rows if r[1] == ext)
    print(f"  {ext}: {dict(c)}")
print("\nsct by (flag, f3):", Counter((r[5], r[2]) for r in rows if r[1] == ".sct"))

raw_sct = [r for r in rows if r[1] == ".sct" and r[5] == 0]
print(f"\nraw sct count: {len(raw_sct)}")
raw_sct.sort(key=lambda r: r[3])
for r in raw_sct[:15]:
    print(f"  {r[0]:70s} stored={r[3]:>10,} raw={r[4]:>10,} f3={r[2]}")

print("\nlargest sct (compressed) as candidates:")
comp_sct = sorted([r for r in rows if r[1] == ".sct" and r[5] == 1], key=lambda r: -r[4])[:10]
for r in comp_sct:
    print(f"  {r[0]:70s} stored={r[3]:>10,} raw={r[4]:>10,}")
json.dump([list(r) for r in rows], open(r"D:\UncleDecodeCZN\decoded\img_rows.json", "w"))