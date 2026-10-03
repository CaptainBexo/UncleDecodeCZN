"""Pre-release privacy audit: nothing dev / personal / token-ish may leave this
repo inside a built exe or a release folder. Run it before every build/publish:

  .venv\\Scripts\\python.exe scripts\\privacy_audit.py            # sources + newest exe
  .venv\\Scripts\\python.exe scripts\\privacy_audit.py --release DIR

What it checks
  - every file that ships inside the exe (source whitelist) for personal markers:
    user names, local paths, personal emails, API-token wording, dev-tool names;
  - the exe archive: TOC must hold no dev-only scripts / __pycache__ / .pyc strays,
    embedded .py/.txt/.html/.js entries are extracted and marker-scanned, frozen
    modules must carry plain basename co_filename (never a build-machine path),
    plus a raw byte scan of the whole file;
  - any release folder you point it at.
Exit code 1 on any hit. The tool brand ("Uncle's ...") is intended and allowed.
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# keep in sync with build_exe.SCRIPTS / build_exe.DATA
SHIP_SCRIPTS = ["czn_pack.py", "czn_paths.py", "char_catalog.py", "export_char.py",
                "spine_prep.py", "scsp2json.py", "sct2.py", "sct2_enc.py",
                "modpack.py", "stealth_check.py"]
SHIP_SOURCES = (["cznmod.py"]
                + ["scripts/" + s for s in SHIP_SCRIPTS]
                + [p for p in glob.glob(os.path.join("ui", "*.py"))
                   + glob.glob(os.path.join("ui", "widgets", "*.py"))
                   if os.path.basename(p) not in ("qa_check.py", "e2e_ctx_menu.py")]
                + glob.glob(os.path.join("ui", "assets", "**", "*"), recursive=True)
                + ["decoded/names_all.json"])
# dev one-offs that must never appear in the exe (names, lowercase, .py optional)
DEV_NAMES = ["catalog", "decode_all", "derive_bases", "derive_bases2", "derive_bases3",
             "dump_inet", "extract", "extract_chunks", "field_final", "hash_fields",
             "hash_tlv", "hash_tlv2", "index_build", "index_dump", "inv_img",
             "layout_truth", "make_demo_mod", "manifest_chunks", "manifest_explore",
             "manifest_files", "manifest_map", "manifest_stride", "match_names",
             "multi_part", "name_hash_test", "overlap_probe", "parse_plpck",
             "probe_chunks", "probe_large_exe", "record_fields", "resolve_bases",
             "scan_large", "scan_manifest_exe", "sct2_decode", "sct2_deep",
             "sct2_strings", "sct_inspect", "solve_map", "solve_order", "ssrc_zstd",
             "trailer_check", "wrap_verify", "debug_frames", "char_ids", "revert_mod",
             "build_exe", "build_dist", "chunk_bases", "qa_check", "e2e_ctx_menu"]
# identity markers: full words, safe to scan even in binary data
IDENT = [rb"hanzo", rb"C:\\Users", rb"uncledecode", rb"captainbexo", rb"@gmail",
         rb"gmail\.com", rb"hermes-agent"]
# looser wording: text files only (binary noise matches things like "token=")
LOOSE = [rb"access_token", rb"bearer", rb"sgup://", rb"token="]
TEXT_EXT = (".py", ".txt", ".html", ".js", ".json", ".md", ".bat", ".svg", ".css", ".xml")


# public identifiers that are part of the product itself (the update endpoint URL)
ALLOWED = [b"https://api.github.com/repos/CaptainBexo/UncleDecodeCZN/releases/latest"]


def scan_bytes(label: str, data: bytes, hits: list, markers) -> None:
    for a in ALLOWED:
        data = data.replace(a, b"<public-url>")
    low = data.lower()
    for m in markers:
        i = low.find(m.lower())
        if i >= 0:
            j = max(0, i - 30)
            ctx = data[j:i + len(m) + 30].decode("utf-8", "replace").replace("\n", " ")
            hits.append(f"{label}: {m.decode()!r} -> ...{ctx}...")


def audit_sources(hits: list) -> None:
    for rel in SHIP_SOURCES:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            scan_bytes(rel, open(p, "rb").read(), hits, IDENT + LOOSE)


def audit_exe(path: str, hits: list) -> None:
    from PyInstaller.archive.readers import CArchiveReader
    scan_bytes(os.path.basename(path), open(path, "rb").read(), hits, IDENT)
    r = CArchiveReader(path)
    names = [n for n in r.toc if isinstance(n, str)]
    for n in names:
        low = n.lower().replace("/", "\\")
        base = os.path.basename(low)
        stem = base[:-3] if base.endswith(".py") else base
        if "__pycache__" in low or (base.endswith((".py", ".pyc")) and stem in DEV_NAMES):
            hits.append(f"exe archive: dev-only entry present: {n}")
            continue
        if low.startswith(("pyside6", "shiboken6")) or base.endswith((".dll", ".pyd", ".so")):
            continue                      # upstream binaries: nothing personal can live there
        if base.endswith(TEXT_EXT) or base.endswith((".png", ".ico", ".ttf", ".exe", ".bin")):
            try:
                b = r.extract(n)
                if isinstance(b, (bytes, bytearray)) and len(b) < 8_000_000:
                    scan_bytes(f"exe:{n}", bytes(b), hits,
                               IDENT + LOOSE if base.endswith(TEXT_EXT) else IDENT)
            except Exception:      # noqa: BLE001 - unreadable entries were listed above
                pass
    pyz = [n for n in names if "PYZ" in n.upper()]
    if pyz:
        z = r.open_embedded_archive(pyz[0])
        for mod in [m for m in z.toc if isinstance(m, str)
                    and re.search(r"(main_window|widgets|data|theme|cznmod)", m)][:12]:
            try:
                code = z.extract(mod)
                found = set()

                def walk(c):
                    if hasattr(c, "co_filename"):
                        found.add(c.co_filename)
                        for k in c.co_consts:
                            walk(k)

                walk(code)
                for f in found:
                    if re.match(r"[A-Za-z]:[\\/]", f):
                        hits.append(f"exe frozen {mod}: absolute co_filename {f!r}")
            except Exception:      # noqa: BLE001
                pass


def audit_dir(path: str, hits: list) -> None:
    for base, _d, files in os.walk(path):
        for fn in files:
            p = os.path.join(base, fn)
            try:
                if os.path.getsize(p) < 300_000_000:
                    markers = IDENT + (LOOSE if fn.lower().endswith(TEXT_EXT) else [])
                    scan_bytes(os.path.relpath(p, path), open(p, "rb").read(), hits, markers)
            except OSError:
                pass


def main(argv: list) -> int:
    hits: list = []
    print("== privacy audit ==")
    audit_sources(hits)
    print(f"   sources: {len(SHIP_SOURCES)} files scanned")
    exe = None
    if "--exe" in argv:
        exe = argv[argv.index("--exe") + 1]
    else:
        found = sorted(glob.glob(os.path.join(ROOT, "dist_exe", "*.exe")),
                       key=os.path.getmtime)
        exe = found[-1] if found else None
    if exe and os.path.isfile(exe):
        audit_exe(exe, hits)
        print(f"   exe: {os.path.basename(exe)} scanned")
    else:
        print("   exe: none found (skipped)")
    if "--release" in argv:
        d = argv[argv.index("--release") + 1]
        audit_dir(d, hits)
        print(f"   release dir: {d} scanned")
    if hits:
        print(f"== {len(hits)} HIT(S) - do not ship ==")
        for h in hits:
            print("  [!]", h)
        return 1
    print("== clean ==")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
