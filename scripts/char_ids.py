"""Build CharID.txt + labeled portrait montages for Chaos Zero Nightmare.

Usage:  python scripts/char_ids.py [out_dir]        (default D:/CZN_Asset)

- ids/codenames/display names come from char_catalog (shared with the UI tab)
- writes CharID.txt + _CharID_*_map.png montages (one per id block)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from char_catalog import DISPLAY_NAMES, build
from czn_pack import Pack
from sct2 import decode
from PIL import Image, ImageDraw, ImageFont


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "D:/CZN_Asset"
    os.makedirs(out, exist_ok=True)
    names = json.load(open(os.path.join(HERE, "..", "decoded", "names_all.json"), encoding="utf-8"))
    rows = build(names)

    lines = ["# Chaos Zero Nightmare character ids (patch 1.0.81406)",
             "# [ID]_[name][_codename]   group   assets",
             "#   name = display name when confirmed from official sources (official MMD",
             "#          fankit / known roster), otherwise the internal codename mined",
             "#          from asset paths (the in-game text db is encrypted)",
             "#   group: playable = 10xx block, supporter = 20xxx block (support units),",
             "#          other = 30xxx+ block",
             "# preview: _CharID_*_map.png (montages labeled by ID)",
             ""]
    for grp, title in [("playable", "PLAYABLE (10xx)"),
                       ("supporter", "SUPPORTERS (20xxx)"),
                       ("other", "OTHER (30xxx+)")]:
        lines.append(f"# --- {title} ---")
        for r in rows:
            if r["group"] != grp:
                continue
            disp = DISPLAY_NAMES.get(r["id"])
            if disp and r["code"]:
                col = f"{r['id']}_{disp}_{r['code']}"
            elif disp:
                col = f"{r['id']}_{disp}"
            else:
                col = f"{r['id']}_{r['code']}" if r["code"] else str(r["id"])
            lines.append(f"{col:<30}  {grp:<10}  {r['assets']} assets")
        lines.append("")
    path = os.path.join(out, "CharID.txt")
    open(path, "w", encoding="utf-8", newline="\r\n").write("\n".join(lines))
    print(f"[OK] {path} ({len(rows)} ids)")

    # --- montages ---
    P = Pack()
    fdir = os.path.join(HERE, "..", "ui", "assets", "fonts")
    font = font_small = None
    try:
        for fn in os.listdir(fdir):
            if "SemiBold" in fn:
                font = ImageFont.truetype(os.path.join(fdir, fn), 20)
                font_small = ImageFont.truetype(os.path.join(fdir, fn), 15)
    except Exception:
        pass
    if font is None:
        font = font_small = ImageFont.load_default()

    def montage(ids_sub, fname, title):
        cols = 8
        cw, ch = 190, 300
        rows_n = (len(ids_sub) + cols - 1) // cols
        canvas = Image.new("RGBA", (cols * cw, rows_n * ch + 40), (24, 24, 28, 255))
        dr = ImageDraw.Draw(canvas)
        dr.text((12, 8), title, font=font, fill=(240, 240, 240))
        for i, (pid, code) in enumerate(ids_sub):
            im = None
            for cand in ["face/character/portrait_character_crop_half_%d.sct",
                         "face/character/portrait_character_crop_%d.sct",
                         "face/character/portrait_character_%d.sct",
                         "face/character/face_character_%d.sct"]:
                try:
                    im, _ = decode(P.extract(cand % pid))
                    im = im.convert("RGBA")
                    break
                except Exception:
                    continue
            x = (i % cols) * cw
            y = (i // cols) * ch + 40
            if im:
                im.thumbnail((cw - 20, ch - 60), Image.LANCZOS)
                canvas.paste(im, (x + (cw - im.width) // 2, y + 6), im)
            disp = DISPLAY_NAMES.get(pid)
            dr.text((x + 10, y + ch - 50), str(pid), font=font, fill=(255, 255, 255))
            dr.text((x + 10, y + ch - 26), disp or code or "?", font=font_small, fill=(160, 200, 255))
        p = os.path.join(out, fname)
        canvas.convert("RGB").save(p)
        print(f"[OK] {p} ({len(ids_sub)} tiles)")

    play = [(r["id"], r["code"]) for r in rows if r["group"] == "playable"]
    supp = [(r["id"], r["code"]) for r in rows if r["group"] == "supporter"]
    othr = [(r["id"], r["code"]) for r in rows if r["group"] == "other"]
    montage(play, "_CharID_playable_map.png", "PLAYABLE block (10xx) - labeled by ID")
    montage(supp, "_CharID_supporter_map.png", "SUPPORTER block (20xxx) - labeled by ID")
    montage(othr, "_CharID_other_map.png", "30xxx+ block - labeled by ID")


if __name__ == "__main__":
    main()
