"""Embedded Spine viewer panel: QtWebEngine + the vendored spine-webgl 3.8
runtime (ui/assets/spine/).  Assets are prepared by scripts/spine_prep.py into
the app cache and served over loopback by spine_serve.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMenu, QVBoxLayout, QWidget

import spine_serve
import theme


class _ViewerWebView(QWebEngineView):
    """Viewer web view with a trimmed right-click menu: the stock WebEngine menu
    offers Save page / View page source, useless for a WebGL app. Copy image is
    the browser's own action (it grabs the canvas correctly); Save image writes
    the canvas ourselves - QtWebEngine's DownloadImageToDisk never starts a
    download for a WebGL canvas."""

    def _menu(self) -> QMenu:
        menu = QMenu(self)
        for label, wa in (("Back", QWebEnginePage.WebAction.Back),
                          ("Forward", QWebEnginePage.WebAction.Forward),
                          (None, None),
                          ("Reload", QWebEnginePage.WebAction.Reload)):
            if label is None:
                menu.addSeparator()
                continue
            act = self.page().action(wa)
            item = menu.addAction(label)
            item.setEnabled(act.isEnabled())
            item.triggered.connect(act.trigger)
        menu.addSeparator()
        menu.addAction("Save image").triggered.connect(self._save_image)
        act_copy = self.page().action(QWebEnginePage.WebAction.CopyImageToClipboard)
        item = menu.addAction("Copy image")
        item.setEnabled(act_copy.isEnabled())
        item.triggered.connect(act_copy.trigger)
        return menu

    def _save_image(self) -> None:
        """'Save image': write what the viewer shows (canvas or image mode)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image",
            os.path.join(os.path.expanduser("~"), "Downloads", "viewer.png"),
            "PNG image (*.png)")
        if not path:
            return

        def _write(data) -> None:
            try:
                head, b64 = str(data).split(",", 1)
                if "base64" not in head:
                    return
                import base64
                with open(path, "wb") as f:
                    f.write(base64.b64decode(b64))
            except Exception:      # noqa: BLE001 - blank/odd canvas: nothing to write
                pass

        self.page().runJavaScript(
            "(() => { const c = document.getElementById('c');"
            " if (c && c.width && c.height) return c.toDataURL('image/png');"
            " const i = document.getElementById('img');"
            " if (i && !i.hidden && i.naturalWidth) {"
            "   const t = document.createElement('canvas');"
            "   t.width = i.naturalWidth; t.height = i.naturalHeight;"
            "   t.getContext('2d').drawImage(i, 0, 0); return t.toDataURL('image/png'); }"
            " return ''; })()", _write)

    def contextMenuEvent(self, ev) -> None:
        menu = self._menu()
        menu.exec(ev.globalPos())

SPINE_DIR = os.path.join(theme.HERE, "assets", "spine")


class SpinePrep(QThread):
    """Runs the asset prep off the UI thread (conversion / page decoding take a moment)."""

    done = Signal(bool, str, str)          # ok, slug, error-or-empty

    def __init__(self, src: str, slug: str, out_dir: str,
                 override: dict | None = None, parent=None,
                 ref_pages: dict | None = None) -> None:
        super().__init__(parent)
        self._src, self._slug, self._out = src, slug, out_dir
        self._override, self._refs = override, ref_pages

    def run(self) -> None:
        import sys
        import data
        sp = os.path.join(data.ROOT, "scripts")     # _MEIPASS/scripts when frozen
        if sp not in sys.path:
            sys.path.insert(0, sp)
        try:
            import spine_prep
            spine_prep.prepare(self._src, self._out, self._override, self._refs)
            self.done.emit(True, self._slug, "")
        except BaseException as e:  # noqa: BLE001 - SystemExit too: no game -> czn_paths exits
            msg = str(e) if isinstance(e, SystemExit) else "%s: %s" % (type(e).__name__, e)
            self.done.emit(False, self._slug, msg)


class SpinePanel(QWidget):
    """Web view showing one prepared model (viewer.html?m=<slug>)."""

    def __init__(self, cache_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache_dir
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = _ViewerWebView(self)
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

    def show_model(self, slug: str, bump: int = 0, binary: bool = False) -> None:
        self.view.setUrl(QUrl("%s/viewer.html?m=%s&r=%d%s"
                              % (self._serve(), slug, bump, "&bin=1" if binary else "")))

    def show_image(self, rel: str, bump: int = 0) -> None:
        self.view.setUrl(QUrl("%s/viewer.html?img=%s&r=%d" % (self._serve(), rel, bump)))

    def show_message(self, text: str, error: bool = True) -> None:
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        color = "#E06C6C" if error else "#8C8C8C"
        self.view.setHtml(
            '<body style="background:#161616;color:%s;font:12px Inter,sans-serif;'
            'padding:16px;white-space:pre-wrap">%s</body>' % (color, safe))
