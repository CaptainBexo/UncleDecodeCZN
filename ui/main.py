"""CZN MM/MI (Uncle's CZN Mod Manager / Mod Importer) - entry point.

  python main.py                run the tool
  python main.py --mods DIR     point it at a different Mods folder (QA fixtures)
  python main.py --shot         save QA screenshots (1100x700, 1400x850; "@150" at 150%)
  main.py --cli <cmd> ...       (packaged exe only) run the cznmod command line

In the packaged exe, CZN_APP_DIR points at the folder holding the exe: Mods/, backup/ and
game_path.txt all live next to the exe instead of inside the onefile extraction folder.
"""
from __future__ import annotations

import os
import sys

if getattr(sys, "frozen", False):
    os.environ.setdefault("CZN_APP_DIR", os.path.dirname(os.path.abspath(sys.executable)))

if "--cli" in sys.argv:
    # The packaged exe re-enters itself as the command-line tool (data.cli spawns `exe --cli ...`).
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cznmod import cli
    cli(sys.argv[sys.argv.index("--cli") + 1:])
    raise SystemExit(0)

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

import theme
from main_window import MainWindow

SHOT_SIZES = [(1100, 700), (1400, 850)]


def _probe() -> None:
    """CZN_PROBE=1 diagnostic: dump how the frozen app resolved its assets next to the exe."""
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtSvg import QSvgRenderer
    svg = os.path.join(theme.ICON_DIR, "close.svg")
    pm = theme.icon_pixmap("close", 16, "#FFFFFF")
    app_icon = QApplication.instance().windowIcon()
    app_icon.pixmap(64, 64).save(os.path.join(os.environ.get("CZN_APP_DIR") or ".", "icon_dump.png"))
    lines = [
        f"frozen={getattr(sys, 'frozen', False)}",
        f"sys.executable={sys.executable}",
        f"CZN_APP_DIR={os.environ.get('CZN_APP_DIR')}",
        f"theme.__file__={theme.__file__}",
        f"ICON_DIR={theme.ICON_DIR} isdir={os.path.isdir(theme.ICON_DIR)}",
        f"FONT_DIR={theme.FONT_DIR} isdir={os.path.isdir(theme.FONT_DIR)}",
        f"close.svg exists={os.path.exists(svg)}",
        f"svg renderer valid={QSvgRenderer(svg).isValid()}",
        f"icon_pixmap null={pm.isNull()} size={pm.width()}x{pm.height()}",
        f"Inter loaded={any(f.startswith('Inter') for f in QFontDatabase.families())}",
        f"windowIcon null={app_icon.isNull()} sizes={[f'{s.width()}x{s.height()}' for s in app_icon.availableSizes()] or 'scalable'}",
    ]
    with open(os.path.join(os.environ.get("CZN_APP_DIR") or ".", "probe.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    theme.apply(app)
    # Taskbar button + Alt-Tab + taskbar hover preview all read the window icon.
    app.setWindowIcon(QIcon(os.path.join(theme.ICON_DIR, "czn.png")))
    if os.environ.get("CZN_PROBE"):
        _probe()

    mods_dir = None
    if "--mods" in sys.argv:
        mods_dir = sys.argv[sys.argv.index("--mods") + 1]

    win = MainWindow(mods_dir)
    win.show()

    if "--shot" in sys.argv:
        os.makedirs("shots", exist_ok=True)
        for w, h in SHOT_SIZES:
            win.resize(w, h)
            for _ in range(4):
                app.processEvents()
            dpr = win.devicePixelRatioF()
            suffix = "@150" if dpr != 1 else ""
            path = os.path.join("shots", f"main_{w}x{h}{suffix}.png")
            win.grab().save(path)
            print("saved", path)
        sys.exit(0)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
