"""SCT2 decoder -> PNG. Spec from community tools (refs/) + reverse eng.

Header (SCT2, LE):
  0x00 "SCT2" | 0x04 u32 total | 0x08 u32 unk | 0x0C u32 data_offset
  0x10 u32 block_w (4/6/8) | 0x14 u32 pixel_format | 0x18 u16 w | 0x1A u16 h
  0x1C u16 tw | 0x1E u16 th | 0x20 u32 flags | TLV meta from 0x24 ("proc","hash")
At data_offset: u32 uncompressed_size, u32 compressed_size, then LZ4 block.
"""
import io, struct, sys, os
import lz4.block
import texture2ddecoder as t2d
from PIL import Image

def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]

FMT = {
    4: ("RGB565_LE", 3), 6: ("RGB", 3), 16: ("RGB565", 3),
    19: ("ETC2_RGBA8", 4), 40: ("ASTC_4x4", 4), 44: ("ASTC_6x6", 4), 47: ("ASTC_8x8", 4),
    102: ("L8", 1),
}

def parse_header(b):
    if b[:4] != b"SCT2":
        raise ValueError("not SCT2")
    return {
        "total": u32(b, 4), "unk8": u32(b, 8), "data_offset": u32(b, 12),
        "block_w": u32(b, 16), "pixel_format": u32(b, 20),
        "width": u16(b, 24), "height": u16(b, 26),
        "tw": u16(b, 28), "th": u16(b, 30), "flags": u32(b, 32),
    }

def expected_size(pf, w, h):
    """Raw texture byte length for a pixel format (None when unknown)."""
    b = {40: 4, 44: 6, 47: 8}.get(pf)
    if b:
        return ((w + b - 1) // b) * ((h + b - 1) // b) * 16
    if pf == 19:
        return ((w + 3) // 4) * ((h + 3) // 4) * 16
    n = {4: 2, 16: 2, 6: 3, 102: 1}.get(pf)
    if 17 <= pf <= 26:
        n = 4
    return w * h * n if n else None


def decode(b):
    h = parse_header(b)
    pf = h["pixel_format"]
    off = h["data_offset"]
    blob = b[off:]
    unc = u32(blob, 0) if len(blob) >= 8 else 0
    comp = u32(blob, 4) if len(blob) >= 8 else 0
    data = None
    # try LZ4 (block) with 8-byte size prefix
    if comp and comp + 8 <= len(blob):
        try:
            out = lz4.block.decompress(blob[8:8 + comp], uncompressed_size=unc)
            if unc == 0 or len(out) == unc:
                data = out
        except Exception:
            data = None
    exp = expected_size(pf, h["width"], h["height"])
    if data is None:
        # two raw layouts observed: [u32 unc][u32 comp][data] or bare data.
        # dispatch on unc == expected size, fall back to a length match; then
        # never hand the C decoder a short buffer (it reads past the end -> crash).
        pair_ok = exp is not None and len(blob) - 8 >= exp and u32(blob, 0) == exp
        if exp is not None and not pair_ok and len(blob) == exp:
            data = blob                                  # bare raw texture
        else:
            data = blob[8:]                              # pair layout
        if exp is not None:
            data = data[:exp]
            if len(data) < exp:
                data = data + bytes(exp - len(data))
    w, hh = h["width"], h["height"]
    name, _ch = FMT.get(pf, (None, None))
    if name is None and 17 <= pf <= 26:
        name = "RGBA"
    if name == "ASTC_4x4": img = t2d.decode_astc(data, w, hh, 4, 4); mode = "BGRA"
    elif name == "ASTC_6x6": img = t2d.decode_astc(data, w, hh, 6, 6); mode = "BGRA"
    elif name == "ASTC_8x8": img = t2d.decode_astc(data, w, hh, 8, 8); mode = "BGRA"
    elif name == "ETC2_RGBA8": img = t2d.decode_etc2a8(data, w, hh); mode = "BGRA"
    elif name == "RGB565_LE":
        img = bytearray(w * hh * 4)
        for i in range(w * hh):
            px = data[2 * i] | (data[2 * i + 1] << 8)
            r = (px >> 11) & 0x1F; g = (px >> 5) & 0x3F; bl = px & 0x1F
            img[4 * i:4 * i + 4] = bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (bl << 3) | (bl >> 2), 255))
        mode = "RGBA"
    elif name == "L8":
        img = bytearray(w * hh * 4)
        for i in range(w * hh):
            v = data[i]
            img[4 * i:4 * i + 4] = bytes((v, v, v, 255))
        mode = "RGBA"
    elif name == "RGBA":
        img = data[: w * hh * 4]; mode = "RGBA"
    else:
        raise ValueError(f"unsupported pixel format {pf}")
    im = Image.frombytes("RGBA", (w, hh), bytes(img[: w * hh * 4]), "raw", mode)
    return im, h

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        assert expected_size(40, 1584, 724) == 1146816
        assert expected_size(40, 2040, 1948) == 3973920
        assert expected_size(40, 1, 1) == 16
        assert expected_size(19, 5, 5) == 64
        assert expected_size(4, 10, 10) == 200
        assert expected_size(6, 10, 10) == 300
        assert expected_size(102, 3, 4) == 12
        print("sct2 selftest ok")
        raise SystemExit(0)
    sys.path.insert(0, os.path.dirname(__file__))
    from czn_pack import Pack
    P = Pack()
    OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extract", "png")
    os.makedirs(OUT, exist_ok=True)
    tests = [
        "face/portrait/1030.sct", "face/portrait/1052_front.sct",
        "face/character/portrait_character_wide_20030.sct",
        "face/character/face_character_1024_panic.sct",
        "card_illustration/start_1061_02.sct",
        "card_illustration/unique_1060_03.sct",
        "img/btn_dark_exit.sct", "img/deco_gra_circle.sct",
        "background/bg_operation_main.sct",
        "encounter_illustration/Ishullen_bg_1.sct" if any(0 for _ in []) else "background/story/lounge.sct",
    ]
    for t in tests:
        try:
            b = P.extract(t)
            im, h = decode(b)
            name = t.replace("/", "_") + ".png"
            im.save(os.path.join(OUT, name))
            print(f"OK  {t}: {h['width']}x{h['height']} fmt={h['pixel_format']} flags={h['flags']:#x} -> {name}")
        except Exception as e:
            print(f"ERR {t}: {type(e).__name__}: {e}")