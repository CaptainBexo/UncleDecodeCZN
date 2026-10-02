"""Prepare Spine assets for the embedded viewer (spine-webgl 3.8).

Source: the game pack - the .scsp/.atlas/.sct trio -> skeleton.json
(scripts/scsp2json.py) + .png pages; `override_pages` swaps a mod's image into
one atlas page, so a mod preview plays the real animation with the mod applied.
The output folder is replaced on every run.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _premultiply(im):
    """Spine's WebGL renderer blends premultiplied alpha; straight-alpha pages
    would show white fringes otherwise."""
    from PIL import Image, ImageChops
    im = im.convert("RGBA")
    a = im.getchannel("A")
    rgb = Image.merge("RGB", [ImageChops.multiply(im.getchannel(c), a) for c in "RGB"])
    return Image.merge("RGBA", [*rgb.split(), a])


def _is_premultiplied(im) -> bool:
    """CZN pages ship premultiplied (no channel exceeds alpha beyond noise);
    a straight page has clearly brighter semi-transparent pixels. Multiplying
    an already-premultiplied page again darkens every soft edge (black fringes).
    Transparent texels (alpha < 32) are ignored - their rgb never reaches the blend."""
    from PIL import Image, ImageChops
    im = im.convert("RGBA")
    a = im.getchannel("A")
    mask = a.point([0] * 32 + [255] * 224)      # C lookup table, not a per-pixel lambda
    diff = ImageChops.subtract(im.convert("RGB"), Image.merge("RGB", [a, a, a]))
    diff = ImageChops.multiply(diff, Image.merge("RGB", [mask, mask, mask]))
    bad = sum(sum(ch.histogram()[24:]) for ch in diff.split())
    semi = sum(a.histogram()[32:])
    return bad < max(1000, semi * 0.005)


def _page_ready(im):
    """Premultiply only when the source is straight alpha."""
    return im if _is_premultiplied(im) else _premultiply(im)


def _rewrite_pages(text: str, rename: bool = True):
    """Page lines sit alone, unindented, right before their 'size:' line."""
    lines = text.splitlines()
    pages = []
    for i, ln in enumerate(lines):
        if not ln or ln[0] in " \t":
            continue
        if i + 1 < len(lines) and lines[i + 1].startswith("size:"):
            new = re.sub(r"\.[A-Za-z0-9]+$", ".png", ln) if rename else ln
            pages.append((ln, new))
            lines[i] = new
    return "\n".join(lines) + "\n", pages


def _fresh(out_dir: str) -> None:
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)


def prepare(spine_name: str, out_dir: str, override_pages: dict | None = None) -> dict:
    """spine_name: pack path of the skeleton, e.g. 'model/1041.scsp'.
    override_pages: {atlas page name: local image path} - the image replaces that page."""
    from PIL import Image

    from czn_pack import Pack
    from sct2 import decode
    from scsp2json import to_json, unwrap

    pack = Pack()
    base = spine_name[: -len(".scsp")]
    folder = base.rsplit("/", 1)[0] + "/" if "/" in base else ""
    data = to_json(unwrap(pack.extract(spine_name)))
    text, pages = _rewrite_pages(pack.extract(base + ".atlas").decode("utf-8", "replace"))

    page_sizes = {}
    _lines = text.splitlines()
    for _i, _ln in enumerate(_lines):
        if _i + 1 < len(_lines) and _lines[_i + 1].startswith("size:") and _ln and _ln[0] not in " \t":
            try:
                _w, _h = _lines[_i + 1].split(":", 1)[1].split(",")
                page_sizes[_ln] = (int(_w), int(_h))
            except ValueError:
                pass

    _fresh(out_dir)
    with open(os.path.join(out_dir, "skeleton.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(out_dir, "skeleton.atlas"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    written = []
    for old, new in pages:
        dst = os.path.join(out_dir, new)
        if override_pages and old in override_pages:
            im = Image.open(override_pages[old]).convert("RGBA")
            pw, ph = page_sizes.get(new, (0, 0))
            if pw and ph and im.size != (pw, ph):
                im = im.resize((pw, ph), Image.LANCZOS)   # wrong-size art still previews
            _page_ready(im).save(dst)
        else:
            im, _meta = decode(pack.extract(folder + old))
            _page_ready(im).save(dst)
        written.append(new)
    anims = data.get("animations") or {}
    names = list(anims) if isinstance(anims, dict) else [a.get("name", str(a)) for a in anims]
    return {"dir": out_dir, "pages": written, "bones": len(data.get("bones", [])),
            "animations": names, "binary": False}


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) < 2:
        print("usage: python spine_prep.py <pack/path.scsp> [out_dir]")
        raise SystemExit(2)
    src = _sys.argv[1]
    out = _sys.argv[2] if len(_sys.argv) > 2 else os.path.join(
        os.environ.get("TEMP", "."), "spine_prep_out")
    info = prepare(src, out)
    print("[OK] %s -> %s (pages=%s)" % (src, info["dir"], info["pages"]))
