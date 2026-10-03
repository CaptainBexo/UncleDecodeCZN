# Uncle'sCZNMMMI v0.4

Lightweight **image / UI mod manager** for **Chaos Zero Nightmare** (STOVE).
Swap character art, portraits and UI textures with your own images — the game
launches through STOVE exactly as before.

Download the zip from the **Assets** section below, unzip anywhere, run the exe.

## What it does

- **Safe in-place mods.** Only image payloads inside the game's own pack files
  are rewritten. File sizes, offsets and the game's boot-integrity hashes stay
  untouched, so the game boots clean — no launcher surgery, no injected code.
- **Fully reversible.** Original bytes are backed up automatically before the
  first write. "Revert all" (or a mod's status chip) puts everything back.
- **Built-in viewer.** Preview any mod or game model with its real Spine 3.8
  animation and your image swapped in as the texture — before you touch the game.
- **Char ID browser.** Every character with portrait, name and ID. Right-click a
  card to export its textures to start editing from.
- **Zero setup.** One exe, no Python required. Mods, backups and settings live
  next to it.

## Requirements

- Windows 10 / 11 (64-bit); any CPU with AVX2 (gaming PCs from ~2014 on)
- Chaos Zero Nightmare installed through STOVE

## Quick start

1. Download the release zip (Assets, below) and unzip it anywhere.
2. Run **`Uncle'sCZNMMMI v0.4.exe`**.
   Windows SmartScreen may warn ("Windows protected your PC") because the file
   is not code-signed — click **More info → Run anyway**. First start takes a
   few extra seconds while the exe unpacks itself.
3. The tool searches common drives for the game. Not found?
   **Settings → Browse…** and pick the game folder (the one containing `bin\`
   and `gameres\`). The choice is remembered.
4. Put your images into the **Mods** folder (the "Open folder" button opens it).
   Any of these work:
   - **exported & edited image** — right-click a character in **Char ID** →
     *Export Asset*, edit the PNG (keep the size and alpha), drop it into
     `Mods\` under any name. It carries its target with it.
   - **loose image** — mirror the game path, `.png` replaces `.sct`:
     `Mods\face\portrait\1041.png` replaces `face/portrait/1041.sct`
   - **mod pack** — a folder with a `manifest.json` mapping files to targets:
     `{"name": "My mod", "map": {"art.png": "face/portrait/1041.sct"}}`
5. **Close the game**, then press **Apply mods** (the tool refuses to write
   while the game runs).
6. Launch the game through **STOVE** as usual. Your images are in the game.

## Previewing

The **Viewer** button (bottom-right) opens the viewer as a separate window:

- load a mod by dropping a file on the window, picking it with **Load**, or
  clicking a mod card's eye icon — a texture mod plays its character's real
  portrait animation with your image applied;
- the path bar also takes a model name (e.g. `1041` or `model/1041.scsp`);
- wheel = zoom, drag = pan, double-click = fit;
- right-click inside the viewer: Back / Forward / Reload / Save image / Copy image.

Nothing in the viewer writes to the game.

## Undo

- Click a mod's **status chip** to switch it off — the original bytes are
  restored and the mod is parked in `Mods\_disabled`.
- **Revert all** restores every original and parks every mod.

## Notes

- The game must be **closed** while applying.
- After a game update the game may re-download changed files — your mods are
  simply gone from the pack; press Apply mods again.
- Image / UI swaps only: nothing here touches saves, items, matchmaking or the
  network.
- Client-side mods: use at your own discretion, like any game mod.

## Credits

- astcenc (Apache-2.0) — ASTC texture encoding
- zstandard, xxhash, lz4, texture2ddecoder, Pillow — pack + texture tooling
- Inter font (SIL OFL)
- Spine runtimes © Esoteric Software LLC ([license](https://esotericsoftware.com/spine-runtimes-license))
- Chaos Zero Nightmare and all game assets © SuperCreative / STOVE.
  This is an unofficial, non-commercial fan tool.
