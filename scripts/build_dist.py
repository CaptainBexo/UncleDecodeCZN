"""Build a portable copy of the CZN mod tool: dist/UncleDecodeCZN/ + dist/UncleDecodeCZN-mod-tool.zip.

Recipient flow: unzip anywhere -> run Setup.bat once (creates .venv + installs deps) ->
drop mods into Mods/ -> ApplyMods.bat (or the tool's Apply mods button) -> launch the game via STOVE.
"""
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "UncleDecodeCZN")

FILES = [
    "cznmod.py",
    "ui/main.py",
    "ui/main_window.py",
    "ui/theme.py",
    "ui/data.py",
    "ui/widgets/mod_delegate.py",
    "ui/widgets/char_grid.py",
    "ui/widgets/chip_bar.py",
    "ui/widgets/sidebar.py",
    "ui/widgets/title_bar.py",
    "ui/widgets/empty_state.py",
    "ui/assets",
    "scripts/czn_pack.py",
    "scripts/char_catalog.py",
    "scripts/czn_paths.py",
    "scripts/export_char.py",
    "scripts/sct2.py",
    "scripts/sct2_enc.py",
    "scripts/modpack.py",
    "scripts/stealth_check.py",
    "decoded/names_all.json",
    "tools/astcenc-avx2.exe",
    "CZN Mod Tool.bat",
    "ApplyMods.bat",
    "RevertMods.bat",
]

SETUP_BAT = r'''@echo off
cd /d "%~dp0"
title CZN Mod Tool - Setup
echo === CZN mod tool setup ===
if exist ".venv\Scripts\python.exe" goto deps
echo Creating Python environment...
py -3 -m venv .venv 2>nul || python -m venv .venv 2>nul || goto nopython
:deps
echo Installing required packages (needs internet, one time)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto pipfail
echo.
echo Checking the game install...
".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'scripts'); import czn_paths; print('  Game found at:', czn_paths.GAME_ROOT)" || goto nogame
echo.
echo Setup complete. Drop mods into the Mods\ folder, press "Apply mods" in the tool
echo (or run ApplyMods.bat), and launch the game via STOVE as usual.
pause
exit /b 0
:nopython
echo [!] Python 3 was not found. Install it from https://www.python.org/downloads/
echo     (tick "Add python.exe to PATH" during install), then run Setup.bat again.
pause
exit /b 1
:pipfail
echo [!] pip install failed. Check your internet connection, then run Setup.bat again.
pause
exit /b 1
:nogame
echo [!] Could not find the game. Create a file named game_path.txt next to this bat with
echo     one line: the game folder that contains bin\ and gameres\ (example below), then
echo     run Setup.bat again.
echo     E:\Games\ChaosZeroNightmare
pause
exit /b 1
'''

INSTALL_MD = r'''# CZN Mod Tool - install guide

In-place image mod injector for **Chaos Zero Nightmare** (STOVE). Mods are written into
the game's own pack chunks with their integrity hashes untouched ("stealth"), so the game
launches normally through STOVE and sees nothing unusual. Image / UI swaps only.

## Requirements

- Windows 10/11, the game installed via STOVE (any drive).
- Python 3.9+ ([python.org](https://www.python.org/downloads/), tick *Add python.exe to PATH*).
- Internet for the one-time `Setup.bat` (installs the required packages, including PySide6).

## Steps

1. Unzip this folder anywhere (e.g. `D:\CZN-Mod-Tool`). The path may contain spaces.
2. Double-click **Setup.bat** - creates `.venv\`, installs dependencies, prints the detected game path.
3. If setup says the game was not found, create `game_path.txt` next to the bat with one line:
   the folder that contains `bin\` and `gameres\`, e.g. `E:\Games\ChaosZeroNightmare` - or open the
   tool and click **Browse...** on the Settings page (only shown while no game was found).
4. Put mods into `Mods\` (see `Mods\README.txt`):
   - loose image: `Mods\face\portrait\1041.png` (path mirrors the pack, `.png` -> `.sct`)
   - mod pack: `Mods\MyMod\manifest.json` = `{"name": "...", "map": {"art.png": "face/portrait/1041.sct"}}`
5. Double-click **CZN Mod Tool.bat** - the mod manager window: every mod is a card with its
   own preview, the white **Apply mods** button applies everything, click a card's status
   chip to enable/disable that one mod, the game status line sits under **Revert all**,
   and **Open folder** sits in the top toolbar. Command-line equivalents if you prefer:
   **ApplyMods.bat** (one click; 1-2 s when nothing changed) and **RevertMods.bat**.
6. Launch the game through **STOVE** as usual. Mods are in-game.

## Notes

- The game must be CLOSED when applying (the tool refuses otherwise - never writes while the game runs).
- Undo: **RevertMods.bat** restores original bytes from `backup\` and moves those mods to `Mods\_disabled\`.
  A region is only restored while it still holds the bytes the tool wrote - if the game patched or
  re-downloaded that chunk since (or you switched game folders), the restore is skipped instead of
  writing stale bytes.
- `cznmod.py list <keyword>` searches image names; `cznmod.py dump <pack path> out.png` exports the
  current in-game image as the editing base.
- Sanity check that the game's boot integrity check still passes:
  `.venv\Scripts\python.exe scripts\stealth_check.py` prints OK for every modded chunk.
- The pack layout (record count, name blob position) is derived from the manifest itself, so small
  game updates keep working; if a future patch changes the layout the tool stops with a clear
  message instead of reading garbage.
- Third-party bits: astcenc (Apache-2.0), Python packages zstandard / xxhash / lz4 /
  texture2ddecoder / pillow (their own licenses). Game assets remain (c) SuperCreative / STOVE.
'''

REQUIREMENTS = "zstandard\nxxhash==4.0.1\nlz4\ntexture2ddecoder\npillow\nPySide6>=6.6\n"


MODS_README = """How mods work here
==================
Drop any of these into this Mods folder:

- self-target png (easiest): PNGs exported from the asset database carry a
  "czn-target" tag naming the game file they replace - the file name and
  location do not matter:
    Mods\\my renoa art.png     replaces face/portrait/1041.sct (per its tag)
  after editing and the tag is gone, re-tag it with:  stamp <file.png> <pack/path.sct>
  (renaming the file to .modfile also works - the tag lives in the content)

- loose image: keep the in-game path, use .png
    Mods\\face\\portrait\\1041.png   replaces face/portrait/1041.sct

- mod pack folder with manifest.json:
    Mods\\MyMod\\manifest.json
    {"name": "My mod", "map": {"art.png": "face/portrait/1041.sct"}}

Then apply - the game must be CLOSED:
- the tool's "Apply mods" button, or ApplyMods.bat

Undo / switching off:
- click a card's status chip in the tool to disable that one mod
- RevertMods.bat (or "Revert all") restores every original

Notes:
- only image payloads are ever written; the game's boot check stays green
- disabled mods are parked in Mods\\_disabled\\
- the tool only scans Mods\\ itself, so _disabled\\ is safe to keep
"""


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    for rel in FILES:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(DIST, rel)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    # Mods/README.txt - kept inline so the build never depends on the dev tree
    os.makedirs(os.path.join(DIST, "Mods"), exist_ok=True)
    open(os.path.join(DIST, "Mods", "README.txt"), "w", encoding="utf-8",
         newline="\r\n").write(MODS_README)
    for fn, txt in [("Setup.bat", SETUP_BAT)]:
        open(os.path.join(DIST, fn), "wb").write(txt.replace("\n", "\r\n").encode("ascii"))
    open(os.path.join(DIST, "requirements.txt"), "w").write(REQUIREMENTS)
    open(os.path.join(DIST, "INSTALL.md"), "w", encoding="utf-8").write(INSTALL_MD)
    zip_path = os.path.join(ROOT, "dist", "UncleDecodeCZN-mod-tool.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(DIST):
            for fn in files:
                p = os.path.join(base, fn)
                z.write(p, os.path.relpath(p, os.path.dirname(DIST)))
    mb = os.path.getsize(zip_path) / 1e6
    print(f"dist folder: {DIST}")
    print(f"zip:         {zip_path} ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
