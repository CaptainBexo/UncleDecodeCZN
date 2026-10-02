"""Correlate manifest 40B file-record fields with known frame data."""
import json, struct, zlib
import xxhash

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
FR = r"D:\UncleDecodeCZN\decoded\frames.jsonl"
d = open(MAN, "rb").read()

A, B, S = 0x760, 0x3573c8, 40
N = (B - A) // S
print(f"records: {N}")

# known frames for lang_en chunks
lang_frames = []
for line in open(FR, encoding="utf-8"):
    r = json.loads(line)
    if r["chunk"].startswith("lang_en"):
        lang_frames.append(r)
print("lang_en frames:", len(lang_frames), "sample:", lang_frames[:3])

# find records containing any lang frame's (in_len, out_len) pair
pairs = [(r["in_len"], r["out_len"]) for r in lang_frames]
found = 0
for i in range(N):
    off = A + i * S
    vals = struct.unpack_from("<8IHI", d, off)  # 8 u32, u16, u16, u32
    for in_len, out_len in pairs:
        if in_len in vals[:8] and out_len in vals[:8]:
            print(f"rec#{i} @{off:#x}: {vals}")
            print(f"   hex: {d[off:off+S].hex(' ')}")
            found += 1
            break
    if found >= 12:
        break
print("matched records:", found)

# name blob base tests with record0 name_off
name_off = struct.unpack_from("<I", d, A + 4)[0]
for base in [0x3573c8, 0x3577c8, 0x3576c8, 0x357800, 0x3577e8]:
    pos = base + name_off
    end = d.find(b"\x00", pos, pos + 200)
    nm = d[pos:end]
    print(f"base {base:#x} + {name_off} = {pos:#x}: {nm[:80]!r}")

# record0 full + A field vs name hash tests
rec0 = d[A:A+S]
print("\nrec0:", rec0.hex(" "))
for base in [0x3573c8, 0x3577c8, 0x357800]:
    pos = base + name_off
    end = d.find(b"\x00", pos, pos + 200)
    nm = d[pos:end]
    print(f"cand name {nm[:60]!r}: crc32={zlib.crc32(nm):08x} xxh32={xxhash.xxh32(nm).intdigest():08x} u32@+0={struct.unpack_from('<I', rec0, 0)[0]:08x}")

# dump first 6 records hex+fields
print("\nfirst 8 records:")
for i in range(8):
    off = A + i * S
    vals = struct.unpack_from("<8IHI", d, off)
    print(f"#{i} @{off:#x}: {vals}")
