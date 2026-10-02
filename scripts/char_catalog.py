"""Character id catalog shared by char_ids.py (CharID.txt + montages) and the
UI's Char ID tab.

- ids come from `face/portrait/<id>.sct`
- codenames are mined from asset name tokens (`<codename>_<id>`, e.g. lenore_1041)
- display names are NOT readable in-game (text db is encrypted); a few are
  confirmed from official sources and listed in DISPLAY_NAMES
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_PATH = os.path.join(HERE, "..", "decoded", "names_all.json")

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

# portrait art per id, best first (260x460 half crops are the cheapest; the small
# face icon is the last resort for ids that only have a head shot)
THUMB_CANDIDATES = ("face/character/portrait_character_crop_half_%d.sct",
                    "face/character/portrait_character_crop_%d.sct",
                    "face/character/portrait_character_%d.sct",
                    "face/character/face_character_%d.sct")

GROUPS = {"playable": "Playable", "supporter": "Support", "other": "Other"}


def group_of(pid: int) -> str:
    if 1000 <= pid < 2000:
        return "playable"
    if 20000 <= pid < 30000:
        return "supporter"
    return "other"


def load(path: str = NAMES_PATH) -> list[dict]:
    """The catalog as [{'id','code','name','group','label','assets','thumb'}]."""
    with open(path, encoding="utf-8") as fh:
        return build(json.load(fh))


def build(names: list[str]) -> list[dict]:
    ids = sorted(int(m.group(1)) for n in names
                 if (m := re.match(r"face/portrait/(\d+)\.sct$", n)))
    id_set = set(ids)
    name_set = set(names)
    assets: Counter = Counter()
    tokens: defaultdict = defaultdict(Counter)
    tpat = re.compile(r"([a-z][a-z0-9_]{1,30}?)[_\-](\d+)(?!\d)")
    for n in names:
        # count each id once per name (maximal digit runs == (?!\d)\d+(?<!\d))
        seen: set[int] = set()
        for d in re.findall(r"\d+", n):
            v = int(d)
            if v in id_set and v not in seen:
                seen.add(v)
                assets[v] += 1
        for m in tpat.finditer(n):
            v = int(m.group(2))
            if v in id_set:
                t = m.group(1).split("_")[-1]
                if t not in JUNK and len(t) >= 3:
                    tokens[v][t] += 1
    rows = []
    for pid in ids:
        code = tokens[pid].most_common(1)[0][0] if tokens[pid] else ""
        thumb = next((c % pid for c in THUMB_CANDIDATES if c % pid in name_set), None)
        grp = group_of(pid)
        rows.append({"id": pid, "code": code, "name": DISPLAY_NAMES.get(pid) or code,
                     "group": grp, "label": GROUPS[grp], "assets": assets.get(pid, 0),
                     "thumb": thumb})
    return rows


def match(row: dict, query: str) -> bool:
    """Search: case-insensitive substring over id, name and codename."""
    q = query.strip().lower()
    if not q:
        return True
    return q in str(row["id"]) or q in row["name"].lower() or q in row["code"].lower()
