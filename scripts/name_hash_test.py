"""Test positional name<->record mapping + name-hash fields."""
import struct
import xxhash, zlib

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
d = open(MAN, "rb").read()

A, B, S = 0x760, 0x3573c8, 40
N = (B - A) // S

# walk names from file-names blob start (after 57 chunk names)
pos = 0x3573c8
names = []
for _ in range(58):  # 57 chunk names
    end = d.find(b"\x00", pos)
    names.append(d[pos:end])
    pos = end + 1
print("chunk names:", len(names), names[:3], names[-2:])
file_names_start = pos
print("file names start:", hex(file_names_start))

names = []
while pos < len(d) - 1 and len(names) < N + 10:
    end = d.find(b"\x00", pos)
    if end == -1:
        break
    nm = d[pos:end]
    if len(nm) == 0 or len(nm) > 300:
        break
    names.append(nm)
    pos = end + 1
print(f"walked {len(names)} file names (expect {N}); last: {names[-3:]}")
print("non-ascii names:", sum(1 for n in names if any(c > 0x7e for c in n)))

# positional hash test
ok = {"sum32": 0, "crc32": 0, "xxh32": 0, "xxh64lo": 0, "xxh64hi": 0, "sum32swap": 0}
tests = 0
for i in range(0, min(N, len(names)), 37):
    off = A + i * S
    A0, A1 = struct.unpack_from("<II", d, off)
    nm = names[i]
    if not nm:
        continue
    tests += 1
    s32 = xxhash.xxh32(nm).intdigest()
    x64 = xxhash.xxh64(nm).intdigest()
    if zlib.crc32(nm) == A0: ok["crc32"] += 1
    if s32 == A0: ok["xxh32"] += 1
    if s32 == A1: ok["sum32swap"] += 1
    if (x64 & 0xFFFFFFFF) == A0: ok["xxh64lo"] += 1
    if (x64 >> 32) == A0: ok["xxh64hi"] += 1
print(f"tests={tests} scores: {ok}")

# if no match, print comparisons for first 5
for i in range(5):
    off = A + i * S
    A0, A1 = struct.unpack_from("<II", d, off)
    nm = names[i]
    print(f"#{i} name={nm[:50]!r}")
    print(f"   rec +0={A0:08x} +4={A1:08x} | xxh32={xxhash.xxh32(nm).intdigest():08x} crc32={zlib.crc32(nm):08x} xxh64={xxhash.xxh64(nm).intdigest():016x}")
