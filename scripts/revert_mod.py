"""Revert injected mods from backup/ (region bytes + hash fix)."""
import os, sys, struct, json
import xxhash
sys.path.insert(0, os.path.dirname(__file__))
from modpack import Modder, BACKUP, MAN, restore_region
from czn_pack import Pack

def revert(name):
    bkf = os.path.join(BACKUP, f"mod_{name.replace('/', '_')}.json")
    if not os.path.exists(bkf):
        raise FileNotFoundError(bkf)
    bks = json.load(open(bkf))
    P = Pack()
    for bk in bks:
        for c in bk["chunks"]:
            okr, why = restore_region(P.chunks_dir, c)
            if not okr:
                print(f"[!] skip {c['chunk']} @{c['local']:,}: {why}")
                continue
            path = os.path.join(P.chunks_dir, c["chunk"])
            # fix trailer hash
            d = open(path, "rb").read()
            h = xxhash.xxh64(d[:-16]).intdigest()
            with open(path, "r+b") as fh:
                fh.seek(len(d) - 16 + 8)
                fh.write(struct.pack("<Q", h))
            row = next(i for i, cc in enumerate(P.chunks) if cc.get("name") == c["chunk"])
            with open(MAN, "r+b") as fh:
                fh.seek(0x40 + row * 32 + 24)
                fh.write(struct.pack("<Q", h))
            print(f"reverted {c['chunk']} @{c['local']:,}")

if __name__ == "__main__":
    for nm in sys.argv[1:]:
        revert(nm)
    print("done")