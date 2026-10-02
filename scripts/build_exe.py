"""Package the tool as a single-file exe: dist_exe/Uncle'sCZNMMMI v0.1.exe.

  .venv\\Scripts\\python.exe scripts\\build_exe.py

The exe is fully standalone (no Python needed): GUI when double-clicked, and the same
file serves the command line via `Uncle'sCZNMMMI v0.1.exe --cli <cmd> ...`. Mods/,
backup/ and game_path.txt live next to the exe (main.py sets CZN_APP_DIR).
Naming note: PyInstaller builds under a safe ASCII name, then the artifact is renamed -
spaces/apostrophes never reach PyInstaller's internals.
"""
import os
import shutil
import sys

import PyInstaller.__main__ as pyi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "Uncle'sCZNMMMI v0.1"        # final artifact name
SAFE = "UncleCZNMMMI_v0.1"          # internal build name
DISTP = os.path.join(ROOT, "dist_exe")
WORK = os.path.join(DISTP, "_build")

# Runtime-imported sources ship as plain data (cznmod + scripts are imported via
# sys.path at runtime, so PyInstaller does not have to freeze them; their deps below do).
# ui/ modules freeze FLATTENED at the bundle root (theme.py -> _MEIPASS/theme.py), so
# theme's HERE points at _MEIPASS: its assets must land at _MEIPASS/assets, not ui/assets.
DATA = [
    (os.path.join(ROOT, "cznmod.py"), "."),
    (os.path.join(ROOT, "scripts"), "scripts"),
    (os.path.join(ROOT, "ui", "assets"), "assets"),
    (os.path.join(ROOT, "decoded", "names_all.json"), "decoded"),
    (os.path.join(ROOT, "tools", "astcenc-avx2.exe"), "tools"),
]
HIDDEN = ["zstandard", "xxhash", "lz4", "lz4.block", "texture2ddecoder", "PIL", "PIL.Image"]

README_TXT = """Uncle'sCZNMMMI v0.1 - image/UI mod manager for Chaos Zero Nightmare
=====================================================================

What it does
  Applies image/UI mods into the game files safely: only image payloads are
  swapped, the game's boot integrity check still passes, and everything is
  reversible (originals are kept in a backup folder next to the exe).

Requirements
  - Windows 10/11 (64-bit)
  - Chaos Zero Nightmare installed. The tool searches common drives for it;
    if it cannot find the game, open Settings and click "Browse..." to point
    it at the game folder (the one containing bin\\ and gameres\\).
  - No Python, no setup - this single .exe is the whole tool.

First start
  - Windows SmartScreen may warn ("Windows protected your PC") because the
    file is not code-signed: click "More info" -> "Run anyway".
  - The very first start takes a few extra seconds (the exe unpacks itself).

Using it
  1. Double-click the exe. A "Mods" folder, "backup" folder and settings are
     created next to the exe on first use.
  2. Browse the game's characters in the "Char ID" tab (sidebar): every
     character with its portrait, name and ID; search by name/ID and filter
     by Playable / Support / Other. Portraits render on first open (a few
     seconds) and are cached next to the exe.
  3. Put mods into the Mods folder (the "Open folder" button opens it):
       - self-target png: any .png carrying a "czn-target" tag names the game
         file it replaces - drop it anywhere, name it anything (PNGs exported
         from the asset database are already tagged; re-tag after editing with
         "stamp <file.png> <pack/path.sct>", or rename it to .modfile;
         an editor that strips the tag? keep the game file's name instead:
         1017.png auto-matches face/portrait/1017.sct, or mirror the pack
         path under Mods\\)
       - loose image: Mods\\face\\portrait\\1041.png  (the .png replaces the
         game file with the same path, here face/portrait/1041.sct)
       - mod pack: Mods\\AnyName\\manifest.json =
         {"name": "My mod", "map": {"art.png": "face/portrait/1041.sct"}}
  4. CLOSE THE GAME before applying (the tool refuses to write while it runs).
  5. Press "Apply mods". A new mod shows a "Pending" chip until you do.
  6. Launch the game through STOVE as usual (the game only starts through
     STOVE - a direct launch shows "please run through the launcher").

Undo / switching mods off
  - Click a mod's status chip to disable it (it moves to Mods\\_disabled).
  - "Revert all" restores every original and parks all mods.

Notes
  - Client-side mods: use at your own discretion, like any game mod.
  - Encoding needs a CPU with AVX2 (any gaming PC from ~2014+ has it).
"""


def write_readme():
    """Drop the recipient README next to the built exe."""
    with open(os.path.join(DISTP, "README.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(README_TXT)


def main():
    args = [
        os.path.join(ROOT, "ui", "main.py"),
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", SAFE,
        "--icon", os.path.join(ROOT, "ui", "assets", "icons", "czn.ico"),
        "--distpath", DISTP, "--workpath", WORK, "--specpath", WORK,
        "--exclude-module", "tkinter",
    ]
    for src, dst in DATA:
        args += ["--add-data", f"{src}{os.pathsep}{dst}"]
    for mod in HIDDEN:
        args += ["--hidden-import", mod]
    pyi.run(args)

    built = os.path.join(DISTP, SAFE + ".exe")
    final = os.path.join(DISTP, NAME + ".exe")
    if os.path.exists(final):
        os.remove(final)
    os.replace(built, final)
    write_readme()
    print("exe:", final, f"({os.path.getsize(final) / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
