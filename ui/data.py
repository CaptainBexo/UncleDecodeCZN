"""Real data layer for the CZN MM/MI tool: scans the Mods/ folder exactly like
cznmod.py does (same keys, same status rules), and shells every write action out to
cznmod.py as a subprocess so the window and the CLI can never disagree.

Read-only here - this module never touches game files.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import zlib
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # repo root, or the portable tool folder in dist
sys.path.insert(0, ROOT)
# Writable app data (game_path.txt) goes next to the exe when packaged frozen.
APP = os.environ.get("CZN_APP_DIR") or (
    os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ROOT)

import cznmod  # noqa: E402

IMG_EXT = cznmod.IMG_EXT
DISABLED_DIR = "_disabled"
DEFAULT_MODS = cznmod.MODS

STATUS_TXT = {"ok": "Enabled", "pending": "Pending", "error": "Failed", "off": "Disabled"}
_WORST = {"error": 0, "pending": 1, "ok": 2}
CAT_PREFIX = (
    ("face/", "Character"),
    ("sound/", "Audio"), ("audio/", "Audio"),
    ("effect/", "UI"), ("background/", "UI"), ("ui/", "UI"), ("wnd/", "UI"),
    ("img/", "UI"), ("font/", "UI"), ("video/", "UI"), ("card_illustration/", "UI"),
    ("encounter_illustration/", "UI"), ("model/", "UI"),
)

TABS = ["All", "Enabled", "Disabled"]
SORTS = ["Newest", "Oldest", "Name A-Z"]
MENU = [("box", "Mods"), ("sliders", "Settings"), ("users", "Char ID")]


@dataclass(frozen=True)
class Mod:
    key: str                # cznmod key: "PackName/local.png" for packs, relpath for loose
    action_name: str        # name accepted by `cznmod.py disable/enable`
    name: str               # card title
    desc: str               # mapped pack paths
    kind: str               # footer text: "mod pack" / "loose image"
    cat: str
    meta: str               # pill text, e.g. "3 images"
    date: str               # dd.mm of the newest source file
    mtime: float
    hue: int                # gradient fallback / avatar colour
    status: str             # ok / pending / error / off
    banner: str | None      # source png used as the card cover
    files: tuple[str, ...] = ()
    disabled: bool = False


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _hue(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) % 360


def _date(mtime: float) -> str:
    return time.strftime("%d.%m", time.localtime(mtime))


def _cat_for(targets: list[str]) -> str:
    for t in targets:
        low = t.lower()
        for prefix, cat in CAT_PREFIX:
            if low.startswith(prefix):
                return cat
    return "Other"


def _merge(a: str, b: str) -> str:
    return a if _WORST[a] <= _WORST[b] else b


def _status(key: str, path: str, state: dict) -> str:
    ent = state.get(key)
    if not ent:
        return "pending"
    # applied to another game folder -> the copy in THIS install is gone (or never was there)
    if ent.get("game_root") and ent["game_root"] != game_root():
        return "pending"
    try:
        h = _sha1(open(path, "rb").read())
    except OSError:
        return "error"
    if ent.get("png_sha1") != h:
        return "pending"
    if not ent.get("sct_sha1"):
        return "error"
    return "ok"


def _one_image(size: int) -> str:
    return "1 image" if size == 1 else f"{size} images"


def _pack(folder: str, rel: str, state: dict, disabled: bool) -> Mod | None:
    """One mod pack folder (has manifest.json). Bad packs are skipped, like the CLI."""
    try:
        man = json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
        mapping = man["map"]
        if not isinstance(mapping, dict) or not mapping:
            return None
    except Exception:
        return None
    keys, srcs, targets, newest, banner = [], [], [], 0.0, None
    status = "off" if disabled else "ok"
    for local, target in sorted(mapping.items()):
        if not str(local).lower().endswith(IMG_EXT):
            continue
        src = os.path.join(folder, local)
        if not os.path.exists(src):
            continue
        keys.append(f"{rel}/{local}")
        srcs.append(src)
        targets.append(str(target))
        if not disabled:
            status = _merge(status, _status(f"{rel}/{local}", src, state))
        newest = max(newest, os.path.getmtime(src))
        if banner is None:
            banner = src
    if not keys:
        return None
    name = str(man.get("name") or rel)
    return Mod(key=rel, action_name=rel, name=name, desc="; ".join(targets),
               kind="mod pack", cat=_cat_for(targets), meta=_one_image(len(keys)),
               date=_date(newest), mtime=newest, hue=_hue(name), status=status,
               banner=banner, files=tuple(keys), disabled=disabled)


def _loose(path: str, rel: str, state: dict, disabled: bool) -> Mod:
    # same rule as cznmod.mod_targets: tag wins, then path mirror, then a
    # file-name match (editors strip the tag - the name still carries meaning)
    target = cznmod.resolve_target(rel, path)
    newest = os.path.getmtime(path)
    return Mod(key=rel, action_name=rel, name=rel, desc=target, kind="loose image",
               cat=_cat_for([target]), meta="1 image", date=_date(newest), mtime=newest,
               hue=_hue(rel), status="off" if disabled else _status(rel, path, state),
               banner=path, files=(rel,), disabled=disabled)


def _walk(base: str, rel: str, state: dict, disabled: bool) -> list[Mod]:
    out: list[Mod] = []
    try:
        entries = sorted(os.listdir(os.path.join(base, rel) if rel else base))
    except OSError:
        return out
    for fn in entries:
        r = f"{rel}/{fn}" if rel else fn
        full = os.path.join(base, r)
        if os.path.isdir(full):
            if fn == DISABLED_DIR:
                continue
            if os.path.isfile(os.path.join(full, "manifest.json")):
                m = _pack(full, r, state, disabled)
                if m:
                    out.append(m)
                continue
            out.extend(_walk(base, r, state, disabled))
        elif fn.lower().endswith(IMG_EXT):
            out.append(_loose(full, r, state, disabled))
    return out


def scan(mods_dir: str | None = None) -> tuple[list[Mod], list[Mod]]:
    """(enabled, disabled) mod cards for the given Mods folder."""
    mods_dir = mods_dir or DEFAULT_MODS
    state: dict = {}
    try:
        state = json.load(open(os.path.join(mods_dir, ".state.json")))
    except Exception:
        pass
    enabled = _walk(mods_dir, "", state, disabled=False)
    disabled = _walk(os.path.join(mods_dir, DISABLED_DIR), "", state, disabled=True)
    return enabled, disabled


def cli(args: list[str]) -> list[str]:
    """Command line that runs cznmod.py with the interpreter we live in."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cli", *args]     # packaged exe re-enters itself
    return [sys.executable, os.path.join(ROOT, "cznmod.py"), *args]


def add_mods(mods_dir: str, paths: list[str]) -> tuple[int, list[str]]:
    """Copy picked/dropped files and folders into the Mods folder.

    Returns (copied, errors). Name clashes get a " (2)" suffix; sources that
    already live inside the Mods folder are skipped (no recursive copies).
    """
    os.makedirs(mods_dir, exist_ok=True)
    base_dir = os.path.abspath(mods_dir)
    copied, errors = 0, []
    for p in paths:
        src = os.path.abspath(p)
        if not os.path.exists(src):
            errors.append(f"{p}: not found")
            continue
        if src == base_dir or src.startswith(base_dir + os.sep):
            continue
        name = os.path.basename(src.rstrip("\\/"))
        dest = os.path.join(base_dir, name)
        n = 2
        while os.path.exists(dest):
            root, ext = os.path.splitext(name)
            dest = os.path.join(base_dir, f"{root} ({n}){ext}")
            n += 1
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            copied += 1
        except OSError as e:
            errors.append(f"{name}: {e}")
    return copied, errors


def game_running() -> bool:
    return cznmod.game_running()


_ROOT: list = []          # [game_root | _NONE] memoized; set_game_dir() / tests clear it
_NONE = object()


def game_root() -> str | None:
    """Resolved game folder (memoized - czn_paths scans drives on a cold resolve)."""
    if not _ROOT:
        try:
            sp = os.path.join(ROOT, "scripts")
            if sp not in sys.path:
                sys.path.insert(0, sp)
            import czn_paths
            _ROOT.append(str(czn_paths.GAME_ROOT))
        except (SystemExit, Exception):
            _ROOT.append(_NONE)
    return None if _ROOT[0] is _NONE else _ROOT[0]


def asset_root() -> str:
    """Where per-character asset exports live: env CZN_ASSET_DIR wins, then the
    dev machine's D:\\CZN_Asset when present, otherwise a folder next to the exe."""
    return (os.environ.get("CZN_ASSET_DIR")
            or ("D:\\CZN_Asset" if os.path.isdir("D:\\CZN_Asset")
                else os.path.join(APP, "CZN_Asset")))


GAME_MANIFEST = ("bin", "appdata", "cznlive", "gameres", "manifest.ssra")


def looks_like_game(path: str) -> bool:
    return os.path.isfile(os.path.join(path, *GAME_MANIFEST))


def set_game_dir(path: str) -> bool:
    """Remember a game folder in game_path.txt (env CZN_GAME_DIR still wins).

    Accepts the game root, or what the user picked INSIDE it (bin\\, gameres\\...):
    the first of the picked folder and its two parents that looks like an install
    is written. Returns False when none of them does.
    """
    p = os.path.abspath(path)
    for cand in (p, os.path.dirname(p), os.path.dirname(os.path.dirname(p))):
        if looks_like_game(cand):
            with open(os.path.join(APP, "game_path.txt"), "w", encoding="utf-8") as fh:
                fh.write(cand + "\n")
            sys.modules.pop("czn_paths", None)     # re-resolve on the next use
            _ROOT.clear()
            return True
    return False


def game_root_changed(mods_dir: str | None = None) -> bool:
    """True when some applied mod in .state.json belongs to a different game folder."""
    try:
        state = json.load(open(os.path.join(mods_dir or DEFAULT_MODS, ".state.json")))
    except Exception:
        return False
    root = game_root()
    return bool(root) and any(
        isinstance(v, dict) and v.get("game_root") and v["game_root"] != root
        for v in state.values())
