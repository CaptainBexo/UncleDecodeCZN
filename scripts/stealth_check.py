"""Verify every chunk we ever touched still passes the game's boot integrity check:
the 16-byte trailer hash must equal the manifest (server) hash. Stealth inject keeps
trailers untouched, so this must print OK for all modded chunks."""
import os
import struct
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    P = Pack()
    bk = os.path.join(HERE, "backup")
    modded = set()
    if os.path.isdir(bk):
        for fn in os.listdir(bk):
            if fn.startswith("mod_") and fn.endswith(".json"):
                for rec in json.load(open(os.path.join(bk, fn))):
                    for c in rec.get("chunks", []):
                        modded.add(c["chunk"])
    if not modded:
        print("no backup records - nothing was ever injected; check skipped")
        return 0
    man = {c["name"]: c for c in P.chunks}
    bad = 0
    for name in sorted(modded):
        p = os.path.join(P.chunks_dir, name)
        if not os.path.exists(p):
            print(f"[!] {name}: file missing")
            bad += 1
            continue
        with open(p, "rb") as fh:
            fh.seek(-16, 2)
            tail = fh.read(16)
        magic, cid, th = struct.unpack_from("<4sIQ", tail, 0)
        m = man.get(name)
        ok = bool(m) and th == m["xh"] and magic == b"SSRC"
        if not ok:
            bad += 1
        print(f"{'OK ' if ok else 'BAD'} {name}: trailer={hex(th)} manifest={hex(m['xh']) if m else None}")
    print(f"== {len(modded) - bad}/{len(modded)} modded chunk(s) still pass the game's boot check ==")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
