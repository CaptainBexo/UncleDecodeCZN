"""Printable strings in sct2 + exe string-table neighborhood."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

P = Pack()
OUT = r"D:\UncleDecodeCZN\extract"

for t in ["face/portrait/1052_front.sct", "img/btn_dark_exit.sct", "face/character/face_character_1024_panic.sct"]:
    b = P.extract(t)
    print(f"\n=== {t} len={len(b):,} ==")
    runs = re.findall(rb"[\x20-\x7e]{4,}", b[:4200])
    for r in runs[:40]:
        print("   ", r.decode())

exe = open(r"E:\Games\ChaosZeroNightmare\bin\ssr-stove-shield.exe", "rb").read()
# string neighborhood around sct2 string
j = exe.find(b"sct2 decoding error")
print("\n=== exe around 'sct2 decoding error' ===")
seg = exe[j-600:j+600]
for r in re.findall(rb"[\x20-\x7e]{5,}", seg):
    print("   ", r.decode(errors="replace"))
# search field-name-ish strings
for pat in [b"proc", b"surface", b"pitch", b"block_size", b"mip"]:
    cnt = exe.count(pat)
    print(f"exe count {pat}: {cnt}")