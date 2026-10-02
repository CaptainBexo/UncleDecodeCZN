"""Build the demo mod pack: Mods/Demo_Renoa_Recolor/{manifest.json, portrait.png}.

The PNG starts from the current in-pack portrait (dump), then gets a clear hue-rotate
recolor so the effect is obvious in-game. Everything else (encode + stealth inject)
is cznmod.py's job -- this script only authors the mod folder.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))

from czn_pack import Pack
from sct2 import decode
from PIL import Image

PACK_PATH = "face/portrait/1041.sct"
MOD_DIR = os.path.join(HERE, "Mods", "Demo_Renoa_Recolor")

os.makedirs(MOD_DIR, exist_ok=True)
im, _ = decode(Pack().extract(PACK_PATH))
print(f"base: {PACK_PATH} -> {im.size} {im.mode}")

rgb = im.convert("RGB").convert("HSV")
h, s, v = rgb.split()
h = h.point(lambda x: (x + 110) % 256)          # hue rotate
s = s.point(lambda x: min(255, int(x * 1.25)))  # punch the saturation
out = Image.merge("HSV", (h, s, v)).convert("RGB")
out = out.convert("RGBA")
if im.mode == "RGBA":
    out.putalpha(im.getchannel("A"))
out.save(os.path.join(MOD_DIR, "portrait.png"))
print("recolored portrait.png written")

import json
json.dump({"name": "Demo Renoa Recolor",
           "map": {"portrait.png": PACK_PATH}},
          open(os.path.join(MOD_DIR, "manifest.json"), "w", encoding="utf-8"), indent=1)
print("manifest.json written")
