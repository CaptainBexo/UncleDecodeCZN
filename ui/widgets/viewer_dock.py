"""Viewer: a detached media-player preview window.

The viewer is its own frameless top-level window (drag by its header, resize by
the bottom-right grip, X collapses it).  The main window keeps a small "Viewer"
button at the bottom-right of the content area to bring it back.
It shows one thing at a time in the WebGL page (viewer.html):
  - a mod's image (opened from the eye button on a mod card),
  - a pack Spine model ('model/1041.scsp' or any .scsp substring),
  - a local image file (png/webp/jpg/bmp/gif) or a .sct texture (decoded first).
The path bar + Load/Reload drive it; Reload re-runs the last load, so an image
edited in Photoshop shows its new content on one click.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizeGrip, QToolButton,
                               QVBoxLayout, QWidget)

import data
import theme
from widgets.spine_panel import SpinePanel, SpinePrep
from widgets.title_bar import DragRow

SCRIPTS = os.path.join(data.ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

IMAGE_EXT = (".png", ".webp", ".jpg", ".jpeg", ".bmp", ".gif")


class ViewerOpenButton(QToolButton):
    """Eye button pinned to the bottom-right corner of the main content area."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("viewerOpenBtn")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(theme.icon("eye", 16, theme.TEXT_MUTED, active=theme.TEXT_STRONG))
        self.setText("Viewer")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setFixedSize(96, 32)
        self.setToolTip("Open the Viewer window (preview a mod image or a game model)")
        parent.installEventFilter(self)
        self._place(parent)

    def _place(self, parent: QWidget | None = None) -> None:
        p = parent if parent is not None else self.parentWidget()
        if p is not None:
            self.move(p.width() - self.width() - 18, p.height() - self.height() - 14)

    def eventFilter(self, obj, ev) -> bool:
        if ev.type() == QEvent.Type.Resize and obj is self.parentWidget():
            self._place(obj)
        return False


class ViewerDock(QWidget):
    """The detached viewer window: header + path bar (Load / Reload) + the player."""

    def __init__(self, mods_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("viewerDock")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Viewer - CZN MM/MI")
        self.resize(540, 680)
        self.setMinimumSize(420, 480)
        self._mods_dir = mods_dir
        self._last: tuple | None = None       # ("image", path) | ("spine", pack_path)
        self._prep = None
        self._n = 0
        self._placed = False                  # first open positions it next to the main window

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 12)
        lay.setSpacing(0)

        head = DragRow(self)                  # drag handle for the frameless window
        head.setFixedHeight(44)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Viewer", head)
        title.setObjectName("pageTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self.close_btn = QToolButton(head)
        self.close_btn.setObjectName("dockClose")
        self.close_btn.setIcon(theme.icon("close", 14, theme.TEXT_MUTED, active=theme.TEXT_STRONG))
        self.close_btn.setToolTip("Hide the viewer (the Viewer button in the main window brings it back)")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setFixedSize(24, 24)
        hl.addWidget(self.close_btn)
        lay.addWidget(head)
        lay.addSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.path = QLineEdit(self)
        self.path.setObjectName("searchBox")
        self.path.setFixedHeight(32)
        self.path.setPlaceholderText("Mod name, model/1041.scsp, or a .skel/.atlas/.png...")
        self.path.setToolTip("Type a mod name, a pack path like model/1041.scsp, "
                             "or a local .skel/.atlas/.png path, then press Enter. "
                             "The Load button opens a file picker instead.")
        self.path.returnPressed.connect(self.load_text)
        row.addWidget(self.path, 1)
        self.load_btn = QPushButton("Load", self)
        self.load_btn.setObjectName("dockBtn")
        self.load_btn.setFixedSize(64, 32)
        self.load_btn.setToolTip("Pick .skel / .atlas / .png files - related files "
                                 "(.skel, .atlas, pages) sync and load automatically")
        self.load_btn.clicked.connect(self.pick_file)
        row.addWidget(self.load_btn)
        self.reload_btn = QPushButton("Reload", self)
        self.reload_btn.setObjectName("dockBtn")
        self.reload_btn.setFixedSize(72, 32)
        self.reload_btn.setToolTip("Re-read the current item (picks up edits on disk)")
        self.reload_btn.clicked.connect(self.reload)
        row.addWidget(self.reload_btn)
        lay.addLayout(row)
        lay.addSpacing(6)

        self.status = QLabel("", self)
        self.status.setObjectName("statusLine")
        self.status.setFixedHeight(18)
        lay.addWidget(self.status)
        lay.addSpacing(4)

        self.panel = SpinePanel(data.SPINE_CACHE, self)
        lay.addWidget(self.panel, 1)

        self._grip = QSizeGrip(self)          # frameless windows need a resize handle
        self._grip.setFixedSize(16, 16)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._grip.move(self.width() - 16, self.height() - 16)

    # ---------- loads ----------

    def show_mod(self, mod: data.Mod) -> None:
        """Preview a mod: when its target has a sibling Spine model (e.g.
        face/portrait/1017.scsp for face/portrait/1017.sct) play that animation
        with the mod's image swapped in as the atlas page; else show the image."""
        if not (mod.banner and os.path.isfile(mod.banner)):
            self._say("This mod has no preview image", error=True)
            return
        self.path.setText(mod.name)
        target = (mod.desc or "").strip()
        base = target[: -len(".sct")] if target.lower().endswith(".sct") else target
        if base and (base + ".scsp") in set(data.spine_files()):
            self.load_mod_spine(base, mod.banner)
            return
        self.load_image(mod.banner, mod.name)

    def load_mod_spine(self, base: str, img: str) -> None:
        """Play the pack model at `base` with `img` replacing its page."""
        if self._prep is not None and self._prep.isRunning():
            return
        override = {os.path.basename(base) + ".sct": img}
        slug = "mod_" + hashlib.sha1(("%s|%s" % (base, img)).encode("utf-8")).hexdigest()[:8]
        self._last = ("modspine", base, img)
        self._say("Preparing %s with %s ..." % (base, os.path.basename(img)))
        self._prep = SpinePrep("pack", base + ".scsp", slug,
                               os.path.join(data.SPINE_CACHE, slug), override, self)
        self._prep.done.connect(self._spine_ready)
        self._prep.start()

    def pick_file(self) -> None:
        """Load button: pick a Spine file; its siblings (.skel/.json, .atlas,
        pages) are resolved automatically."""
        start = self.path.text().strip()
        start = start if os.path.isdir(start) else os.path.dirname(start)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Spine files", start,
            "Spine files (*.skel *.json *.atlas *.png *.webp *.jpg *.jpeg *.bmp);;All files (*)")
        if not path:
            return
        self.path.setText(path)
        self.load_text()

    def _has_trio(self, path: str) -> bool:
        try:
            import spine_prep
            spine_prep.pick_trio(path)
            return True
        except Exception:  # noqa: BLE001 - no trio beside it: plain image then
            return False

    def _pack_base(self, path: str) -> str:
        """A pack model whose name matches this file's stem, e.g.
        1017.png -> 'face/portrait/1017' (load_mod_spine swaps the image in)."""
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        hits = [n for n in data.spine_files()
                if os.path.splitext(os.path.basename(n))[0].lower() == stem]
        return hits[0][: -len(".scsp")] if hits else ""

    def load_text(self) -> None:
        text = self.path.text().strip()
        if not text:
            self._say("Type a mod name, a .scsp pack path, a .skel/.atlas file or an image", error=True)
            return
        if os.path.isdir(text):
            self.load_trio(text)
            return
        if os.path.isfile(text):
            ext = os.path.splitext(text)[1].lower()
            if ext in (".skel", ".json", ".atlas"):
                self.load_trio(text)
                return
            if ext in IMAGE_EXT or ext == ".sct":
                if self._has_trio(text):
                    self.load_trio(text)             # an image syncs with its Spine siblings
                    return
                base = self._pack_base(text)         # ...or with the game's own model
                if base:
                    self.load_mod_spine(base, text)  # play it with this image as its page
                    return
            self.load_image(text)
            return
        mods = self._mod_matches(text)
        if mods:
            self.show_mod(mods[0])
            if len(mods) > 1:
                self._say("Loaded %s (%d mods match)" % (mods[0].name, len(mods)))
            return
        files = data.spine_files()
        if text in set(files):
            self.load_spine(text)
            return
        hits = [n for n in files if text.lower() in n.lower()]
        if hits:
            self.load_spine(hits[0])
            self._say("Loaded %s (%d models match)" % (hits[0], len(hits)))
            return
        self._say("Nothing matches '%s'" % text, error=True)

    def load_image(self, path: str, label: str = "") -> None:
        try:
            name = self._stage_image(path)
        except Exception as e:  # noqa: BLE001 - surface the real reason in the status
            self._say("Failed: %s: %s" % (type(e).__name__, e), error=True)
            return
        self._last = ("image", path)
        self.panel.show_image("img/" + name, self._bump())
        self._say("Loaded " + (label or os.path.basename(path)))

    def load_spine(self, name: str) -> None:
        if self._prep is not None and self._prep.isRunning():
            return
        slug = name[: -len(".scsp")].replace("/", "__")
        self._last = ("spine", name)
        self._say("Preparing %s ..." % name)
        self._prep = SpinePrep("pack", name, slug, os.path.join(data.SPINE_CACHE, slug), None, self)
        self._prep.done.connect(self._spine_ready)
        self._prep.start()

    def load_trio(self, path: str) -> None:
        """Local standard Spine files: a .skel/.json, a .atlas, or a folder with them."""
        if self._prep is not None and self._prep.isRunning():
            return
        slug = "local_" + hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:8]
        self._last = ("trio", path)
        self._say("Preparing %s ..." % os.path.basename(path))
        self._prep = SpinePrep("files", path, slug, os.path.join(data.SPINE_CACHE, slug), None, self)
        self._prep.done.connect(self._spine_ready)
        self._prep.start()

    def reload(self) -> None:
        if not self._last:
            self._say("Nothing loaded yet", error=True)
            return
        kind = self._last[0]
        if kind == "image":
            self.load_image(self._last[1])
        elif kind == "trio":
            self.load_trio(self._last[1])
        elif kind == "modspine":
            self.load_mod_spine(self._last[1], self._last[2])
        else:
            self.load_spine(self._last[1])

    # ---------- internals ----------

    def _mod_matches(self, text: str) -> list[data.Mod]:
        q = text.lower()
        en, off = data.scan(self._mods_dir)
        return [m for m in (*en, *off) if q in m.name.lower() or q in m.key.lower()]

    def _stage_image(self, path: str) -> str:
        """Copy (or decode, for .sct) the image into the served cache; returns its name."""
        img_dir = os.path.join(data.SPINE_CACHE, "img")
        os.makedirs(img_dir, exist_ok=True)
        tag = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:8]
        stem, ext = os.path.splitext(os.path.basename(path))
        ext = ext.lower()
        if ext == ".sct":
            from sct2 import decode
            with open(path, "rb") as f:
                im, _meta = decode(f.read())
            out = "%s_%s.png" % (tag, stem)
            im.convert("RGBA").save(os.path.join(img_dir, out))
        elif ext in IMAGE_EXT:
            out = "%s_%s%s" % (tag, stem, ext)
            shutil.copyfile(path, os.path.join(img_dir, out))
        else:
            raise ValueError("not an image file (%s)" % (ext or "no extension"))
        return out

    def _spine_ready(self, ok: bool, slug: str, err: str) -> None:
        if ok:
            binary = os.path.isfile(os.path.join(data.SPINE_CACHE, slug, "skeleton.skel"))
            self.panel.show_model(slug, self._bump(), binary)
            self._say("Loaded " + slug.replace("__", "/"))
        else:
            self._say("Failed: " + err, error=True)

    def _bump(self) -> int:
        self._n += 1
        return self._n

    def _say(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet("color: %s" % (theme.DANGER if error else theme.TEXT_TOTAL))
