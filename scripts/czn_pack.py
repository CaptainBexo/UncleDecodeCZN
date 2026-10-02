"""CZN extractor: manifest.ssra + chunks -> file bytes. Verified model:
- chunk stream per group = chunks in table order, offsets u32 (wrap 2^32, f3 = wrap flag)
- entry: flag=1 -> zstd frame, flag=0 -> raw bytes
- record table @0x760 stride 40, N records; the names blob starts at 0x760 + 40*N and
  opens with the chunk-file names ('*.ssrc', one per chunk-table row) before the
  file-name blob. N is DERIVED from the data (the old 0x3573c8/87529 hardcode only
  fit patch 1.0.81406).
"""
import os, struct, sys, json
from collections import defaultdict
import zstandard as zstd
import xxhash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from czn_paths import GAME

MAN = os.path.join(GAME, "gameres", "manifest.ssra")

REC0, RSTRIDE = 0x760, 40


def _blob_start(d):
    """Find (names_start, record_count) from the manifest itself.

    The correct start satisfies: (start - 0x760) % 40 == 0, and the bytes there
    are the chunk-file names - exactly one '*.ssrc' NUL-string per chunk-table
    row - followed by the file-name blob."""
    L, want, marker = len(d), (REC0 - 0x40) // 32, b".ssrc\x00"
    p = REC0 + RSTRIDE
    while True:
        p = d.find(marker, p, L)
        if p == -1:
            break
        start = d.rfind(b"\x00", REC0, p) + 1     # start of the string containing the marker
        p += 1
        if (start - REC0) % RSTRIDE:
            continue
        q, ok = start, True
        for _ in range(want):
            e = d.find(b"\x00", q)
            if e == -1 or e - q < 6 or not d[q:e].endswith(b".ssrc"):
                ok = False
                break
            q = e + 1
        if ok:
            return start, (start - REC0) // RSTRIDE
    raise RuntimeError("manifest.ssra layout not recognised - this game patch changed the "
                       "pack layout; update the assumptions in czn_pack.py")

class Pack:
    def __init__(self, man=MAN, chunks_dir=None):
        self.d = d = open(man, "rb").read()
        self.chunks_dir = chunks_dir or os.path.join(GAME, "gameres", "chunks")
        self.blob0, self.nrec = _blob_start(d)      # derived, patch-independent
        # chunk table
        self.chunks = []
        for i in range((REC0 - 0x40) // 32):
            o = 0x40 + i * 32
            cid, gid, fl = struct.unpack_from("<IHH", d, o)
            pay, size, xh = struct.unpack_from("<QQQ", d, o + 8)
            self.chunks.append({"cid": cid, "gid": gid, "pay": pay, "size": size, "xh": xh})
        pos = self.blob0
        for c in self.chunks:
            e = d.find(b"\x00", pos)
            c["name"] = d[pos:e].decode()
            pos = e + 1
        # per-group cumulative bases (table order)
        self.gcum = {}
        for gid in sorted({c["gid"] for c in self.chunks}):
            c0 = 0
            lst = []
            for c in self.chunks:
                if c["gid"] != gid:
                    continue
                c["cum0"] = c0
                lst.append(c)
                c0 += c["pay"]
            self.gcum[gid] = lst
        # records
        self.recs = []
        for i in range(self.nrec):
            f = struct.unpack_from("<8I2HI", d, REC0 + i * RSTRIDE)
            self.recs.append(f)
        # file-name blob starts right after the chunk names
        pos = self.blob0
        for _ in self.chunks:
            pos = d.find(b"\x00", pos) + 1
        self.name_base = pos
        self._h2n = None

    def names(self):
        if self._h2n is None:
            pos = self.name_base
            h2n = {}
            d = self.d
            while pos < len(d):
                e = d.find(b"\x00", pos)
                if e == -1:
                    break
                nm = d[pos:e]
                h2n[xxhash.xxh64(nm).intdigest()] = nm.decode("utf-8", "replace")
                pos = e + 1
                # name blob ends where chunk-name-blob structure ends; just try to consume plausibly
                if pos >= len(d):
                    break
            self._h2n = h2n
        return self._h2n

    def lookup(self, name):
        h = xxhash.xxh64(name.encode()).intdigest()
        for i, f in enumerate(self.recs):
            if ((f[1] << 32) | f[0]) == h:
                return i, f
        return None, None

    def real_off(self, f):
        return f[2] + ((1 << 32) if f[3] == 1 else 0)

    def read_stream(self, gid, real, ln):
        """Read ln bytes from group gid stream starting at real offset (across chunk boundaries)."""
        lst = self.gcum[gid]
        out = bytearray()
        for c in lst:
            c0, pay = c["cum0"], c["pay"]
            if real + ln <= c0 or real >= c0 + pay:
                continue
            local = max(0, real - c0)
            take = min(ln - len(out), pay - local)
            p = os.path.join(self.chunks_dir, c["name"])
            with open(p, "rb") as fh:
                fh.seek(local)
                out += fh.read(take)
            if len(out) >= ln:
                break
        if len(out) != ln:
            raise IOError(f"short read: {len(out)} != {ln} (group {gid}, real {real})")
        return bytes(out)

    def extract(self, name):
        i, f = self.lookup(name)
        if f is None:
            raise KeyError(name)
        in_off, f3, stored, raw, f6, name_off, flag, grp, fC = f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9], f[10]
        real = self.real_off(f)
        blob = self.read_stream(grp, real, stored)
        if flag == 1:
            data = zstd.ZstdDecompressor().decompress(blob)
            assert len(data) == raw, f"decompressed {len(data)} != raw {raw} for {name}"
            return data
        return blob

    def rec_info(self, name):
        i, f = self.lookup(name)
        if f is None:
            return None
        return {"idx": i, "in_off": f[2], "f3": f[3], "stored": f[4], "raw": f[5],
                "name_off": f[7], "flag": f[8], "grp": f[9], "real": self.real_off(f)}


if __name__ == "__main__":
    P = Pack()
    print(f"layout derived: names blob @0x{P.blob0:x}, {P.nrec:,} records "
          f"(patch-1.0.81406 values: @0x3573c8, 87,529)")
    checks = [
        ("sound/master.bank", 361306848, None),
        ("wnd/unit_mode_profile_content.csb", 20324, None),
        ("face/portrait/1030.sct", 1483818, b"SCT2"),
    ]
    for name, want, magic in checks:
        try:
            b = P.extract(name)
            ok = len(b) == want and (magic is None or b[:4] == magic)
            print(f"{'OK ' if ok else 'BAD'} {name}: {len(b):,} head={b[:8].hex()}")
        except Exception as e:
            print(f"ERR {name}: {e}")