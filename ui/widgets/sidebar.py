"""Left sidebar column (bg #101010, full window height).

72px header row (draggable: game icon + "CZN MM/MI" + the Uncle's ... subtitle)
/ menu / bottom apply block (primary "Apply mods" + "Revert all" ghost, with the
game status line under them). The apply block is disabled with a 0.5 opacity
while the game is running - writing needs the game closed.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

import data
import theme
from widgets.title_bar import DragRow


class StatusDot(QWidget):
    """8px status dot: grey = game closed, green = game running."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = theme.GAME_OFF

    def set_color(self, color: str) -> None:
        if color != self._color:
            self._color = color
            self.update()

    def paintEvent(self, e) -> None:
        from PySide6.QtGui import QColor, QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(self.rect())


class Sidebar(QWidget):
    applyClicked = Signal()
    revertClicked = Signal()
    runGameClicked = Signal()
    pageChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(theme.SIDEBAR_W)
        self._running = False
        self._busy = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 72px row, same height and centre line as the tab row in the content column
        name_row = DragRow(self)
        name_row.setFixedHeight(theme.HEADER_H)
        nv = QVBoxLayout(name_row)
        nv.setContentsMargins(theme.PAD_SIDE, 0, theme.PAD_SIDE, 0)
        nv.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(10)
        ic = QLabel(name_row)
        ic.setObjectName("appIcon")
        ic.setPixmap(QPixmap(os.path.join(theme.ICON_DIR, "czn.png")).scaled(
            26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        name = QLabel("CZN MM/MI", name_row)
        name.setObjectName("appName")
        top.addWidget(ic)
        top.addWidget(name)
        top.addStretch(1)
        sub = QLabel("Uncle's CZN Mod Manager / Mod Importer", name_row)
        sub.setObjectName("appSub")
        sub.setWordWrap(True)                  # wraps only if a font change pushes it past the sidebar
        nv.addStretch(1)
        nv.addLayout(top)
        nv.addWidget(sub)
        nv.addStretch(1)
        lay.addWidget(name_row)
        self._name_row = name_row

        menu = QWidget(self)
        menu_lay = QVBoxLayout(menu)
        menu_lay.setContentsMargins(theme.PAD_SIDE, 0, theme.PAD_SIDE, 0)
        menu_lay.setSpacing(4)
        self.menu_group = QButtonGroup(self)
        self.menu_group.setExclusive(True)
        self._menu_items: list[QPushButton] = []
        for icon_name, label in data.MENU:
            b = self._menu_item(icon_name, label)
            self.menu_group.addButton(b)
            menu_lay.addWidget(b)
            self._menu_items.append(b)
        self._menu_items[0].setChecked(True)
        self.menu_group.buttonClicked.connect(lambda b: self.pageChanged.emit(b.text()))

        # quick-launch under the Char ID tab: needs STOVE running in the background
        menu_lay.addSpacing(12)
        self.run_game = QPushButton("Run Game", menu)
        self.run_game.setObjectName("runGameBtn")
        self.run_game.setFixedHeight(44)
        self.run_game.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_game.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.run_game.clicked.connect(self.runGameClicked)
        menu_lay.addWidget(self.run_game)
        menu_lay.addSpacing(4)
        self.run_hint = QLabel("Open STOVE first (can stay in tray)", menu)
        self.run_hint.setObjectName("runHint")
        self.run_hint.setWordWrap(True)
        menu_lay.addWidget(self.run_hint)
        self._stove = False
        self._run_enabled()
        lay.addWidget(menu)

        lay.addStretch(1)

        # ---- inject block ----
        lay.addWidget(self._divider())

        block = QWidget(self)
        self._block = block
        bl = QVBoxLayout(block)
        bl.setContentsMargins(theme.PAD_SIDE, 14, theme.PAD_SIDE, theme.PAD_SIDE)
        bl.setSpacing(0)

        self.primary = QPushButton("Apply mods", block)
        self.primary.setObjectName("primaryBtn")
        self.primary.setFixedHeight(44)
        self.primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.primary.clicked.connect(self.applyClicked)
        bl.addWidget(self.primary)
        bl.addSpacing(8)

        self.revert = QPushButton("Revert all", block)
        self.revert.setObjectName("ghostBtn")
        self.revert.setFixedHeight(32)
        self.revert.setIcon(theme.icon("undo", 16))
        self.revert.setIconSize(QSize(16, 16))
        self.revert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.revert.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.revert.clicked.connect(self.revertClicked)
        bl.addWidget(self.revert)
        bl.addSpacing(12)

        status = QHBoxLayout()
        status.setContentsMargins(2, 0, 0, 0)
        status.setSpacing(8)
        self.dot = StatusDot(block)
        self.status_lbl = QLabel("Game closed", block)
        self.status_lbl.setObjectName("injectStatus")
        status.addWidget(self.dot)
        status.addWidget(self.status_lbl)
        status.addStretch(1)
        bl.addLayout(status)

        lay.addWidget(block)
        self._effect = QGraphicsOpacityEffect(block)
        self._effect.setOpacity(1.0)
        block.setGraphicsEffect(self._effect)

    # ---------- state ----------

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.primary.setText("Working..." if busy else "Apply mods")
        self._apply_enabled()

    def set_game(self, running: bool) -> None:
        if running == self._running:
            return
        self._running = running
        self.dot.set_color(theme.GAME_ON if running else theme.GAME_OFF)
        self.status_lbl.setText("Game running" if running else "Game closed")
        self._apply_enabled()
        self._run_enabled()

    def set_stove(self, running: bool) -> None:
        if running == self._stove:
            return
        self._stove = running
        self._run_enabled()

    def _run_enabled(self) -> None:
        """Run Game works only while STOVE runs in the background and the game is closed."""
        self.run_game.setEnabled(self._stove and not self._running)
        if self._running:
            self.run_hint.setText("Game is already running")
        elif self._stove:
            self.run_hint.setText("STOVE is running - click to launch")
        else:
            self.run_hint.setText("Open STOVE first (can stay in tray)")

    def _apply_enabled(self) -> None:
        # Writing needs the game CLOSED: while it runs the whole block is disabled.
        ok = not self._running and not self._busy
        reason = "Close the game before applying mods" if self._running else ""
        for b in (self.primary, self.revert):
            b.setEnabled(ok)
            b.setToolTip(reason)
        self._effect.setOpacity(0.5 if self._running else 1.0)

    # ---------- helpers ----------

    def _divider(self) -> QFrame:
        sep = QFrame(self)
        sep.setObjectName("sideSep")
        sep.setFixedHeight(1)
        return sep

    def _menu_item(self, icon_name: str, label: str) -> QPushButton:
        b = QPushButton(label, self)
        b.setObjectName("menuItem")
        b.setFixedHeight(40)
        b.setCheckable(True)
        b.setIcon(theme.icon(icon_name, 18))
        b.setIconSize(QSize(18, 18))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        return b
