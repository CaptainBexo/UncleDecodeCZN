"""Window chrome helpers for the frameless window.

DragRow: a header row that drags the window from its empty areas
(double-click toggles maximize).
WindowButtons: the minimize / maximize / close trio, pinned to the content
column's top-right corner on the same 72px header line as the tabs.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

import theme

BTN_W = 46
BTN_H = 40
BTN_Y = 0            # flush with the top edge; the trio hugs the window's top-right corner


class DragRow(QWidget):
    """Header row whose empty area drags the frameless window."""

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            win.showNormal() if win.isMaximized() else win.showMaximized()


class WindowButtons(QWidget):
    """min / max / close pinned to the parent's top-right corner."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(BTN_W * 3, BTN_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.btn_min = self._btn("minsign", "Minimize", "winBtn",
                                 lambda: self.window().showMinimized())
        self.btn_max = self._btn("maxsign", "Maximize", "winBtn", self._toggle_max)
        self.btn_close = self._btn("close", "Close", "winBtnClose",
                                   lambda: self.window().close())
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)
        parent.installEventFilter(self)
        self._reposition(parent)

    def _btn(self, name: str, tip: str, obj: str, slot) -> QPushButton:
        b = QPushButton(self)
        b.setObjectName(obj)
        b.setFixedSize(BTN_W, BTN_H)
        b.setIcon(theme.icon(name, 16, active=theme.TEXT_STRONG))
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        b.clicked.connect(slot)
        return b

    def _toggle_max(self) -> None:
        win = self.window()
        win.showNormal() if win.isMaximized() else win.showMaximized()

    def set_maximized(self, on: bool) -> None:
        self.btn_max.setIcon(theme.icon("restore" if on else "maxsign", 16,
                                        active=theme.TEXT_STRONG))
        self.btn_max.setToolTip("Restore" if on else "Maximize")

    def _reposition(self, parent: QWidget | None = None) -> None:
        parent = parent or self.parentWidget()
        self.move(parent.width() - self.width(), BTN_Y)

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self._reposition(obj)
        return super().eventFilter(obj, ev)
