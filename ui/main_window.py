"""Frameless main window: two full-height columns (sidebar / content), wired to
the real Mods/ folder; every write action runs `cznmod.py` as a subprocess.

Layout: no top bar - each column starts with its own 72px draggable header row
(app name / page tabs / "Settings"), both on the same line; the window buttons
overlay the content column's top-right corner.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

import data
import theme
from widgets.char_grid import CharGrid, ThumbLoader
from widgets.chip_bar import FilterChips, InfoRow, TabRow, Toolbar
from widgets.empty_state import EmptyState
from widgets.mod_delegate import ModListView
from widgets.sidebar import Sidebar
from widgets.title_bar import DragRow, WindowButtons

GRIP = 6          # resize zone along the window edges (columns cover the whole window)
GAME_POLL_MS = 5000


class MainWindow(QWidget):
    def __init__(self, mods_dir: str | None = None) -> None:
        super().__init__()
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("CZN MM/MI - Uncle's CZN Mod Manager / Mod Importer")
        self.setMinimumSize(880, 560)
        self.resize(1100, 700)
        # The window itself holds the startup focus: otherwise Qt focuses the first
        # tab-chain button when the window is shown and lights its focus ring. The
        # ring is reserved for Tab navigation (all buttons use Qt.TabFocus).
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        QApplication.instance().installEventFilter(self)   # resize cursor + edge press
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self._tab_nav = False      # True while the user is navigating with Tab

        self._mods_dir = mods_dir or data.DEFAULT_MODS
        self._tab = data.TABS[0]
        self._cat = "All"
        self._sort = data.SORTS[0]
        self._enabled: list[data.Mod] = []
        self._disabled: list[data.Mod] = []
        self._busy = False
        self._q: queue.Queue = queue.Queue()
        self._char_rows: list[dict] | None = None     # Char ID tab, loaded on first open
        self._char_shown: list[dict] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.side = Sidebar(self)
        root.addWidget(self.side)

        main_col = QWidget(self)
        main_col.setObjectName("mainCol")
        main_col.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cv = QVBoxLayout(main_col)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        content = QWidget(main_col)
        cvl = QVBoxLayout(content)
        cvl.setContentsMargins(theme.PAD_MAIN, 0, theme.PAD_MAIN, 10)
        cvl.setSpacing(0)
        self.tab_row = TabRow(content)
        cvl.addWidget(self.tab_row)
        cvl.addSpacing(20)
        self.toolbar = Toolbar(content)
        cvl.addWidget(self.toolbar)
        cvl.addSpacing(16)
        self.info = InfoRow(content)
        cvl.addWidget(self.info)
        cvl.addSpacing(16)
        self.view = ModListView(content)
        cvl.addWidget(self.view, 1)
        self.empty = EmptyState(content)
        self.empty.hide()
        cvl.addWidget(self.empty, 1)
        self.status = QLabel("", content)
        self.status.setObjectName("statusLine")
        self.status.setFixedHeight(20)
        self.status.setVisible(False)          # no blank band while idle
        cvl.addWidget(self.status)

        self.stack = QStackedWidget(main_col)
        self.stack.addWidget(content)
        self.settings_page = self._build_settings_page(self.stack)
        self.stack.addWidget(self.settings_page)
        self.char_page = self._build_char_page(self.stack)
        self.stack.addWidget(self.char_page)
        self.char_loader = ThumbLoader(self)
        self.char_loader.loaded.connect(self._char_thumb_ready)
        cv.addWidget(self.stack, 1)
        self.btns = WindowButtons(main_col)     # overlay pinned to the top-right corner
        root.addWidget(main_col, 1)

        # wiring
        self.tab_row.tabChanged.connect(self._set_tab)
        self.toolbar.chips.catChanged.connect(self._set_cat)
        self.toolbar.refreshClicked.connect(self.refresh)
        self.toolbar.openFolderClicked.connect(self._open_mods)
        self.info.sortChanged.connect(self._set_sort)
        self.side.applyClicked.connect(lambda: self._run_cli(["apply"], "Apply mods"))
        self.side.revertClicked.connect(self._revert_all)
        self.side.pageChanged.connect(self._set_page)
        self.view.chipClicked.connect(self._toggle_mod)
        self.view.filesDropped.connect(self._add_paths)
        self.empty.filesDropped.connect(self._add_paths)

        self.refresh()
        self._poll = QTimer(self)
        self._poll.setInterval(GAME_POLL_MS)
        self._poll.timeout.connect(self._poll_game)
        self._poll.start()
        self._drain = QTimer(self)
        self._drain.setInterval(80)
        self._drain.timeout.connect(self._drain_q)
        self._drain.start()

    # ---------- listing / filtering ----------

    def refresh(self) -> None:
        self._enabled, self._disabled = data.scan(self._mods_dir)
        self._rebuild()
        self._poll_game()
        if not self.status.isVisible() and data.game_root_changed(self._mods_dir):
            self._status("Game folder changed - press Apply mods")

    def _tab_pool(self) -> list[data.Mod]:
        if self._tab == "Disabled":
            return self._disabled
        if self._tab == "Enabled":
            return self._enabled
        return self._enabled + self._disabled      # "All" tab

    def _pool(self) -> list[data.Mod]:
        pool = self._tab_pool()
        if self._cat != "All":
            pool = [m for m in pool if m.cat == self._cat]
        return pool

    def _rebuild(self) -> None:
        cats = sorted({m.cat for m in self._tab_pool()})
        labels = cats
        if self._cat not in labels:
            self._cat = "All"
        self.toolbar.chips.set_labels(labels, self._cat)
        mods = self._pool()
        if self._sort == "Newest":
            mods = sorted(mods, key=lambda m: m.mtime, reverse=True)
        elif self._sort == "Oldest":
            mods = sorted(mods, key=lambda m: m.mtime)
        else:
            mods = sorted(mods, key=lambda m: m.name.lower())
        self.view.set_mods(mods)
        self.info.set_total(len(mods))
        empty = not mods
        self.view.setVisible(not empty)
        self.empty.setVisible(empty)
        if empty:
            if self._cat != "All":
                self.empty.set_text("No mods match this filter",
                                    "Click the chip again to show everything")
            else:
                self.empty.set_text("No mods yet",
                                    'Click "Open folder" and drop your mods in')

    def _set_tab(self, tab: str) -> None:
        self._tab = tab
        self._rebuild()

    def _set_cat(self, cat: str) -> None:
        self._cat = cat
        self._rebuild()

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self._rebuild()

    # ---------- per-mod enable / disable (status chip on the card) ----------

    def _toggle_mod(self, row: int) -> None:
        mods = self.view.mods
        if row >= len(mods):
            return
        m = mods[row]
        if m.disabled:                     # parked cards enable, live cards disable
            self._run_cli(["enable", m.action_name], f"Enable {m.name}")
        else:
            self._run_cli(["disable", m.action_name], f"Disable {m.name}")

    # ---------- adding mods ----------

    def _add_paths(self, paths: list[str]) -> None:
        copied, errors = data.add_mods(self._mods_dir, paths)
        if errors:
            self._status("; ".join(errors)[:220])
        elif copied:
            self._status(f"Added {copied} item(s) to Mods - press Apply mods to apply")
        if copied:
            self.refresh()

    def _status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))     # collapse the band when there is nothing to say

    # ---------- actions ----------

    def _revert_all(self) -> None:
        if QMessageBox.question(
                self, "Revert all mods",
                "Restore every original image in the game and move the mods into Mods\\_disabled\\?")\
                == QMessageBox.StandardButton.Yes:
            self._run_cli(["revert"], "Revert all")

    def _open_mods(self) -> None:
        os.makedirs(self._mods_dir, exist_ok=True)
        os.startfile(self._mods_dir)

    def _pick_game_dir(self) -> None:
        """Browse for the game folder (only offered while none was found)."""
        p = QFileDialog.getExistingDirectory(self, "Select the Chaos Zero Nightmare folder")
        if not p:
            return
        if data.set_game_dir(p):
            root = data.game_root() or p
            self._game_val.setText(root)
            self._game_browse.setVisible(False)
            self._status(f"Game folder set: {root}")
            self.refresh()
        else:
            QMessageBox.warning(
                self, "Game folder",
                "That folder is not a Chaos Zero Nightmare install.\n"
                "Pick the folder that contains bin\\ (bin\\appdata\\cznlive\\gameres\\manifest.ssra).")

    def _set_page(self, name: str) -> None:
        if name == "Char ID":
            self._ensure_chars()
        self.stack.setCurrentIndex({"Mods": 0, "Settings": 1, "Char ID": 2}.get(name, 0))

    def _build_char_page(self, parent: QWidget) -> QWidget:
        """Character dex: portrait grid with a search box and group chips."""
        page = QWidget(parent)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(theme.PAD_MAIN, 0, theme.PAD_MAIN, 10)
        lay.setSpacing(0)

        head = DragRow(page)
        head.setFixedHeight(theme.HEADER_H)     # same line as the app name / tabs
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Char ID", head)
        title.setObjectName("pageTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        lay.addWidget(head)
        sep = QFrame(page)
        sep.setObjectName("sideSep")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        lay.addSpacing(20)

        row = QWidget(page)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(16)
        self.char_search = QLineEdit(row)
        self.char_search.setObjectName("searchBox")
        self.char_search.setFixedSize(300, 36)
        self.char_search.setPlaceholderText("Search name or ID...")
        self.char_search.setClearButtonEnabled(True)
        self.char_search.addAction(theme.icon("search", 16, theme.TEXT_MUTED),
                                   QLineEdit.ActionPosition.LeadingPosition)
        self.char_search.textChanged.connect(self._char_filter)
        rl.addWidget(self.char_search)
        self.char_chips = FilterChips(row)
        self.char_chips.set_labels(["Playable", "Support", "Other"])
        self.char_chips.catChanged.connect(self._char_filter)
        rl.addWidget(self.char_chips, 1)
        lay.addWidget(row)
        lay.addSpacing(12)

        self.char_count = QLabel("Total 0", page)
        self.char_count.setObjectName("totalLbl")
        self.char_hint = QLabel("", page)
        self.char_hint.setObjectName("statusLine")
        self.char_hint.hide()
        info = QHBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(12)
        info.addWidget(self.char_count)
        info.addWidget(self.char_hint, 1)
        info.addStretch(1)          # pins the columns button to the right edge
        self.char_cols_btn = QPushButton("Columns: Auto", page)
        self.char_cols_btn.setObjectName("sortBtn")
        self.char_cols_btn.setFixedHeight(28)
        self.char_cols_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.char_cols_btn.setIcon(theme.icon("chevron-down", 14))
        self.char_cols_btn.setIconSize(QSize(14, 14))
        self.char_cols_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.char_cols_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.char_cols_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.char_cols_btn.clicked.connect(self._char_columns)
        info.addWidget(self.char_cols_btn)
        lay.addLayout(info)
        lay.addSpacing(12)

        self.char_grid = CharGrid(page)
        self.char_cols_btn.setText(f"Columns: {self.char_grid.cols_fixed or 'Auto'}")
        self.char_grid.cardMenuRequested.connect(self._char_menu)
        lay.addWidget(self.char_grid, 1)
        return page

    def _ensure_chars(self) -> None:
        """Load the char catalog (once) and kick off thumbnail rendering."""
        if self._char_rows is None:
            try:
                from char_catalog import load
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    self._char_rows = load()
                finally:
                    QApplication.restoreOverrideCursor()
            except Exception as e:
                self._char_rows = []
                self.char_hint.setText(f"Character list unavailable ({type(e).__name__})")
                self.char_hint.show()
            if self._char_rows and not data.game_root():
                self.char_hint.setText("Game folder not found - portraits unavailable "
                                       "(Settings > Browse...)")
                self.char_hint.show()
        self.char_loader.start(self._char_rows)
        self._char_filter()

    def _char_filter(self) -> None:
        if self._char_rows is None:
            return
        from char_catalog import match
        grp = self.char_chips.checked()          # "All" when no chip is active
        q = self.char_search.text()
        self._char_shown = [r for r in self._char_rows
                            if (grp == "All" or r["label"] == grp) and match(r, q)]
        self.char_grid.set_rows(self._char_shown)
        self.char_count.setText(f"Total {len(self._char_shown)}")

    def _char_thumb_ready(self, pid: int) -> None:
        self.char_grid.thumb_ready(pid)

    def _char_columns(self) -> None:
        menu = QMenu(self)
        for label in ["Auto"] + [str(i) for i in range(3, 11)]:
            menu.addAction(label)
        chosen = menu.exec(self.char_cols_btn.mapToGlobal(
            QPoint(0, self.char_cols_btn.height() + 4)))
        if chosen:
            self.char_cols_btn.setText(f"Columns: {chosen.text()}")
            self.char_grid.set_columns(0 if chosen.text() == "Auto" else int(chosen.text()))

    def _char_asset_dir(self, r: dict) -> str:
        """<asset root>/<ID>_<name> - the folder Export Asset writes to."""
        name = re.sub(r'[\\/:*?"<>|]', "_", r["name"] or "").strip()
        return os.path.join(data.asset_root(), f"{r['id']}_{name}" if name else str(r["id"]))

    def _char_menu(self, row: int, gpos) -> None:
        if row >= len(self.char_grid.rows):
            return
        r = self.char_grid.rows[row]
        folder = self._char_asset_dir(r)
        menu = QMenu(self)
        act_export = menu.addAction("Export Asset")
        act_locate = menu.addAction("Locate Asset")
        act_locate.setEnabled(os.path.isdir(folder))   # only after a real export
        chosen = menu.exec(gpos)
        if chosen is act_export:
            self._char_export(r, folder)
        elif chosen is act_locate:
            os.startfile(folder)

    def _char_export(self, r: dict, folder: str) -> None:
        """Background export of every image of this character (re-runs add new files)."""
        self._run_cli(["export", str(r["id"]), folder],
                      f"Export {os.path.basename(folder)}")

    def closeEvent(self, e) -> None:
        self.char_loader.stop()
        super().closeEvent(e)

    def _build_settings_page(self, parent: QWidget) -> QWidget:
        """A real settings page in the content column (no popup)."""
        page = QWidget(parent)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(theme.PAD_MAIN, 0, theme.PAD_MAIN, 10)
        lay.setSpacing(0)

        head = DragRow(page)
        head.setFixedHeight(theme.HEADER_H)     # same line as the app name / tabs
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Settings", head)
        title.setObjectName("pageTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        lay.addWidget(head)
        sep = QFrame(page)
        sep.setObjectName("sideSep")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        lay.addSpacing(24)

        root = data.game_root()
        rows = [
            ("Game folder", root or "Not found - click Browse to select the game folder"),
            ("Mods folder", self._mods_dir),
            ("Game patch", "1.0.81406"),
            ("About", "CZN MM/MI 1.0 - Uncle's CZN Mod Manager / Mod Importer - image/UI mods for Chaos Zero Nightmare"),
        ]
        body = QWidget(page)
        body.setMaximumWidth(720)          # keeps the rows from sprawling on wide windows
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self._game_val = self._game_browse = None
        for key, value in rows:
            row = QWidget(body)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(16)
            k = QLabel(key, row)
            k.setObjectName("setKey")
            k.setFixedWidth(120)
            v = QLabel(value, row)
            v.setObjectName("setVal")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setWordWrap(True)
            rl.addWidget(k)
            rl.addWidget(v, 1)
            if key == "Game folder":
                self._game_val = v
                self._game_browse = QPushButton("Browse...", row)
                self._game_browse.setObjectName("outlineBtn")
                self._game_browse.setFixedHeight(30)
                self._game_browse.setCursor(Qt.CursorShape.PointingHandCursor)
                self._game_browse.clicked.connect(self._pick_game_dir)
                self._game_browse.setVisible(not root)
                rl.addWidget(self._game_browse)
            bl.addWidget(row)
            bl.addSpacing(18)
        lay.addWidget(body)

        lay.addStretch(1)
        return page

    def _run_cli(self, args: list[str], what: str) -> None:
        if self._busy:
            return
        self._busy = True
        self.side.set_busy(True)
        self._status(f"{what}: running...")

        def worker() -> None:
            try:
                p = subprocess.Popen(data.cli(args), cwd=data.ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", creationflags=0x08000000)
                last = ""
                for line in p.stdout:
                    line = line.rstrip("\r\n")
                    if line:
                        last = line
                    self._q.put(("log", line))
                p.wait()
                self._q.put(("done", p.returncode, last))
            except Exception as e:
                self._q.put(("done", -1, f"{type(e).__name__}: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_q(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if msg[0] == "done":
                    code, last = msg[1], msg[2]
                    self._busy = False
                    self.side.set_busy(False)
                    self._status(last or f"done (exit {code})")
                    self.refresh()
        except queue.Empty:
            pass

    def _poll_game(self) -> None:
        self.side.set_game(data.game_running())

    # ---------- frameless window: resize grips + maximise state ----------

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.setFocus()

    def _zone(self, pos: QPoint) -> Qt.Edge:
        w, h = self.width(), self.height()
        edge = Qt.Edge(0)
        if pos.x() < GRIP:
            edge |= Qt.Edge.LeftEdge
        elif pos.x() >= w - GRIP:
            edge |= Qt.Edge.RightEdge
        if pos.y() < GRIP:
            edge |= Qt.Edge.TopEdge
        elif pos.y() >= h - GRIP:
            edge |= Qt.Edge.BottomEdge
        return edge

    def eventFilter(self, obj, ev) -> bool:
        # A cursor set on this window is inherited by every child widget, and mouse
        # moves over children never reach the window's own mouseMoveEvent. So the
        # resize cursor must be re-evaluated on EVERY move in the app, or a shape
        # set in a border zone leaks and sticks everywhere inside the tool.
        if ev.type() == QEvent.Type.MouseMove:
            self._update_cursor(ev.globalPosition().toPoint())
        elif ev.type() == QEvent.Type.MouseButtonPress:
            self._tab_nav = False
            if ev.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
                # the columns cover the whole window, so the edge press lands on a
                # child widget - intercept it here to start a system resize.
                # Exception: presses on the window buttons (which reach y=0) must
                # stay clicks, never a resize.
                on_btns = obj is self.btns or self.btns.isAncestorOf(obj)
                pos = self.mapFromGlobal(ev.globalPosition().toPoint())
                if self.rect().contains(pos) and not on_btns:
                    z = self._zone(pos)
                    if z:
                        self.windowHandle().startSystemResize(z)
                        return True
        elif ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Tab:
            self._tab_nav = True
        return super().eventFilter(obj, ev)

    def _focus_changed(self, old, new) -> None:
        """Focus ring is for Tab navigation only.

        Qt occasionally assigns focus to the first tab-chain button by itself
        (window activation, internal relayouts). Whenever that happens without a
        Tab press, hand the focus back to the window so no ring lights up.
        """
        if new is None or new is self or not self.isAncestorOf(new):
            return
        if self._tab_nav or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        if isinstance(new, QAbstractButton):
            new.clearFocus()      # kills the ring even while the window is inactive
            self.setFocus()

    def _update_cursor(self, global_pos: QPoint) -> None:
        shape = Qt.CursorShape.ArrowCursor
        if not self.isMaximized():
            pos = self.mapFromGlobal(global_pos)
            over_btns = self.btns.rect().contains(self.btns.mapFromGlobal(global_pos))
            if self.rect().contains(pos) and not over_btns:
                z = self._zone(pos)
                if (z & Qt.Edge.LeftEdge and z & Qt.Edge.TopEdge) or \
                   (z & Qt.Edge.RightEdge and z & Qt.Edge.BottomEdge):
                    shape = Qt.CursorShape.SizeFDiagCursor
                elif (z & Qt.Edge.RightEdge and z & Qt.Edge.TopEdge) or \
                     (z & Qt.Edge.LeftEdge and z & Qt.Edge.BottomEdge):
                    shape = Qt.CursorShape.SizeBDiagCursor
                elif z & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
                    shape = Qt.CursorShape.SizeHorCursor
                elif z & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
                    shape = Qt.CursorShape.SizeVerCursor
        if self.cursor().shape() != shape:
            self.setCursor(shape)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self.btns.set_maximized(self.isMaximized())
