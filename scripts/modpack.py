"""In-place pack mod injector: replace file bytes in chunks, keep sizes/stream, fix trailers+manifest hash."""
import os, sys, struct, json, time
import zstandard as zstd, xxhash

sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack
from czn_paths import MAN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.environ.get("CZN_APP_DIR") or (
    os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ROOT)
BACKUP = os.path.join(APP, "backup")

class Modder:
    def __init__(self):
        self.P = Pack()

    def build_entry(self, rec, new_bytes):
        flag, stored, raw = rec["flag"], rec["stored"], rec["raw"]
        if flag == 0:
            if len(new_bytes) != stored:
                raise ValueError(f"raw entry needs exactly {stored:,} bytes, got {len(new_bytes):,}")
            return new_bytes
        if len(new_bytes) != raw:
            raise ValueError(f"compressed entry needs raw size {raw:,}, got {len(new_bytes):,}")
        frame = None
        for lvl in (19, 15, 9, 6, 3):
            f = zstd.ZstdCompressor(level=lvl).compress(new_bytes)
            if len(f) <= stored:
                frame = f
                break
        if frame is None:
            raise ValueError(f"zstd cannot fit {stored:,} bytes")
        rem = stored - len(frame)
        if rem == 0:
            return frame
        if rem < 8:
            raise ValueError(f"pad gap {rem} too small for skippable frame")
        return frame + struct.pack("<II", 0x184D2A50, rem - 8) + b"\x00" * (rem - 8)

    def inject(self, name, new_bytes, dry=False, backup=True, stealth=False, key=None):
        P = self.P
        rec = P.rec_info(name)
        if rec is None:
            raise KeyError(name)
        entry = self.build_entry(rec, new_bytes)
        grp, real = rec["grp"], rec["real"]
        lst = P.gcum[grp]
        # locate chunks; keep the byte slices we are about to write
        parts = []
        pos, e = real, entry
        for c in lst:
            c0, pay = c["cum0"], c["pay"]
            if pos + len(e) <= c0 or pos >= c0 + pay:
                continue
            local = max(0, pos - c0)
            take = min(len(e), c0 + pay - pos)
            parts.append((c, local, take, e[:take]))
            e = e[take:]
            pos += take
            if not e:
                break
        if e:
            raise RuntimeError("entry spans beyond group chunks")
        # backup originals (keeps the FIRST backup = the true original)
        if backup and not dry:
            os.makedirs(BACKUP, exist_ok=True)
            bk = {"name": name, "key": key or name, "ts": time.time(), "chunks": [], "manifest": []}
            for c, local, take, piece in parts:
                path = os.path.join(P.chunks_dir, c["name"])
                with open(path, "rb") as fh:
                    fh.seek(local)
                    orig_entry = fh.read(take)
                bakf = os.path.join(BACKUP, f"{c['name']}.region.{local}.bin")
                if not os.path.exists(bakf):
                    open(bakf, "wb").write(orig_entry)
                bk["chunks"].append({"chunk": c["name"], "local": local,
                                     "orig_bak": os.path.basename(bakf),
                                     "applied": hex(xxhash.xxh64(piece).intdigest())})
            mfh = MAN
            row = next(i for i, cc in enumerate(P.chunks) if cc.get("name") == parts[0][0]["name"])
            bk["manifest"] = [{"row": row, "orig_hash": hex(struct.unpack_from('<Q', P.d, 0x40 + row * 32 + 24)[0])}]
            bkf = os.path.join(BACKUP, f"mod_{name.replace('/', '_')}.json")
            allbk = json.load(open(bkf)) if os.path.exists(bkf) else []
            allbk.append(bk)
            json.dump(allbk, open(bkf, "w"), indent=1)
        # write
        touched = set()
        for c, local, take, piece in parts:
            path = os.path.join(P.chunks_dir, c["name"])
            if not dry:
                with open(path, "r+b") as fh:
                    fh.seek(local)
                    fh.write(piece)
            touched.add(c["name"])
        # fix trailers + manifest hashes (skipped in stealth: payload-only)
        if not dry and not stealth:
            for cn in touched:
                path = os.path.join(P.chunks_dir, cn)
                d = open(path, "rb").read()
                payload, tr = d[:-16], d[-16:]
                h = xxhash.xxh64(payload).intdigest()
                if struct.unpack_from("<Q", tr, 8)[0] != h:
                    with open(path, "r+b") as fh:
                        fh.seek(len(d) - 16 + 8)
                        fh.write(struct.pack("<Q", h))
                row = next(i for i, cc in enumerate(P.chunks) if cc.get("name") == cn)
                mo = 0x40 + row * 32 + 24
                with open(MAN, "r+b") as fh:
                    fh.seek(mo)
                    fh.write(struct.pack("<Q", h))
        return sorted(touched)

    def verify(self, name):
        """Re-extract from disk via fresh Pack and return bytes."""
        P2 = Pack()
        return P2.extract(name)


def restore_region(chunks_dir, c, backup_dir=BACKUP):
    """Put one backed-up region back, refusing when it is no longer ours.

    Returns (restored, reason). If the chunk does not hold the bytes we wrote
    anymore (game re-downloaded / patched it since), the backup is stale and
    restoring it would corrupt the pack - skip instead.
    """
    src = os.path.join(backup_dir, c["orig_bak"])
    if not os.path.exists(src):
        return False, "backup blob missing"
    orig = open(src, "rb").read()
    path = os.path.join(chunks_dir, c["chunk"])
    if not os.path.exists(path):
        return False, "chunk file missing"
    with open(path, "r+b") as fh:
        fh.seek(c["local"])
        cur = fh.read(len(orig))
        ap = c.get("applied")
        if ap and xxhash.xxh64(cur).intdigest() != int(ap, 16):
            return False, "chunk changed since it was modded (game update/repair?)"
        fh.seek(c["local"])
        fh.write(orig)
    return True, "restored"


def _selftest():
    """Run: python modpack.py --selftest  (no game needed)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cdir, bdir = os.path.join(td, "chunks"), os.path.join(td, "backup")
        os.makedirs(cdir), os.makedirs(bdir)
        open(os.path.join(bdir, "b.bin"), "wb").write(b"ORIG")
        cpath = os.path.join(cdir, "c.ssrc")
        rec = {"chunk": "c.ssrc", "local": 4, "orig_bak": "b.bin",
               "applied": hex(xxhash.xxh64(b"MODD").intdigest())}
        open(cpath, "wb").write(b"headMODDtail")           # our bytes -> restores
        ok, why = restore_region(cdir, rec, bdir)
        assert ok and open(cpath, "rb").read() == b"headORIGtail", (ok, why)
        open(cpath, "wb").write(b"headNEWPtail")           # game replaced it -> refuses
        ok, why = restore_region(cdir, rec, bdir)
        assert not ok and "changed" in why, (ok, why)
        assert open(cpath, "rb").read() == b"headNEWPtail" # refusal leaves it untouched
        assert restore_region(cdir, {"chunk": "gone.ssrc", "local": 0,
                                     "orig_bak": "b.bin"}, bdir)[0] is False
        print("modpack selftest ok: restores own bytes, refuses stale, survives missing chunk")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("png", nargs="?")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--effort", default="-medium")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        raise SystemExit(0)
    if not (a.name and a.png):
        ap.error("name and png are required (or use --selftest)")
    from sct2_enc import encode_like
    M = Modder()
    orig = M.P.extract(a.name)
    new = encode_like(orig, a.png, a.effort)
    rec = M.P.rec_info(a.name)
    print(f"orig={len(orig):,} new={len(new):,} rec stored={rec['stored']:,} raw={rec['raw']:,} flag={rec['flag']}")
    touched = M.inject(a.name, new, dry=a.dry)
    print("touched chunks:", touched, "(dry)" if a.dry else "")
    if not a.dry:
        back = M.verify(a.name)
        ok = back == new
        print("verify re-extract == new:", ok)