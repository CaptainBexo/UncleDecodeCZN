"""Find file-record array: use SCT2 internal hash + dump region after chunk table."""
import struct

MAN = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\manifest.ssra"
DEC = r"D:\UncleDecodeCZN\decoded\lang_en_b00_0.bin"
d = open(MAN, "rb").read()
dec = open(DEC, "rb").read()

# SCT2 file #1 (first frame): SCT2 | u32 ? | u32 ? | ... 'hash' tag + u16 len + bytes
f = dec[:1787]
print("SCT2 head:", f[:48].hex())
tag = f.find(b"hash")
print("hash tag @", tag, "->", f[tag+4:tag+4+2].hex(), "payload:", f[tag+6:tag+6+32].hex())
h16 = f[tag+6:tag+6+16]

for label, needle in [("hash16", h16), ("hash16 BE?", h16[::-1]), ("first8", h16[:8]), ("last8", h16[8:16])]:
    offs, i = [], d.find(needle)
    while i != -1 and len(offs) < 8:
        offs.append(i); i = d.find(needle, i+1)
    print(f"manifest {label}: {[hex(o) for o in offs]}")

# dump manifest after chunk table 0x760..0x9a0
print("\nmanifest 0x760..0x8a0:")
for i in range(0x760, 0x8a0, 16):
    row = d[i:i+16]
    asc = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
    print(f"  {i:06x}: {row.hex(' '):<47} {asc}")

# where do file records live? sample known-length tail: dump last 512 bytes
print("\nmanifest tail 512:")
for i in range(len(d)-512, len(d), 16):
    row = d[i:i+16]
    asc = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
    print(f"  {i:06x}: {row.hex(' '):<47} {asc}")
