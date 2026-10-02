"""Title tabs, the content toolbar (filter chips + actions), and the info row.

Toolbar row = 44px: filter chips left; refresh icon + "Open folder" right.
Info row: "Total N" left, sort dropdown right.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QWidget)

import data
import theme
from widgets.title_bar import DragRow

TOOLBAR_H = 44
CHIP_H = 36
ACTION_H = 36


class TabRow(DragRow):
    """72px page-tab row; its empty right side doubles as a window drag area."""

    tabChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.HEADER_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for label in data.TABS:
            b = QPushButton(label, self)
            b.setObjectName("tabBtn")
            b.setCheckable(True)
            b.setFixedHeight(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.setToolTip({"All": "Every mod, including disabled ones",
                          "Enabled": "Mods currently applied to the game",
                          "Disabled": "Mods parked in Mods/_disabled"}.get(label, ""))
            self.group.addButton(b)
            lay.addWidget(b)
        lay.addStretch(1)
        self.group.buttons()[0].setChecked(True)
        self.group.buttonClicked.connect(lambda b: self.tabChanged.emit(b.text()))


class FilterChips(QWidget):
    """Category pills: click one to filter, click it again to clear the filter."""

    catChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._building = False
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)     # allows clicking the active chip to clear
        self.group.buttonToggled.connect(self._toggled)
        self.lay.addStretch(1)
        self.set_labels([])

    def _toggled(self, btn: QPushButton, on: bool) -> None:
        if self._building:
            return
        if on:
            for b in self.group.buttons():
                if b is not btn and b.isChecked():
                    b.setChecked(False)
            self.catChanged.emit(btn.text())
        elif not any(b.isChecked() for b in self.group.buttons()):
            self.catChanged.emit("All")

    def set_labels(self, labels: list[str], checked: str = "All",
                   tip: str = "Filter - click again to clear") -> None:
        self._building = True
        for b in self.group.buttons():
            self.group.removeButton(b)
            self.lay.removeWidget(b)
            # deleteLater alone leaves the stale button visible (painted in the gap)
            # until the event loop processes the deferred delete - drop it now.
            b.setParent(None)
            b.deleteLater()
        for i, label in enumerate(labels):
            chip = QPushButton(label, self)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setFixedHeight(CHIP_H)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(tip)
            # Chips are recreated on every rebuild; a focusable recreated widget
            # makes Qt shuffle focus between chips (ring lights up by itself).
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.group.addButton(chip)
            self.lay.insertWidget(i, chip)
            if label == checked:
                chip.setChecked(True)
        self._building = False

    def checked(self) -> str:
        for b in self.group.buttons():
            if b.isChecked():
                return b.text()
        return "All"

    @property
    def buttons(self) -> list[QPushButton]:
        return self.group.buttons()


class Toolbar(QWidget):
    """44px row: filter chips on the left; refresh + Open folder on the right."""

    refreshClicked = Signal()
    openFolderClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TOOLBAR_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.chips = FilterChips(self)
        lay.addWidget(self.chips, 1)

        self.refresh = QPushButton(self)
        self.refresh.setObjectName("iconBtn")
        self.refresh.setFixedSize(36, ACTION_H)
        self.refresh.setIcon(theme.icon("refresh", 18, active=theme.TEXT_STRONG))
        self.refresh.setIconSize(QSize(18, 18))
        self.refresh.setToolTip("Rescan mods")
        self.refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.refresh.clicked.connect(self.refreshClicked)
        lay.addWidget(self.refresh)

        self.open_folder = QPushButton("Open folder", self)
        self.open_folder.setObjectName("outlineBtn")
        self.open_folder.setFixedHeight(ACTION_H)
        self.open_folder.setToolTip("Show the Mods folder in File Explorer")
        self.open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.open_folder.clicked.connect(self.openFolderClicked)
        lay.addWidget(self.open_folder)


class InfoRow(QWidget):
    """Left: total count. Right: sort dropdown."""

    sortChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.total = QLabel("Total 0", self)
        self.total.setObjectName("totalLbl")
        lay.addWidget(self.total)
        lay.addStretch(1)

        self.sort_btn = QPushButton(data.SORTS[0], self)
        self.sort_btn.setObjectName("sortBtn")
        self.sort_btn.setFixedHeight(28)
        self.sort_btn.setToolTip("Sort the cards")
        self.sort_btn.setIcon(theme.icon("chevron-down", 14))
        self.sort_btn.setIconSize(QSize(14, 14))
        self.sort_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # icon on the right
        self.sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.sort_btn.clicked.connect(self._show_menu)
        lay.addWidget(self.sort_btn)

    def set_total(self, n: int) -> None:
        self.total.setText(f"Total {n}")

    def _show_menu(self) -> None:
        menu = QMenu(self)
        for label in data.SORTS:
            menu.addAction(label)
        chosen = menu.exec(self.sort_btn.mapToGlobal(
            QPoint(0, self.sort_btn.height() + 4)))
        if chosen:
            self.sort_btn.setText(chosen.text())
            self.sortChanged.emit(chosen.text())
