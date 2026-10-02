"""Prepare Spine assets for the embedded viewer (spine-webgl 3.8).

Two sources:
  - the game pack: the .scsp/.atlas/.sct trio -> skeleton.json (scripts/scsp2json.py)
    + .png pages; `override_pages` swaps a mod's image into one atlas page, so a
    mod preview plays the real animation with the mod applied.
  - local standard files: a .skel/.json + .atlas (+ pages) trio from disk, copied
    beside each other; pma-aware (premultiply only when the atlas says straight
    alpha; pages already premultiplied are left alone).
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

    _fresh(out_dir)
    with open(os.path.join(out_dir, "skeleton.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(out_dir, "skeleton.atlas"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    written = []
    for old, new in pages:
        dst = os.path.join(out_dir, new)
        if override_pages and old in override_pages:
            _premultiply(Image.open(override_pages[old])).save(dst)
        else:
            im, _meta = decode(pack.extract(folder + old))
            _premultiply(im).save(dst)
        written.append(new)
    anims = data.get("animations") or {}
    names = list(anims) if isinstance(anims, dict) else [a.get("name", str(a)) for a in anims]
    return {"dir": out_dir, "pages": written, "bones": len(data.get("bones", [])),
            "animations": names, "binary": False}


def _pick_trio(path: str) -> tuple[str, str]:
    """Resolve (skeleton, atlas) from a .skel/.json/.atlas file or a folder."""
    if os.path.isdir(path):
        d = path
        skel = None
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".skel"):
                skel = os.path.join(d, f)
                break
        if skel is None:
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(".json") and os.path.isfile(os.path.join(d, f[:-5] + ".atlas")):
                    skel = os.path.join(d, f)
                    break
        if skel is None:
            raise FileNotFoundError("no .skel / .json skeleton in %s" % path)
        stem = skel[: -len(os.path.splitext(skel)[1])]
        atlas = stem + ".atlas"
        if not os.path.isfile(atlas):
            cands = [os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.lower().endswith(".atlas")]
            if not cands:
                raise FileNotFoundError("no .atlas in %s" % path)
            atlas = cands[0]
        return skel, atlas
    stem, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext == ".atlas":
        for sext in (".skel", ".json"):
            if os.path.isfile(stem + sext):
                return stem + sext, path
        raise FileNotFoundError("no .skel / .json beside %s" % path)
    if ext in (".skel", ".json"):
        atlas = stem + ".atlas"
        if not os.path.isfile(atlas):
            d = os.path.dirname(path) or "."
            cands = [os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.lower().endswith(".atlas")]
            if len(cands) != 1:
                raise FileNotFoundError("no unique .atlas beside %s" % path)
            atlas = cands[0]
        return path, atlas
    raise ValueError("not a .skel/.json/.atlas source: %s" % path)


def prepare_trio(path: str, out_dir: str) -> dict:
    """Local standard Spine files (.skel/.json + .atlas + pages) -> viewer folder.
    A .sct page (game-extracted atlas) is decoded to .png on the way."""
    from PIL import Image

    skel, atlas_path = _pick_trio(path)
    src_dir = os.path.dirname(atlas_path) or "."
    text = open(atlas_path, encoding="utf-8", errors="replace").read()
    pma = any(ln.strip().lower() == "pma: true" for ln in text.splitlines())

    _fresh(out_dir)
    skel_name = "skeleton" + os.path.splitext(skel)[1].lower()
    shutil.copyfile(skel, os.path.join(out_dir, skel_name))

    lines = text.splitlines()
    written = []
    for i, ln in enumerate(lines):
        if not ln or ln[0] in " \t":
            continue
        if i + 1 < len(lines) and lines[i + 1].startswith("size:"):
            src = os.path.join(src_dir, ln)
            if not os.path.isfile(src):
                raise FileNotFoundError("atlas page missing: %s" % src)
            dst = os.path.join(out_dir, ln)
            if os.path.dirname(ln):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
            if ln.lower().endswith(".sct"):
                from sct2 import decode
                with open(src, "rb") as f:
                    im, _meta = decode(f.read())
                new = re.sub(r"\.[A-Za-z0-9]+$", ".png", ln)
                _premultiply(im).save(os.path.join(out_dir, new))
                lines[i] = new
                written.append(new)
            elif ln.lower().endswith((".png", ".webp")):
                im = Image.open(src)
                (im if pma else _premultiply(im)).save(dst)
                written.append(ln)
            else:
                shutil.copyfile(src, dst)          # opaque formats need no alpha work
                written.append(ln)
    with open(os.path.join(out_dir, "skeleton.atlas"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return {"dir": out_dir, "pages": written, "bones": 0, "animations": [],
            "binary": skel_name.endswith(".skel")}


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) < 2:
        print("usage: python spine_prep.py <pack/path.scsp | file.skel | folder> [out_dir]")
        raise SystemExit(2)
    src = _sys.argv[1]
    out = _sys.argv[2] if len(_sys.argv) > 2 else os.path.join(
        os.environ.get("TEMP", "."), "spine_prep_out")
    if src.endswith(".scsp"):
        info = prepare(src, out)
    else:
        info = prepare_trio(src, out)
    print("[OK] %s -> %s (pages=%s binary=%s)" % (src, info["dir"], info["pages"], info["binary"]))
