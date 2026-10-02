"""Locate name table in manifest.ssra and dump entry context."""
import re

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()

def show(off, before=32, after=96, label=""):
    print(f"--- {label} @{off:#x}")
    b = d[max(0,off-before):off+after]
    for i in range(0, len(b), 16):
        chunk = b[i:i+16]
        asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
        print(f"  {max(0,off-before)+i:08x}: {chunk.hex(' '):<47} {asc}")

# first occurrences or samples
for pat, label in [(b"base_b00", "base_b00"), (b"base_b32", "base_b32"),
                   (b"lang_en_b00", "lang_en_b00"), (b"bin_x86_64", "bin_x86_64"),
                   (b".ssrc", ".ssrc"), (b"group_", "group_")]:
    i = d.find(pat)
    while i != -1:
        # only show if surrounded by printable-ish (name table region)
        ctx = d[max(0,i-100):i+120]
        printable = sum(1 for c in ctx if 32 <= c < 127 or c == 0)
        if printable > len(ctx) * 0.75:
            show(i, 48, 120, label + " (printable ctx)")
            break
        i = d.find(pat, i + 1)

# density scan: find first region where 2KB window printable ratio > 0.9
WIN = 2048
prev_report = 0
for off in range(0, len(d) - WIN, WIN // 2):
    w = d[off:off+WIN]
    pr = sum(1 for c in w if 32 <= c < 127 or c == 0) / WIN
    if pr > 0.90:
        print(f"\nFIRST dense-name region @{off:#x} printable={pr:.2f}")
        show(off, 0, 256, "name table start")
        break

# count density regions (name tables)
regions = []
off = 0
while off < len(d) - WIN:
    w = d[off:off+WIN]
    pr = sum(1 for c in w if 32 <= c < 127 or c == 0) / WIN
    if pr > 0.90:
        regions.append(off)
        off += WIN
    else:
        off += WIN // 2
print(f"\ndense regions: {len(regions)}, first few: {[hex(x) for x in regions[:6]]}...{hex(regions[-1]) if regions else ''}")

# sample names from a few dense regions
for r in regions[:3] + regions[-2:]:
    names = re.findall(rb"[\x21-\x7e]{6,}[a-zA-Z0-9_/\.\-@]{0,80}", d[r:r+WIN])
    print(f"\n@{r:#x}: {[n.decode('latin1') for n in names[:12]]}")
