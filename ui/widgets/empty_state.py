"""Empty-state panel: dashed frame, cube icon, title and hint.

Fills the whole grid area (min 280px). Accepts drag & drop: while files are
dragged over it the frame turns ACCENT with a light blue wash.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import theme


def url_paths(mime) -> list[str]:
    if not mime.hasUrls():
        return []
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]


class EmptyState(QWidget):
    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setMinimumHeight(280)
        self.setAcceptDrops(True)
        self._drag = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(0)
        lay.addStretch(1)

        icon = QLabel(self)
        icon.setPixmap(theme.icon_pixmap("box", 40, "#565656"))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(icon)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(14)

        title = QLabel("No mods yet", self)
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)

        desc = QLabel('Click "Open folder" and drop your mods in', self)
        desc.setObjectName("emptyDesc")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc)

        lay.addStretch(1)
        self.title = title
        self.desc = desc

    def set_text(self, title: str, desc: str) -> None:
        """Adapt the message to the context (empty tab / empty filter)."""
        self.title.setText(title)
        self.desc.setText(desc)

    # ---------- dashed frame ----------

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        if self._drag:
            p.setBrush(QColor(61, 106, 255, 15))          # rgba(61,106,255,0.06)
            pen = QPen(QColor(theme.ACCENT))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor(255, 255, 255, 31))         # rgba(255,255,255,0.12)
        pen.setWidthF(1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(r, theme.R_CARD, theme.R_CARD)

    # ---------- drag & drop ----------

    def dragEnterEvent(self, e) -> None:
        if url_paths(e.mimeData()):
            e.acceptProposedAction()
            self._drag = True
            self.update()

    def dragLeaveEvent(self, e) -> None:
        self._drag = False
        self.update()

    def dropEvent(self, e) -> None:
        self._drag = False
        self.update()
        paths = url_paths(e.mimeData())
        if paths:
            e.acceptProposedAction()
            self.filesDropped.emit(paths)
