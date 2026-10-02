# UncleDecodeCZN

Decoder + texture mod toolkit for Chaos Zero Nightmare (yuna engine, STOVE).

## Layout

- `cznmod.py` — Mods/ folder tool: apply / revert / list / dump / stamp (stealth in-place pack patches; the game boots clean through STOVE)
- `ui/` — PySide6 mod manager (real tool, run via `CZN Mod Tool.bat`); QA: `ui/qa_check.py`
- `scripts/` — pack + SCT2 tooling: `czn_pack.py`, `sct2.py`, `sct2_enc.py`, `modpack.py`, `export_char.py`, `char_ids.py`, `build_dist.py`, `build_exe.py`
- `tools/astcenc-avx2.exe` — ASTC encoder used for re-encoding
- `decoded/names_all.json` — game asset name table (runtime dependency)

## Setup (dev)

```
py -3 -m venv .venv
.venv\Scripts\pip install zstandard "xxhash==4.0.1" lz4 texture2ddecoder pillow PySide6 pyinstaller
```

Game files, backups, build outputs and the reference rippers are not committed (see `.gitignore`).
