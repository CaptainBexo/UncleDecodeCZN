"""Swap a character's default assets CONTENT with its `<id>_01` skin content (pilot).

Groups (id = 1056 = Rei):
  model    : model/<id>.{scsp,atlas,sct} <- model/<id>_01.*      (display/walk rig)
  portrait : the face/character/<stem>_<id>.sct family <- its `_01` skin art
             (big portrait, crops, wide, sad variants, face/hud/map/bookmark/popup/sd/shortcut/stress icons)

Payload-only (stealth): record fields, chunk trailers and manifest.ssra stay untouched ->
the boot check sees nothing. New content is padded to the target's ORIGINAL raw size
(scsp/sct: NUL pad after the inner blocks; atlas: newline run) so the manifest record never
changes and zstd still fits the stored slot. Reversible from backup/ (revert).

NOT swapped: the `face/portrait/<id>` spine rig - the skin's scsp raw (259,488) already
exceeds the target raw (235,978) AND its zstd frame cannot fit the 211,331 slot; revisiting
would need an inner-LZ4 recompression trick (new in-game assumption, not worth it for a pilot).

  python scripts/swap_rig.py apply 1056 [--only model|portrait] [--dry]
  python scripts/swap_rig.py revert 1056
  python scripts/swap_rig.py status 1056
  python scripts/swap_rig.py selftest
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from czn_pack import Pack
from modpack import Modder

RIG_EXTS = ("scsp", "atlas", "sct")

PORTRAIT_STEMS = [
    "portrait_character", "portrait_character_crop", "portrait_character_crop_half",
    "portrait_character_wide", "portrait_character_sad_crop", "portrait_character_sad_crop_half",
    "face_character", "face_character_map", "bookmark_face_character_map",
    "face_character_popup", "face_character_sd", "face_character_wide",
    "shortcut_face_character", "stress_mini_face_character",
]


def pairs(cid, group="all"):
    out = []
    if group in ("all", "model"):
        out += [(f"model/{cid}.{e}", f"model/{cid}_01.{e}") for e in RIG_EXTS]
    if group in ("all", "portrait"):
        out += [(f"face/character/{s}_{cid}.sct", f"face/character/{s}_{cid}_01.sct")
                for s in PORTRAIT_STEMS]
    return out


def pad_to(data, length, ext):
    if len(data) > length:
        raise ValueError(f"content {len(data):,} > target raw {length:,} ({ext})")
    n = length - len(data)
    return data + ((b"\n" * n) if ext == "atlas" else (b"\x00" * n))


def cmd_apply(cid, group, dry):
    import cznmod
    if not dry and cznmod.game_running():
        print("[X] Game is running - close it first (nothing was changed).")
        return 3
    P, M = Pack(), Modder()
    for tgt, src in pairs(cid, group):
        rec = P.rec_info(tgt)
        if rec is None or P.rec_info(src) is None:
            print(f"[X] missing in pack: {tgt if rec is None else src}")
            return 1
        new = pad_to(P.extract(src), rec["raw"], tgt.rsplit(".", 1)[1])
        if P.extract(tgt) == new:
            print(f"[skip] {tgt}: already swapped")
            continue
        touched = M.inject(tgt, new, dry=dry, stealth=True, key=f"swap:{cid}")
        back = M.verify(tgt)
        ok = back == new
        print(f"[{'dry' if dry else 'OK'}] {tgt} <- {src}  raw={len(new):,} slot={rec['stored']:,} "
              f"chunks={','.join(touched)} verify={'match' if ok else 'MISMATCH'}")
        if not dry and not ok:
            return 1
    if not dry:
        print(f"[i] undo: python scripts/swap_rig.py revert {cid}   (or python cznmod.py revert swap:{cid})")
    return 0


def cmd_revert(cid):
    import cznmod
    return cznmod.revert(f"swap:{cid}")


def cmd_status(cid):
    P = Pack()
    tot = done = 0
    for tgt, src in pairs(cid):
        try:
            rec = P.rec_info(tgt)
            same = P.extract(tgt) == pad_to(P.extract(src), rec["raw"], tgt.rsplit(".", 1)[1])
        except Exception:
            same = False
        tot += 1
        done += same
        print(f"  {tgt}: {'SWAPPED (skin content)' if same else 'original / not swapped'}")
    print(f"== {done}/{tot} swapped ==")
    return 0


def _selftest():
    assert pad_to(b"abc", 5, "atlas") == b"abc\n\n"
    assert pad_to(b"abc", 5, "scsp") == b"abc\x00\x00"
    assert pad_to(b"abc", 3, "sct") == b"abc"
    try:
        pad_to(b"abcdef", 5, "sct")
        raise AssertionError("overflow must raise")
    except ValueError:
        pass
    assert pairs("1056", "model")[0] == ("model/1056.scsp", "model/1056_01.scsp")
    assert len(pairs("1056", "portrait")) == len(PORTRAIT_STEMS) == 14
    assert pairs("1056", "portrait")[0] == ("face/character/portrait_character_1056.sct",
                                            "face/character/portrait_character_1056_01.sct")
    print("[OK] swap_rig selftest")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["apply", "revert", "status", "selftest"])
    ap.add_argument("cid", nargs="?")
    ap.add_argument("--only", choices=["model", "portrait"], default="all")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        _selftest()
        sys.exit(0)
    if not a.cid:
        ap.error("character id required")
    if a.cmd == "apply":
        sys.exit(cmd_apply(a.cid, a.only, a.dry))
    if a.cmd == "revert":
        sys.exit(cmd_revert(a.cid))
    sys.exit(cmd_status(a.cid))
