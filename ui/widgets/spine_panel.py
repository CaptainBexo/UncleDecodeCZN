"""Embedded Spine viewer panel: QtWebEngine + the vendored spine-webgl 3.8
runtime (ui/assets/spine/).  Assets are prepared by scripts/spine_prep.py into
the app cache and served over loopback by spine_serve.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

import spine_serve
import theme

SPINE_DIR = os.path.join(theme.HERE, "assets", "spine")


class SpinePrep(QThread):
    """Runs spine_prep.prepare off the UI thread (page decoding takes a moment)."""

    done = Signal(bool, str, str)          # ok, slug, error-or-empty

    def __init__(self, name: str, slug: str, out_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._name, self._slug, self._out = name, slug, out_dir

    def run(self) -> None:
        import sys
        import data
        sp = os.path.join(data.ROOT, "scripts")     # _MEIPASS/scripts when frozen
        if sp not in sys.path:
            sys.path.insert(0, sp)
        try:
            import spine_prep
            spine_prep.prepare(self._name, self._out)
            self.done.emit(True, self._slug, "")
        except Exception as e:  # noqa: BLE001 - surface any prep failure in the panel
            self.done.emit(False, self._slug, "%s: %s" % (type(e).__name__, e))


class SpinePanel(QWidget):
    """Web view showing one prepared model (viewer.html?m=<slug>)."""

    def __init__(self, cache_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache_dir
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.view.setToolTip("Spine model preview (spine-webgl 3.8, offline)")
        lay.addWidget(self.view)
        self._base = None
        self.show_message("Select a model on the left to preview it here.", error=False)

    def _serve(self) -> str:
        if self._base is None:
            os.makedirs(self._cache, exist_ok=True)
            for f in ("viewer.html", "spine-webgl.js"):
                # always overwrite: a stale copy here serves the old page forever
                shutil.copyfile(os.path.join(SPINE_DIR, f), os.path.join(self._cache, f))
            self._base = spine_serve.ensure(self._cache)
        return self._base

    def show_model(self, slug: str, bump: int = 0) -> None:
        self.view.setUrl(QUrl("%s/viewer.html?m=%s&r=%d" % (self._serve(), slug, bump)))

    def show_image(self, rel: str, bump: int = 0) -> None:
        self.view.setUrl(QUrl("%s/viewer.html?img=%s&r=%d" % (self._serve(), rel, bump)))

    def show_message(self, text: str, error: bool = True) -> None:
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        color = "#E06C6C" if error else "#8C8C8C"
        self.view.setHtml(
            '<body style="background:#161616;color:%s;font:12px Inter,sans-serif;'
            'padding:16px;white-space:pre-wrap">%s</body>' % (color, safe))
