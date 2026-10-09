"""CZN Mods injector: drop-in 'Mods/' folder -> in-place STEALTH inject into pack chunks.

Usage (or double-click the .bat files at workspace root):
  python cznmod.py apply              apply everything under Mods/ (loose images and mod packs)
  python cznmod.py watch              silent background: auto-apply when Mods/ changes and the game is closed
  python cznmod.py revert [substr]    restore originals from backup/; those mods move to Mods/_disabled/
  python cznmod.py disable <mod>      take one mod out of the game and park it in Mods/_disabled/
  python cznmod.py enable <mod>       move a parked mod back from Mods/_disabled/ and apply it
  python cznmod.py list <keyword>     search pack file names (to build a Mods/ path)
  python cznmod.py dump <pack-path> <out.png>   export the current in-game image as PNG (edit base)
  python cznmod.py export <id|keyword> <outdir> export every image of one character (id or keyword)
  python cznmod.py stamp <png> <pack/path.sct>  tag any png with its target (self-target mod)
  python cznmod.py selftest           check Mods/ detection for all three mod kinds

Three kinds of mods live under Mods/:
  * self-target :  Mods/<any name>.png carrying an embedded "czn-target" text chunk
                   (the tag names the game file; file name and folder do not matter)
  * loose image :  Mods/<pack/path>.png            (mirrors the pack path, .png -> .sct)
  * mod pack    :  Mods/<any name>/manifest.json   {"name": ..., "map": {"<local.png>": "<pack/path.sct>"}}
                   (as many images per pack as you want; .skel/.scsp skeleton mods not supported yet)

Stealth = payload-only writes: chunk trailer hashes + manifest.ssra stay at their original
(server) values, so the game's boot integrity check sees nothing. Aesthetic file swaps only.
State (Mods/.state.json) caches per-file hashes + the game folder each mod was applied to:
unchanged mods are skipped, a repaired game is re-applied (self-heal), and pointing the tool at
another game folder makes every mod re-apply instead of trusting a stale "in game" status.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "scripts"))

# Writable app data (Mods/, backup/, state) sits next to the exe when packaged: main.py
# sets CZN_APP_DIR, the exe fallback covers a direct run without it. Repo folder otherwise.
APP = os.environ.get("CZN_APP_DIR") or (
    os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else HERE)

MODS = os.path.join(APP, "Mods")
BACKUP = os.path.join(APP, "backup")
STATE = os.path.join(MODS, ".state.json")
LOG = os.path.join(MODS, ".log.txt")
PIDF = os.path.join(MODS, ".watch.pid")
GAME_EXE = "ssr-stove-shield.exe"
EFFORT = os.environ.get("CZNMOD_EFFORT", "-thorough")   # 0.5s/page, measurably cleaner edges than -medium
IMG_EXT = (".png", ".webp", ".jpg", ".jpeg", ".modfile")


def _task_running(exe):
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
            capture_output=True, text=True,
            creationflags=0x08000000 if os.name == "nt" else 0).stdout
        return exe.lower() in out.lower()
    except Exception:
        return False


def game_running():
    return _task_running(GAME_EXE)


def png_target(path):
    """Pack path stored in the png's "czn-target" text chunk (self-target mod), else None.

    Images the tool exports from the asset database already carry the tag; `stamp`
    (re)applies it after editing. A .modfile rename keeps working because the tag is
    read from the file content, not the name.
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            t = (im.text or {}).get("czn-target")
    except Exception:
        return None
    if not t:
        return None
    t = t.strip().replace("\\", "/")
    if not t:
        return None
    return t if t.lower().endswith(".sct") else t + ".sct"


def mod_targets():
    """(key, src, target) for every mod under Mods/.
    Loose images mirror their pack path; a folder holding manifest.json is a mod pack whose
    "map" says {"local file": "pack/path.sct"}. Bad packs are reported and skipped."""
    out = []
    for root, dirs, files in os.walk(MODS):
        dirs[:] = [d for d in dirs if d != "_disabled"]
        if "manifest.json" in files:
            dirs[:] = []  # a mod pack is one unit; do not descend further
            mp = os.path.join(root, "manifest.json")
            base = os.path.relpath(root, MODS).replace("\\", "/")
            try:
                man = json.load(open(mp, encoding="utf-8"))
                mapping = man["map"]
                if not isinstance(mapping, dict) or not mapping:
                    raise ValueError('"map" must be a non-empty {local file: pack path} object')
            except Exception as e:
                print(f"[X] bad mod pack '{base}/manifest.json': {e}")
                continue
            for local, target in mapping.items():
                src = os.path.join(root, local)
                if not str(local).lower().endswith(IMG_EXT):
                    print(f"[X] '{base}': only image files are supported for now -> skipped {local}")
                    continue
                if not os.path.exists(src):
                    print(f"[X] '{base}': file not found -> skipped {local}")
                    continue
                out.append((f"{base}/{local}".replace("\\", "/"), src, target))
            continue
        for fn in files:
            if fn.lower().endswith(IMG_EXT):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, MODS).replace("\\", "/")
                target = resolve_target(rel, p)
                out.append((rel, p, target))
    return sorted(out)


def _sha1(b):
    return hashlib.sha1(b).hexdigest()


def _load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


_NAMES: list | None = None


def _names():
    """The pack path list (decoded/names_all.json), loaded once per process."""
    global _NAMES
    if _NAMES is None:
        try:
            _NAMES = json.load(open(os.path.join(HERE, "decoded", "names_all.json")))
        except Exception:
            _NAMES = []
    return _NAMES


def _stem_matches(stem):
    """Pack paths whose file name is exactly `<stem>.sct`."""
    s = stem.lower()
    return [n for n in _names() if n.lower().endswith("/" + s + ".sct") or n.lower() == s + ".sct"]


def resolve_target(rel, path):
    """Where a mod's image goes: its czn-target tag, else the mirrored pack path,
    else a file-name match - a unique pack path with the same stem, or
    face/portrait/<stem>.sct for a plain character id (editors like Photoshop
    strip the tag; the file name still carries the meaning). The card shows the
    resolved target before applying."""
    tagged = png_target(path)
    if tagged:
        return tagged
    mirror = os.path.splitext(rel)[0] + ".sct"
    if mirror.lower() in [n.lower() for n in _names()]:
        return mirror
    stem = os.path.splitext(os.path.basename(rel))[0]
    m = _stem_matches(stem)
    if len(m) == 1:
        return m[0]
    if stem.isdigit():
        for n in m:
            if n.lower().startswith("face/portrait/"):
                return n
    return mirror


def _retype_hint(key, path, target):
    """Actionable hint when a mod has no czn-target tag and its target is unknown."""
    if png_target(path):
        return ""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = _stem_matches(stem)
    if len(m) == 1:
        return f'  (no czn-target tag - re-tag: stamp "{key}" {m[0]})'
    if m:
        return (f'  (no czn-target tag; {len(m)} pack paths match "{stem}": '
                + ", ".join(m[:4]) + f' - re-tag: stamp "{key}" <pick one>)')
    return ("  (no czn-target tag and no pack path matches this name - use the "
            "Char ID tab's Export Asset, or 'list <keyword>')")


def _orig_ref_path(key):
    return os.path.join(BACKUP, key.replace("/", "_").replace("\\", "_") + ".orig.png")


def _ensure_orig_ref(key, target, orig):
    """Path of the pristine page PNG used to strip editor ripple from mods.

    Seeded from the pack on the very first apply of a page (the pack still
    holds the true original then). Once the page has backup entries the pack
    is no longer original, so no ref is invented - the ripple pass just stays
    off for it."""
    rp = _orig_ref_path(key)
    if os.path.exists(rp):
        return rp
    try:
        bj = os.path.join(BACKUP, "mod_" + target.replace("/", "_") + ".json")
        if os.path.exists(bj) and json.load(open(bj)):
            return None
        from sct2 import decode
        im, _ = decode(orig)
        os.makedirs(BACKUP, exist_ok=True)
        im.save(rp)
        return rp
    except Exception:
        return None


def apply(quiet=False, verify_all=False):
    """Apply Mods/ -> pack. Skips files whose PNG is unchanged and whose in-pack copy still matches
    what we wrote (verify pass re-checks the pack, catching game repairs). Returns (applied, skipped, failed)."""
    from czn_pack import Pack
    from sct2_enc import encode_like
    from modpack import Modder
    from czn_paths import GAME_ROOT
    if game_running():
        if not quiet:
            print("[X] Game is running - close it first (writing pack files while it runs is unsafe).")
        return (0, 0, 0)
    mods = mod_targets()
    if not mods:
        if not quiet:
            print("[i] Mods/ has nothing to apply. Three ways to mod:")
            print("    self-target : Mods/anything.png  (stamped: cznmod.py stamp <png> <pack/path.sct>)")
            print("    loose image : Mods/face/character/portrait_character_crop_half_1041.png")
            print("    mod pack    : Mods/MyMod/manifest.json  {\"map\": {\"art.png\": \"face/portrait/1041.sct\"}}")
        return (0, 0, 0)
    P = Pack()
    M = Modder()
    st = _load_state()
    ok = skip = fail = 0
    for key, path, target in mods:
        png_sha = _sha1(open(path, "rb").read())
        if not quiet and not png_target(path) and \
                target.lower() != os.path.splitext(key)[0].lower() + ".sct":
            print(f"[i] {key}: no czn-target tag - matched by file name -> {target}")
        entry = st.get(key, {})
        try:
            orig = P.extract(target)
        except KeyError:
            if not quiet:
                print(f"[X] {key}: pack path not found: {target}{_retype_hint(key, path, target)}")
            # remember the failure so the card shows Failed instead of Pending
            st[key] = {"png_sha1": png_sha, "sct_sha1": None, "target": target,
                       "game_root": GAME_ROOT}
            fail += 1
            continue
        ref = _ensure_orig_ref(key, target, orig)
        if entry.get("png_sha1") == png_sha and entry.get("game_root") == GAME_ROOT:
            if not entry.get("sct_sha1"):
                skip += 1  # previous encode failed; wait for the PNG to change
                continue
            if not verify_all or _sha1(orig) == entry["sct_sha1"]:
                skip += 1
                continue
        try:
            new = encode_like(orig, path, EFFORT, ref_png=ref)
            touched = M.inject(target, new, stealth=True, key=key)
            if M.verify(target) != new:
                raise RuntimeError("re-extract verify mismatch")
            st[key] = {"png_sha1": png_sha, "sct_sha1": _sha1(new), "target": target,
                       "game_root": GAME_ROOT}
            ok += 1
            msg = f"{key} -> {target} ({len(new):,} B, {','.join(touched)})"
            if not quiet:
                print(f"[OK] {msg}")
            log("[OK] " + msg)
        except Exception as e:
            st[key] = {"png_sha1": png_sha, "sct_sha1": None, "target": target,
                       "game_root": GAME_ROOT}
            if not quiet:
                print(f"[X] {key}: {type(e).__name__}: {e}")
            log(f"[X] {key}: {type(e).__name__}: {e}")
            fail += 1
    _save_state(st)
    if not quiet or ok or fail:
        print(f"== {ok} applied, {skip} unchanged, {fail} failed ==")
        if ok:
            print("All mods under Mods/ are now inside the game files - open the game via STOVE as usual.")
    return (ok, skip, fail)


def revert(filt=None, targets=None):
    from czn_pack import Pack
    from modpack import restore_region
    if game_running():
        print("[X] Game is running - close it first.")
        return 1
    P = Pack()
    n = 0
    done = set()
    for fn in sorted(os.listdir(BACKUP)) if os.path.isdir(BACKUP) else []:
        if not (fn.startswith("mod_") and fn.endswith(".json")):
            continue
        for bk in json.load(open(os.path.join(BACKUP, fn))):
            name = bk.get("name", "")
            if filt and filt not in name and filt not in bk.get("key", ""):
                continue
            if targets is not None and name not in targets:
                continue
            for c in bk["chunks"]:
                okr, why = restore_region(P.chunks_dir, c)
                if not okr:
                    print(f"[!] {name}: {c['chunk']}@{c['local']:,} skipped - {why}")
                    continue
                print(f"[OK] {name}: {c['chunk']}@{c['local']:,} restored")
                n += 1
            done.add(name)
    st = _load_state()
    moved = 0
    seen_packs = set()
    for key, path, target in mod_targets():
        if not (target in done or (filt and (filt in target or filt in key)) or (targets and target in targets)):
            continue
        pack_dir = os.path.join(MODS, key.split("/")[0])
        if os.path.isfile(os.path.join(pack_dir, "manifest.json")):
            if pack_dir in seen_packs:
                continue
            seen_packs.add(pack_dir)
            dst = os.path.join(MODS, "_disabled", key.split("/")[0])
            shutil.rmtree(dst, ignore_errors=True)
            os.makedirs(os.path.dirname(dst), exist_ok=True)   # fresh Mods: _disabled may not exist yet
            try:
                os.replace(pack_dir, dst)
            except OSError as e:
                print(f"[!] could not park {pack_dir} - {e}")
                continue
            for k in [k for k in st if k.split("/")[0] == key.split("/")[0]]:
                st.pop(k, None)
            moved += 1
        else:
            dst = os.path.join(MODS, "_disabled", key)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.replace(path, dst)
            except OSError as e:
                print(f"[!] could not park {path} - {e}")
                continue
            st.pop(key, None)
            moved += 1
    _save_state(st)
    print(f"== {n} region(s) restored across {len(done)} file(s); {moved} mod(s) moved to Mods/_disabled/ ==")
    return 0


def disabled_mods():
    """Names of mods parked in Mods/_disabled/ (same key shape as mod_targets)."""
    base = os.path.join(MODS, "_disabled")
    out = []
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        if "manifest.json" in files:
            dirs[:] = []
            out.append(os.path.relpath(root, base).replace("\\", "/"))
            continue
        for fn in files:
            if fn.lower().endswith(IMG_EXT):
                out.append(os.path.relpath(os.path.join(root, fn), base).replace("\\", "/"))
    return sorted(out)


def cmd_disable(name):
    """Take one mod (pack folder or loose image) out of the game and park it in Mods/_disabled/."""
    mine = [(k, p, t) for k, p, t in mod_targets() if k == name or k.split("/")[0] == name]
    if not mine:
        print(f"[X] no mod named '{name}' under Mods/")
        return 1
    return revert(targets={t for _, _, t in mine})


def cmd_enable(name):
    """Move a parked mod back from Mods/_disabled/ and apply it."""
    src = os.path.join(MODS, "_disabled", name)
    if not os.path.exists(src):
        print(f"[X] no disabled mod named '{name}'")
        return 1
    dst = os.path.join(MODS, name)
    if os.path.exists(dst):
        print(f"[X] Mods/{name} already exists - rename one of them first")
        return 1
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    print(f"[OK] Mods/_disabled/{name} -> Mods/{name}")
    apply()
    return 0


def _fingerprint():
    """{mod key: (size, mtime_ns)} - cheap way to notice edits without hashing anything."""
    fp = {}
    for key, path, _target in mod_targets():
        try:
            s = os.stat(path)
            fp[key] = (s.st_size, s.st_mtime_ns)
        except OSError:
            pass
    return fp


def watch():
    """Silent auto-apply: while the game is closed, any change under Mods/ is applied within ~3 s.
    Idle cost = one directory scan per 3 s; tasklist is only spawned when a change is pending,
    and every child process runs with CREATE_NO_WINDOW (no console flashes)."""
    os.makedirs(MODS, exist_ok=True)
    open(PIDF, "w").write(str(os.getpid()))
    log("watcher started (silent)")
    last = None
    while True:
        try:
            fp = _fingerprint()
            if fp != last:
                if game_running():
                    pass  # leave `last` stale: retry next tick once the game closes
                else:
                    r = apply(quiet=True)
                    if r[0]:
                        log(f"change pass: applied={r[0]} skipped={r[1]} failed={r[2]}")
                    if r[2] == 0:
                        last = fp
        except Exception as e:
            log(f"watch error: {type(e).__name__}: {e}")
        time.sleep(3)


def cmd_stamp(png, target):
    """(Re)write the "czn-target" tag of a png so it self-describes its pack path.
    The re-save also drops editor metadata (Paint.NET/Photoshop/EXIF): a picked
    file carries nothing but the image and its target - handy before sharing."""
    from PIL import Image, PngImagePlugin
    im = Image.open(png)
    im.load()
    im.info.pop("exif", None)
    pi = PngImagePlugin.PngInfo()
    pi.add_text("czn-target", target.replace("\\", "/"))
    im.save(png, "PNG", pnginfo=pi)
    print(f"[OK] {png}  ->  {target}  (now drop it anywhere under Mods/)")
    return 0


def cmd_selftest():
    """Build a throwaway Mods tree and check detection of all three mod kinds."""
    import tempfile
    from PIL import Image, PngImagePlugin
    global MODS
    orig = MODS
    tmp = tempfile.mkdtemp(prefix="czn_mods_")
    MODS = tmp
    try:
        os.makedirs(os.path.join(tmp, "face", "portrait"))
        open(os.path.join(tmp, "face", "portrait", "1041.png"), "wb").write(b"not a png")
        pi = PngImagePlugin.PngInfo()
        pi.add_text("czn-target", "card/unique_1041_01.sct")
        Image.new("RGBA", (2, 2)).save(os.path.join(tmp, "my renoa art.png"), pnginfo=pi)
        d = os.path.join(tmp, "MyMod")
        os.makedirs(d)
        open(os.path.join(d, "a.png"), "wb").write(b"nothing")
        json.dump({"name": "MyMod", "map": {"a.png": "effect/lenore_1041_ug_eff_1.sct"}},
                  open(os.path.join(d, "manifest.json"), "w"))
        got = {k: t for k, _p, t in mod_targets()}
        assert got["face/portrait/1041.png"] == "face/portrait/1041.sct", got
        assert got["my renoa art.png"] == "card/unique_1041_01.sct", got
        assert got["MyMod/a.png"] == "effect/lenore_1041_ug_eff_1.sct", got
        # an untagged, non-mirrored name gets an actionable re-tag hint
        open(os.path.join(tmp, "1017.png"), "wb").write(b"x")
        hint = _retype_hint("1017.png", os.path.join(tmp, "1017.png"), "1017.sct")
        assert "face/portrait/1017.sct" in hint, hint
        got2 = {k: t for k, _p, t in mod_targets()}
        assert got2["1017.png"] == "face/portrait/1017.sct", got2.get("1017.png")
        print("[OK] selftest: self-target + loose + pack all detected + name match + hint")
        return 0
    finally:
        MODS = orig
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_list(kw):
    p = os.path.join(HERE, "decoded", "names_all.json")
    if not os.path.exists(p):
        print("[i] decoded/names_all.json is missing (it ships with the tool) - 'list' is not available.")
        return 1
    names = json.load(open(p))
    if names and isinstance(names[0], list):
        names = [n[0] for n in names]
    hits = [n for n in names if kw.lower() in n.lower()]
    for n in hits[:80]:
        print(" ", n)
    print(f"== {len(hits)} match(es) for '{kw}' ==")
    return 0


def cmd_dump(ppath, out):
    from czn_pack import Pack
    from sct2 import decode
    d = os.path.dirname(os.path.abspath(out))
    os.makedirs(d, exist_ok=True)
    im, _ = decode(Pack().extract(ppath))
    im.save(out)
    print(f"[OK] {ppath} -> {out} {im.size}")
    return 0


def cmd_export(spec, outdir):
    """Export every image asset of one character (id or keyword) to plain PNGs."""
    from export_char import run
    run(spec, outdir)
    return 0


def cli(argv):
    """Command-line entry shared by `python cznmod.py ...` and the packaged exe (`exe --cli ...`)."""
    cmd = argv[0] if argv else "apply"
    if cmd == "apply":
        if game_running():
            print("[X] Game is running - close it first (nothing was changed).")
            sys.exit(3)
        ok, skip, fail = apply()
        sys.exit(0 if fail == 0 else 2)
    if cmd == "watch":
        sys.exit(watch())
    if cmd == "revert":
        sys.exit(revert(argv[1] if len(argv) > 1 else None))
    if cmd == "disable" and len(argv) > 1:
        sys.exit(cmd_disable(argv[1]))
    if cmd == "enable" and len(argv) > 1:
        sys.exit(cmd_enable(argv[1]))
    if cmd == "list" and len(argv) > 1:
        sys.exit(cmd_list(argv[1]))
    if cmd == "dump" and len(argv) > 2:
        sys.exit(cmd_dump(argv[1], argv[2]))
    if cmd == "export" and len(argv) > 2:
        sys.exit(cmd_export(argv[1], argv[2]))
    if cmd == "stamp" and len(argv) > 2:
        sys.exit(cmd_stamp(argv[1], argv[2]))
    if cmd == "selftest":
        sys.exit(cmd_selftest())
    print(__doc__)


if __name__ == "__main__":
    cli(sys.argv[1:])
