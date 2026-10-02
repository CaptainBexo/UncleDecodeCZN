"""Pin chunk-table record layout + find file-record array."""
import struct

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()

known_sizes = {
    "lang_en_b00": 259776, "lang_en_b01": 181040, "lang_en_b02": 76208,
    "lang_en_b03": 15459312, "bin_x86_64": 18277776, "base_b00": 236720144,
    "base_b01": 218529728, "base_b02": 207107424, "base_b28_1": 40427568,
    "base_large_p0": 268435472, "base_large_p1": 92871408,
}
print("== u64 positions of known chunk sizes:")
pos = {}
for k, v in known_sizes.items():
    b = struct.pack("<Q", v)
    i = d.find(b, 0, 0x3573c8)
    if i == -1:
        b32 = struct.pack("<I", v)
        j = d.find(b32, 0, 0x3573c8)
        print(f"  {k}: u64 none; u32 @{hex(j) if j>=0 else '-'}")
        if j >= 0: pos[k] = j
    else:
        pos[k] = i
        print(f"  {k:14s} u64 @{i:#07x}")
order = sorted(pos.items(), key=lambda kv: kv[1])
print("\nsorted offsets + deltas:")
prev = None
for k, o in order:
    delta = o - prev if prev is not None else 0
    print(f"  {o:#07x} (+{delta:#x}) {k}")
    prev = o

# hexdump 0x140-0x1b0 and 0x2e0-0x350
for a, b in [(0x140, 0x1b0), (0x2e0, 0x360)]:
    print(f"\nhexdump {a:#x}..{b:#x}:")
    for i in range(a, b, 16):
        row = d[i:i+16]
        asc = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
        print(f"  {i:06x}: {row.hex(' '):<47} {asc}")

# also: check what follows each known size: 8B after size = trailer hash?
print("\nsize followed by 8 bytes / 16 bytes:")
for k, o in pos.items():
    print(f"  {k:14s} @{o:#x}: next8={d[o+8:o+16].hex()} next16={d[o+16:o+32].hex()} prev8={d[o-8:o].hex()}")
