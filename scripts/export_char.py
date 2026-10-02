"""Export every image asset of one character to plain PNGs, pack path mirrored.

Usage:
    python scripts/export_char.py 1041 D:/CZN_Asset
    python scripts/export_char.py lenore D:/CZN_Asset

- matches the keyword against decoded/names_all.json on digit boundaries
  ("1041" never matches inside a longer number).
- .sct files decode to PNG; other image files (.webp) are copied as-is.
- output mirrors the pack path, so an edit drops straight back in by putting
  the PNG into the tool's Mods/ folder with the same relative path.
- decode failures are listed in _README.txt instead of aborting the run.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from czn_pack import Pack
from sct2 import decode


def main():
    kw, outdir = sys.argv[1], sys.argv[2]
    names = json.load(open(os.path.join(HERE, "..", "decoded", "names_all.json"), encoding="utf-8"))
    pat = re.compile(r"(?<![0-9])%s(?![0-9])" % re.escape(kw), re.I)
    hits = [n for n in names if pat.search(n)]
    imgs = [n for n in hits if n.lower().endswith((".sct", ".webp", ".png"))]
    P = Pack()
    ok = copied = 0
    fails = []
    for name in imgs:
        dst = os.path.join(outdir, name)
        out_path = dst[:-4] + ".png" if name.lower().endswith(".sct") else dst
        if os.path.exists(out_path):
            ok += 1                    # exported by a previous (interrupted) run
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            data = P.extract(name)
            if name.lower().endswith(".sct"):
                from PIL import PngImagePlugin
                im, _h = decode(data)
                tag = PngImagePlugin.PngInfo()
                tag.add_text("czn-target", name)   # self-target: drop the edited png anywhere under Mods/
                im.save(dst[:-4] + ".png", pnginfo=tag)
                ok += 1
            else:
                open(dst, "wb").write(data)
                copied += 1
        except Exception as e:
            fails.append(f"{name}  --  {type(e).__name__}: {e}")

    nonimg = len(hits) - len(imgs)
    rep = [
        f"Character export: '{kw}'",
        f"names matched: {len(hits)}  (images: {len(imgs)}, other data files: {nonimg})",
        f"decoded to PNG: {ok}   copied raw: {copied}   failed: {len(fails)}",
        "",
        "Editing: every PNG here carries a 'czn-target' tag naming its game file,",
        "so after editing you can drop it ANYWHERE under the tool's Mods/ folder",
        "(any name). The tool re-tags if your editor strips it: stamp <png> <pack/path.sct>.",
        "The folder-mirrored path works too as a fallback.",
        "",
    ]
    if nonimg:
        rep.append(f"({nonimg} non-image files - .atlas/.scsp/.bank/.cfx etc - were skipped)")
        rep.append("")
    rep.append("FAILED:")
    rep += [f"  {f}" for f in fails] or ["  none"]
    open(os.path.join(outdir, "_README.txt"), "w", encoding="utf-8",
         newline="\r\n").write("\n".join(rep) + "\n")
    print(f"matched {len(hits)} | images {len(imgs)} | png {ok} | raw {copied} | failed {len(fails)}")
    for f in fails:
        print("  FAIL", f)


if __name__ == "__main__":
    main()
