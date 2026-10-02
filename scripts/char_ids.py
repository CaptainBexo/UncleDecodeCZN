"""Build CharID.txt + labeled portrait montages for Chaos Zero Nightmare.

Usage:  python scripts/char_ids.py [out_dir]        (default D:/CZN_Asset)

- ids come from `face/portrait/<id>.sct`
- codenames are mined from asset names embedding `<codename>_<id>` (e.g. lenore_1041)
- display names are NOT readable in-game (text db is encrypted); a few are
  confirmed from official sources and listed in DISPLAY_NAMES below
- writes CharID.txt + _CharID_*_map.png montages (one per id block)
"""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from czn_pack import Pack
from sct2 import decode
from PIL import Image, ImageDraw, ImageFont

JUNK = {"eff", "fx", "ui", "img", "bg", "sct", "icon", "sd", "atk", "def", "hit",
        "idle", "skill", "trs", "pos", "b", "a", "n", "w", "tex", "glow", "line",
        "unique", "liveevent", "event", "story", "card", "main", "sub", "item", "wep",
        "weapon", "boss", "npc", "world", "chapter", "field", "tutorial", "guide", "hud",
        "supporter", "support", "partner", "char", "face", "model", "pose", "start", "end",
        "character", "wide"}

# display names confirmed from official sources (STOVE fankit MMD kits / known roster)
DISPLAY_NAMES = {
    1041: "Renoa",      # user-verified
    1027: "Mei Lin",    # official MMD kit "Mei Lin"
    1033: "Veronica",   # official MMD kit "Veronica"
    30075: "Sereniel",  # official MMD kit "Sereniel" + sereniel_30075_* assets
    30115: "Arabella",  # official MMD kit "Arabella" + arabella_30115_* assets
}


def group_of(pid):
    if 1000 <= pid < 2000:
        return "playable"
    if 20000 <= pid < 30000:
        return "supporter"
    return "other"


def codename_for(pid, names):
    pat = re.compile(r"([a-z][a-z0-9_]{1,30}?)[_\-]%d(?![0-9])" % pid)
    c = Counter()
    for n in names:
        for m in pat.findall(n):
            tok = m.split("_")[-1]
            if tok not in JUNK and not tok.isdigit() and len(tok) >= 3:
                c[tok] += 1
    return c.most_common(1)[0][0] if c else ""


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "D:/CZN_Asset"
    os.makedirs(out, exist_ok=True)
    names = json.load(open(os.path.join(HERE, "..", "decoded", "names_all.json"), encoding="utf-8"))
    ids = sorted(int(m.group(1)) for n in names if (m := re.match(r"face/portrait/(\d+)\.sct$", n)))
    rows = []
    for pid in ids:
        code = codename_for(pid, names)
        cnt = len([n for n in names if re.search(r"(?<![0-9])%d(?![0-9])" % pid, n)])
        rows.append((pid, code, group_of(pid), cnt))

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
        for pid, code, pgrp, cnt in rows:
            if pgrp != grp:
                continue
            disp = DISPLAY_NAMES.get(pid)
            if disp and code:
                col = f"{pid}_{disp}_{code}"
            elif disp:
                col = f"{pid}_{disp}"
            else:
                col = f"{pid}_{code}" if code else str(pid)
            lines.append(f"{col:<30}  {grp:<10}  {cnt} assets")
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
                         "face/character/portrait_character_%d.sct"]:
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

    play = [(pid, code) for pid, code, g, _ in rows if g == "playable"]
    supp = [(pid, code) for pid, code, g, _ in rows if g == "supporter"]
    othr = [(pid, code) for pid, code, g, _ in rows if g == "other"]
    montage(play, "_CharID_playable_map.png", "PLAYABLE block (10xx) - labeled by ID")
    montage(supp, "_CharID_supporter_map.png", "SUPPORTER block (20xxx) - labeled by ID")
    montage(othr, "_CharID_other_map.png", "30xxx+ block - labeled by ID")


if __name__ == "__main__":
    main()
