"""Locate the Chaos Zero Nightmare install for every tool script.

Resolution order:
  1. CZN_GAME_DIR environment variable (game root, the folder holding bin/ and gameres/)
  2. game_path.txt next to this repo's root (one line, the same folder)
  3. common default install locations
Raises SystemExit with a clear message when nothing matches.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# game_path.txt next to the exe when packaged (main.py sets CZN_APP_DIR), repo root otherwise.
APP = os.environ.get("CZN_APP_DIR") or (
    os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ROOT)


def _candidates():
    yield os.environ.get("CZN_GAME_DIR", "").strip()
    for base in dict.fromkeys((APP, ROOT)):
        cfg = os.path.join(base, "game_path.txt")
        if os.path.isfile(cfg):
            try:
                yield open(cfg, encoding="utf-8-sig").read().strip().strip('"')
            except OSError:
                pass
    for drive in ("E", "D", "C", "F", "G"):
        yield rf"{drive}:\Games\ChaosZeroNightmare"
        yield rf"{drive}:\ChaosZeroNightmare"


def _find():
    for root in _candidates():
        if root and os.path.isfile(os.path.join(root, "bin", "appdata", "cznlive", "gameres", "manifest.ssra")):
            return root
    raise SystemExit(
        "[X] Chaos Zero Nightmare install not found.\n"
        "    Fix: set the CZN_GAME_DIR environment variable, or create game_path.txt next to\n"
        "    the tool with one line - the game folder that contains bin\\ and gameres\\\n"
        "    (e.g. E:\\Games\\ChaosZeroNightmare).")


GAME_ROOT = _find()
GAME = os.path.join(GAME_ROOT, "bin", "appdata", "cznlive")
MAN = os.path.join(GAME, "gameres", "manifest.ssra")
CHUNKS = os.path.join(GAME, "gameres", "chunks")
