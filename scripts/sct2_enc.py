"""SCT2 encoder: PNG -> SCT2 matching original header (in-place friendly, keep same byte length)."""
import os, struct, subprocess, sys, tempfile
import lz4.block
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from sct2 import parse_header, decode, expected_size

ASTCENC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "astcenc-avx2.exe")
U16 = lambda b, o: struct.unpack_from("<H", b, o)[0]
U32 = lambda b, o: struct.unpack_from("<I", b, o)[0]

def _astc_encode(png_path, w, h, bw, bh, effort="-medium"):
    tmp = png_path + f".{bw}x{bh}.astc"
    cmd = [ASTCENC, "-cl", png_path, tmp, f"{bw}x{bh}", effort]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    if r.returncode != 0:
        raise RuntimeError(f"astcenc failed: {r.stdout[-200:]} {r.stderr[-300:]}")
    data = open(tmp, "rb").read()
    os.remove(tmp)
    # astcenc writes a 16-byte .astc file header (magic 0x5CA1AB13 + block dims +
    # w/h/z); the engine wants bare blocks - keeping the header shifts every
    # block by one slot (4px) and overflows bare layouts by exactly 16 bytes.
    if data[:4] != b"\x13\xab\xa1\x5c":
        raise RuntimeError(f"astcenc output not a .astc file: {data[:4].hex()}")
    return data[16:]

def _snapped(im, step: int):
    """Round rgb to the nearest multiple of `step` (alpha untouched) - flattens
    resample noise so the ASTC/lz4 stream fits the texture's fixed byte budget."""
    r, g, b, a = im.split()
    half = step // 2
    snap = lambda ch: ch.point(lambda v: min(255, ((v + half) // step) * step))  # noqa: E731
    return Image.merge("RGBA", (snap(r), snap(g), snap(b), a))


def encode_like(orig: bytes, png_path: str, effort="-thorough", keep_len=True, pad="zeros",
                ref_png=None) -> bytes:
    """Re-encode PNG as SCT2 with the same header/flags as `orig`, keep_len = pad to original size.

    When the encoded stream overflows the original byte budget (heavily
    resampled artwork compresses worse), rgb is snapped to a small step and
    the encode retried before giving up."""
    h = parse_header(orig)
    pf = h["pixel_format"]
    w, hh = h["width"], h["height"]
    doff = h["data_offset"]
    header = bytearray(orig[:doff])
    # mirror the original texture layout: bit31 clear = bare raw (no size pair,
    # the engine reads pixels right at data_offset); bit31 set = [u32 unc][u32 comp][lz4]
    exp = expected_size(pf, w, hh)
    bare = exp is not None and (len(orig) - doff) == exp and not (h["flags"] & 0x80000000)
    if pf not in (40, 44, 47):
        raise NotImplementedError(f"encode for format {pf} not implemented")
    bw = {40: 4, 44: 6, 47: 8}[pf]
    # astcenc needs image with exact w×h; resize input if mismatched
    im = Image.open(png_path).convert("RGBA")
    if im.size != (w, hh):
        im = im.resize((w, hh), Image.LANCZOS)
    # Match the game's own texel conventions the same way the viewer prep
    # does: clear texels flushed to black, straight pages premultiplied
    # once, straight leftovers on a premultiplied page premultiplied. Raw
    # PNG input carries no decode noise, so the excess threshold is tight.
    # NOTE (v0.8.2): the pristine-reference ripple pass (_match_source) is NOT
    # applied here. It regressed the user's soft-brush strokes: at feathered
    # stroke edges (partial coverage of the original linework) the small
    # high-frequency steps ARE the intended blend, and clipping them pulled
    # those pixels back toward the reference - faint ghost lines along every
    # stroke edge, worse than the ripple it removed. Kept in spine_prep for
    # reference only.
    import spine_prep
    im = spine_prep._page_ready(im, tol=2)

    fd, work = tempfile.mkstemp(prefix="czn_enc_", suffix=".png")
    os.close(fd)

    def _attempt(candidate) -> bytes | None:
        """Encode one candidate image; None when it cannot fit the budget."""
        try:
            candidate.save(work)
            block = _astc_encode(work, w, hh, bw, bw, effort)
        finally:
            try:
                os.remove(work + f".{bw}x{bw}.astc")
            except OSError:
                pass
        if bare:
            out = bytes(header) + block
        else:
            lz = lz4.block.compress(block, store_size=False, mode="high_compression")
            out = bytes(header) + struct.pack("<II", len(block), len(lz)) + lz
        if keep_len and len(out) > len(orig):
            return None
        return out

    try:
        out = _attempt(im)
        for step in (4, 8):                # salvage: flatten resample noise
            if out is not None:
                break
            out = _attempt(_snapped(im, step))
            if out is not None:
                print(f"[i] {os.path.basename(png_path)}: flattened to step {step} "
                      "to fit the texture byte budget", flush=True)
    finally:
        try:
            os.remove(work)
        except OSError:
            pass
    if out is None:
        raise RuntimeError(
            f"encoded image does not fit {len(orig):,} bytes even after flattening - "
            "the picture carries too much fine detail/noise for this texture "
            "(tip: export at the exact original size; avoid repeated resampling)")
    if keep_len:
        out = out + b"\x00" * (len(orig) - len(out))
        # keep total field = original (== our padded len)
    out = bytearray(out)
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)

def self_check():
    """Round-trip: decode orig -> png -> encode_like -> decode -> compare."""
    from czn_pack import Pack
    import io, math
    P = Pack()
    for name, effort in [("img/btn_dark_exit.sct", "-medium"),
                         ("face/character/face_character_wide_1041.sct", "-medium"),
                         ("background/story/illust_trauma_1041_08.sct", "-medium"),
                         ("face/character/face_character_1041_01.sct", "-medium")]:
        orig = P.extract(name)
        im0, h = decode(orig)
        tmp = os.path.join(tempfile.gettempdir(), "rt_test.png")
        im0.save(tmp)
        new = encode_like(orig, tmp, effort)
        assert len(new) == len(orig), f"{name}: len {len(new)} != {len(orig)}"
        assert (parse_header(new)["flags"] & 0x80000000) == (h["flags"] & 0x80000000), \
            f"{name}: layout bit31 changed"
        im1, _ = decode(new)
        assert im1.size == im0.size
        # mean abs diff
        a = im0.convert("RGBA").tobytes(); b = im1.convert("RGBA").tobytes()
        diff = sum(abs(x - y) for x, y in zip(a[::997], b[::997])) / (len(a[::997]) * 1)
        print(f"OK {name}: {im0.size} fmt={h['pixel_format']} roundtrip len={len(new):,} "
              f"meandiff~{diff:.2f} (0=lossless)")
        out_dir = tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        im1.save(os.path.join(out_dir, os.path.basename(name) + ".roundtrip.png"))

if __name__ == "__main__":
    self_check()