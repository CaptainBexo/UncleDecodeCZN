"""Prepare one game Spine model for the embedded viewer (spine-webgl 3.8).

Converts the pack's .scsp/.atlas/.sct trio into what a stock Spine viewer
needs: skeleton.json (via scripts/scsp2json.py), the atlas with .png page
names, and decoded page PNGs premultiplied for the WebGL renderer.
The output folder is replaced on every run.
"""
from __future__ import annotations

import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in __import__("sys").path:
    __import__("sys").path.insert(0, HERE)


def _premultiply(im):
    """Spine's WebGL renderer blends premultiplied alpha; SCT2 pages are
    straight alpha (same fix the BD2 viewer needed - white fringes otherwise)."""
    from PIL import Image, ImageChops
    im = im.convert("RGBA")
    a = im.getchannel("A")
    rgb = Image.merge("RGB", [ImageChops.multiply(im.getchannel(c), a) for c in "RGB"])
    return Image.merge("RGBA", [*rgb.split(), a])


def _rewrite_pages(text: str):
    """Page lines sit alone, unindented, right before their 'size:' line."""
    lines = text.splitlines()
    pages = []
    for i, ln in enumerate(lines):
        if not ln or ln[0] in " \t":
            continue
        if i + 1 < len(lines) and lines[i + 1].startswith("size:"):
            new = re.sub(r"\.[A-Za-z0-9]+$", ".png", ln)
            pages.append((ln, new))
            lines[i] = new
    return "\n".join(lines) + "\n", pages


def prepare(spine_name: str, out_dir: str) -> dict:
    """spine_name: pack path of the skeleton, e.g. 'model/1041.scsp'."""
    from czn_pack import Pack
    from sct2 import decode
    from scsp2json import to_json, unwrap

    pack = Pack()
    base = spine_name[: -len(".scsp")]
    folder = base.rsplit("/", 1)[0] + "/" if "/" in base else ""
    data = to_json(unwrap(pack.extract(spine_name)))
    text, pages = _rewrite_pages(pack.extract(base + ".atlas").decode("utf-8", "replace"))

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    with open(os.path.join(out_dir, "skeleton.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(out_dir, "skeleton.atlas"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    written = []
    for old, new in pages:
        im, _meta = decode(pack.extract(folder + old))
        _premultiply(im).save(os.path.join(out_dir, new))
        written.append(new)
    anims = data.get("animations") or {}
    names = list(anims) if isinstance(anims, dict) else [a.get("name", str(a)) for a in anims]
    return {
        "dir": out_dir,
        "pages": written,
        "bones": len(data.get("bones", [])),
        "animations": names,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python spine_prep.py <pack/path.scsp> [out_dir]")
        raise SystemExit(2)
    name = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.environ.get("TEMP", "."), "spine_prep_out")
    info = prepare(name, out)
    print("[OK] %s -> %s (bones=%d pages=%s anims=%d)"
          % (name, info["dir"], info["bones"], info["pages"], len(info["animations"])))
