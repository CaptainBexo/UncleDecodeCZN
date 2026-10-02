"""Character dex grid for the Char ID tab: QListView (IconMode) + one delegate
painting portrait thumbs, name and id.

Thumbs are rendered from the game pack once (background daemon thread) into
APP/cache/char_thumbs/<id>.png and reused on every later run; the cache is
dropped automatically when the name table changes (game patch).
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QObject, QPoint, QRectF,
                            QSettings, QSize, Qt, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPixmap,
                           QStandardItem, QStandardItemModel)
from PySide6.QtWidgets import QFrame, QListView, QStyledItemDelegate

import data                       # noqa: F401  (importing it puts scripts/ on sys.path)
import theme
from widgets.mod_delegate import blend

THUMB_CACHE = os.path.join(data.APP, "cache", "char_thumbs")
THUMB_H = 300                     # cached png height (half crops are 260x460)
BODY_H = 58                       # name + id under the image
CARD_MIN_W = 150
HOVER_MS = 130
BADGE_COLORS = {"Playable": theme.ACCENT, "Support": theme.WARNING, "Other": theme.TEXT_MUTED}


def thumb_png(pid: int) -> str:
    return os.path.join(THUMB_CACHE, f"{pid}.png")


def _invalidate_if_stale() -> None:
    """Drop cached thumbs when the name table changed (game patch)."""
    from char_catalog import NAMES_PATH
    st = os.stat(NAMES_PATH)
    key = f"{st.st_mtime_ns}:{st.st_size}"
    marker = os.path.join(THUMB_CACHE, "_src.txt")
    try:
        old = open(marker, encoding="utf-8").read().strip()
    except OSError:
        old = ""
    if old == key:
        return
    for fn in os.listdir(THUMB_CACHE):
        if fn.endswith(".png"):
            try:
                os.remove(os.path.join(THUMB_CACHE, fn))
            except OSError:
                pass
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(key)


class ThumbLoader(QObject):
    """Decodes missing char thumbs from the game pack in a daemon thread."""

    loaded = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self, rows: list[dict]) -> None:
        if self._t and self._t.is_alive():
            return
        todo = [r for r in rows if r["thumb"] and not os.path.exists(thumb_png(r["id"]))]
        if not todo:
            return
        self._t = threading.Thread(target=self._run, args=(todo,), daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self, todo: list[dict]) -> None:
        try:
            from PIL import Image
            from czn_pack import Pack
            from sct2 import decode
            os.makedirs(THUMB_CACHE, exist_ok=True)
            _invalidate_if_stale()
            pack = Pack()
        except Exception:
            return                          # no game / no names table - placeholders stay
        for r in todo:
            if self._stop.is_set():
                return
            try:
                im, _ = decode(pack.extract(r["thumb"]))
                h = THUMB_H
                w = max(1, round(im.width * h / im.height))
                im.convert("RGBA").resize((w, h), Image.LANCZOS).save(thumb_png(r["id"]))
                self.loaded.emit(r["id"])
            except Exception:
                continue


class CharDelegate(QStyledItemDelegate):
    def __init__(self, view: QListView) -> None:
        super().__init__(view)
        self._view = view
        self._pix: dict[tuple, QPixmap] = {}
        self._hover = -1
        self._prev = -1
        self._v = 0.0
        base = QFont("Inter")
        self.f_title = QFont(base)
        self.f_title.setPixelSize(14)
        self.f_title.setWeight(QFont.Weight.DemiBold)
        self.f_small = QFont(base)
        self.f_small.setPixelSize(theme.F_SMALL)

    # ---- hover fade (same pattern as the mod card delegate) ----

    def set_hover(self, row: int) -> None:
        if row == self._hover:
            return
        self._prev, self._hover = self._hover, row
        self._v = 0.0
        anim = QVariantAnimation(self._view)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(HOVER_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._tick)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _tick(self, v) -> None:
        self._v = float(v)
        self._view.viewport().update()

    def _hover_t(self, row: int) -> float:
        if row == self._hover:
            return self._v
        if row == self._prev:
            return 1.0 - self._v
        return 0.0

    # ---- scaled thumb cache (negative entries cleared by thumb_ready) ----

    def thumb(self, pid: int, w: int, h: int, dpr: float) -> QPixmap | None:
        key = (pid, w, h, dpr)
        if key in self._pix:
            pm = self._pix[key]
            return pm if not pm.isNull() else None
        src = QPixmap(thumb_png(pid))
        if src.isNull():
            self._pix[key] = QPixmap()
            return None
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = src.scaled(pm.size(), Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((pm.width() - scaled.width()) // 2,
                     (pm.height() - scaled.height()) // 2, scaled)
        p.end()
        self._pix[key] = pm
        return pm

    def thumb_ready(self, pid: int) -> None:
        for k in [k for k in self._pix if k[0] == pid]:
            del self._pix[k]
        self._view.viewport().update()

    def sizeHint(self, opt, idx) -> QSize:
        return self._view.gridSize()

    # ---- painting ----

    def paint(self, p: QPainter, opt, idx) -> None:
        rows = self._view.rows
        if idx.row() >= len(rows):
            return
        r = rows[idx.row()]
        rect = opt.rect
        w = rect.width() - theme.GRID_GAP
        h = rect.height() - theme.GRID_GAP
        card = QRectF(rect.x(), rect.y(), w, h)
        t = self._hover_t(idx.row())

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blend(theme.BG_CARD, theme.BG_CARD_HOVER, t))
        p.drawRoundedRect(card, theme.R_CARD, theme.R_CARD)

        # portrait, fit inside the image area (panel behind keeps square icons
        # looking deliberate next to full-bleed portrait crops)
        img_h = h - BODY_H
        p.setBrush(QColor(theme.BG_CHIP))
        p.drawRoundedRect(QRectF(card.x(), card.y(), w, img_h), theme.R_CARD, theme.R_CARD)
        pm = self.thumb(r["id"], int(w), int(img_h), self._view.devicePixelRatioF())
        if pm is not None:
            p.drawPixmap(int(card.x()), int(card.y()), pm)
        else:
            p.setFont(self.f_title)
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(QRectF(card.x(), card.y(), w, img_h), Qt.AlignmentFlag.AlignCenter,
                       (r["name"] or "?")[:1].upper())

        # group badge, top-left of the image (outlined pill like the mod cards)
        fm_small = QFontMetrics(self.f_small)
        bw = fm_small.horizontalAdvance(r["label"]) + 18
        brect = QRectF(card.x() + 8, card.y() + 8, bw, 20)
        p.setBrush(QColor(theme.BG_APP))
        p.setPen(QColor(BADGE_COLORS.get(r["label"], theme.TEXT_MUTED)))
        p.drawRoundedRect(brect, 10, 10)
        p.setFont(self.f_small)
        p.drawText(brect, Qt.AlignmentFlag.AlignCenter, r["label"])

        # name + id (no-name cards already say "ID <n>" as the title)
        fm_title = QFontMetrics(self.f_title)
        name = r["name"] or f"ID {r['id']}"
        p.setFont(self.f_title)
        p.setPen(QColor(theme.TEXT_STRONG))
        p.drawText(QRectF(card.x() + 10, card.y() + img_h + 8, w - 20, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft,
                   fm_title.elidedText(name, Qt.TextElideMode.ElideRight, int(w) - 20))
        sub = str(r["id"]) if (r["name"] or r["code"]) else ""
        if r["code"] and r["name"] != r["code"]:
            sub = f"{r['id']} · {r['code']}"
        p.setFont(self.f_small)
        p.setPen(QColor(theme.TEXT_MUTED))
        p.drawText(QRectF(card.x() + 10, card.y() + img_h + 8 + fm_title.height(), w - 20,
                          fm_small.height()),
                   Qt.AlignmentFlag.AlignLeft,
                   fm_small.elidedText(sub, Qt.TextElideMode.ElideRight, int(w) - 20))
        p.restore()


class CharGrid(QListView):
    """IconMode grid of character cards; the cell adapts to the viewport width."""

    cardMenuRequested = Signal(int, QPoint)     # row, global position

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardGrid")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.card_delegate = CharDelegate(self)
        self.setItemDelegate(self.card_delegate)
        self.rows: list[dict] = []
        # 0 = adaptive columns; 3..10 = fixed count (persisted across runs)
        self.cols_fixed = int(QSettings("CZN_MMMI", "tool").value("char_columns", 0) or 0)
        self.item_model = QStandardItemModel(0, 1, self)
        self.setModel(self.item_model)

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.card_delegate.set_hover(-1)
        self.item_model.clear()
        for r in rows:
            item = QStandardItem(str(r["id"]))
            item.setEditable(False)
            self.item_model.appendRow(item)
        self.relayout()
        self.viewport().update()

    def thumb_ready(self, pid: int) -> None:
        self.card_delegate.thumb_ready(pid)

    def set_columns(self, n: int) -> None:
        """0 = adaptive (auto); 3..10 = fixed column count (persisted)."""
        self.cols_fixed = n
        QSettings("CZN_MMMI", "tool").setValue("char_columns", n)
        self.relayout()

    def relayout(self) -> None:
        # same rule as the mod grid: reserve the scrollbar + 2 px slack so the
        # column count cannot ping-pong with scrollbar visibility.
        vw = self.width() - theme.SCROLLBAR_W - 2
        if self.cols_fixed:
            # ponytail: 60px/card floor keeps a big column count renderable on a
            # small window; switch to a min-width + h-scroll if cards matter more
            n = max(2, min(self.cols_fixed, max(2, vw // 60)))
        else:
            n = max(3, (vw + theme.GRID_GAP) // (CARD_MIN_W + theme.GRID_GAP))
            while n > 3 and (vw - n * theme.GRID_GAP) // n < CARD_MIN_W:
                n -= 1
        w = (vw - n * theme.GRID_GAP) // n
        h = round(w * 1.77) + BODY_H            # half crops are 260x460
        cell = QSize(w + theme.GRID_GAP, h + theme.GRID_GAP)
        if cell != self.gridSize():
            self.setGridSize(cell)
            self.doItemsLayout()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.relayout()

    def mouseMoveEvent(self, e) -> None:
        super().mouseMoveEvent(e)
        idx = self.indexAt(e.position().toPoint())
        self.card_delegate.set_hover(idx.row() if idx.isValid() else -1)

    def contextMenuEvent(self, e) -> None:
        idx = self.indexAt(e.pos())
        if idx.isValid():
            self.cardMenuRequested.emit(idx.row(), e.globalPos())
            e.accept()
            return
        super().contextMenuEvent(e)

    def leaveEvent(self, e) -> None:
        super().leaveEvent(e)
        self.card_delegate.set_hover(-1)
