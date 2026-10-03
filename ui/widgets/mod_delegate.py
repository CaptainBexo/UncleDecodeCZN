"""Card grid: one delegate paints every card; the view is a plain QListView (IconMode).

No QWidget per card - the delegate caches scaled, top-rounded banner pixmaps (the
char's portrait thumb by default, the mod's own PNG while hovered) and paints straight
onto the viewport. Two painted buttons are clickable: the status chip near the bottom
(toggle enable/disable) and the eye button on the banner (preview in the Viewer dock).
"""
from __future__ import annotations

import os

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QModelIndex, QRectF,
                            QSize, Qt, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPixmap, QStandardItem, QStandardItemModel)
from PySide6.QtWidgets import QFrame, QListView, QStyledItemDelegate

import data
import theme
from widgets.empty_state import url_paths

BANNER_RATIO = 9 / 16
BODY_H = 100          # title(2 lines) + one bottom row (target path + status chip)
HOVER_MS = 130        # spec: 120-150 ms hover transition

STATUS_COLORS = {
    "ok": (theme.ACCENT_SOFT_BG, theme.ACCENT_SOFT_TEXT),
    "pending": (theme.BG_CHIP, theme.WARNING),
    "error": (theme.BG_CHIP, theme.DANGER),
    "off": (theme.BG_CHIP, theme.TEXT_MUTED),
}

STATUS_TIPS = {
    "ok": "Click the chip to disable: reverts the mod and parks it in Mods/_disabled",
    "pending": "Not applied yet - press Apply mods",
    "error": "The last apply failed - check the status line",
    "off": "Click the chip to enable: re-applies the mod",
}


def blend(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def wrap_two(fm: QFontMetrics, text: str, width: int) -> tuple[str, str]:
    """Greedy wrap to at most two lines; the second line is elided right.
    A single first word wider than the line gets a middle elide instead, so long
    filenames still show both their beginning and their extension."""
    words = text.split()
    line1 = ""
    while words:
        cand = (line1 + " " + words[0]).strip()
        if fm.horizontalAdvance(cand) > width:
            if not line1:
                return fm.elidedText(words[0], Qt.TextElideMode.ElideMiddle, width), ""
            break
        line1 = cand
        words.pop(0)
    rest = " ".join(words)
    return line1, (fm.elidedText(rest, Qt.TextElideMode.ElideRight, width) if rest else "")


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view: QListView) -> None:
        super().__init__(view)
        self._view = view
        self._thumbs: dict[tuple[int, int, str, float], QPixmap] = {}
        self.chip_hit: dict[int, QRectF] = {}
        self.eye_hit: dict[int, QRectF] = {}
        self._hover = -1
        self._prev = -1
        self._v = 0.0
        base = QFont("Inter")
        self.f_title = QFont(base)
        self.f_title.setPixelSize(theme.F_CARD)
        self.f_title.setWeight(QFont.Weight.DemiBold)   # real SemiBold face
        self.f_desc = QFont(base)
        self.f_desc.setPixelSize(13)
        self.f_small = QFont(base)
        self.f_small.setPixelSize(theme.F_SMALL)
        self.f_small.setWeight(QFont.Weight.DemiBold)

    # ---- hover fade (QVariantAnimation for the self-painted part) ----

    def tooltip_at(self, idx: QModelIndex, pos) -> str:
        """Region tooltip (the float_tip hook): only the eye button describes itself;
        everywhere else the item's own tooltip (status action) applies."""
        r = self.eye_hit.get(idx.row())
        return "Preview in Viewer" if r and r.contains(pos) else ""

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

    # ---- cached banner pixmap: char portrait by default, the mod's own PNG on hover ----

    def _src_tag(self, mod: data.Mod, hover: bool) -> str:
        """Cache-key tag for the cover source (so two mods sharing a banner, or one
        with a char thumb and one without, never collide in the pixmap cache)."""
        if not hover:
            pid = data.char_id_in(mod.desc)
            if pid and os.path.exists(os.path.join(data.CHAR_THUMB_DIR, f"{pid}.png")):
                return f"char:{pid}"
        return mod.banner or f"hue{mod.hue}"

    def _source(self, mod: data.Mod, hover: bool) -> QPixmap:
        """Default cover = the char portrait thumb (same image as the Char ID tab);
        sweeping the card flips it to the mod's own image."""
        tag = self._src_tag(mod, hover)
        if tag.startswith("char:"):
            pm = QPixmap(os.path.join(data.CHAR_THUMB_DIR, f"{tag[5:]}.png"))
            if not pm.isNull():
                return pm
        return QPixmap(mod.banner) if mod.banner else QPixmap()

    def clear_thumbs(self) -> None:
        self._thumbs.clear()

    def _thumb(self, w: int, h: int, mod: data.Mod, dpr: float, hover: bool = False) -> QPixmap:
        key = (w, h, self._src_tag(mod, hover), dpr)
        pm = self._thumbs.get(key)
        if pm is not None:
            return pm
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)     # corners outside the rounded clip stay clean
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)   # union of both subpaths, not xor
        path.addRoundedRect(QRectF(0, 0, w, h), theme.R_CARD, theme.R_CARD)
        path.addRect(QRectF(0, theme.R_CARD, w, h - theme.R_CARD))
        p.setClipPath(path)
        if hover:
            # opaque backing: the hover image REPLACES the cover - transparent
            # areas of the mod png must not let the portrait bleed through
            p.fillRect(QRectF(0, 0, w, h), QColor(theme.BG_CARD))
        src = self._source(mod, hover)
        if not src.isNull():
            scaled = src.scaled(pm.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(0, 0, scaled, (scaled.width() - pm.width()) // 2,
                         (scaled.height() - pm.height()) // 2, pm.width(), pm.height())
        else:
            grad = QLinearGradient(0, 0, w * 0.5, h)
            grad.setColorAt(0.0, QColor.fromHsv(mod.hue, 80, 68))
            grad.setColorAt(1.0, QColor.fromHsv((mod.hue + 40) % 360, 130, 118))
            p.fillRect(QRectF(0, 0, w, h), grad)
        p.end()
        self._thumbs[key] = pm
        return pm

    def sizeHint(self, opt, idx) -> QSize:
        # every item fills its grid cell so the painted card rect == cell - gap
        return self._view.gridSize()

    # ---- painting ----

    def paint(self, p: QPainter, opt, idx: QModelIndex) -> None:
        mods = self._view.mods
        if idx.row() >= len(mods):
            return
        m = mods[idx.row()]
        r = opt.rect
        w = r.width() - theme.GRID_GAP
        h = r.height() - theme.GRID_GAP
        card = QRectF(r.x(), r.y(), w, h)
        t = self._hover_t(idx.row())

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # card background (hover: slightly lighter only - no scale, no shadow)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blend(theme.BG_CARD, theme.BG_CARD_HOVER, t))
        p.drawRoundedRect(card, theme.R_CARD, theme.R_CARD)

        # banner (16:9, top corners follow the card radius); hovering cross-fades
        # from the char portrait to the mod's own image
        bh = round(w * BANNER_RATIO)
        banner = QRectF(card.x(), card.y(), w, bh)
        dpr = self._view.devicePixelRatioF()
        p.drawPixmap(banner.toRect(), self._thumb(w, bh, m, dpr, hover=False))
        if t > 0.001:
            p.setOpacity(t)
            p.drawPixmap(banner.toRect(), self._thumb(w, bh, m, dpr, hover=True))
            p.setOpacity(1.0)

        fm_small = QFontMetrics(self.f_small)

        # category badge, top-right on the banner
        text = m.cat
        bw = fm_small.horizontalAdvance(text) + 22
        brect = QRectF(banner.right() - 12 - bw, banner.top() + 12, bw, 22)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(brect, 11, 11)
        p.setFont(self.f_small)
        p.setPen(QColor(theme.TEXT_STRONG))
        p.drawText(brect, Qt.AlignmentFlag.AlignCenter, text)

        # eye button, top-left on the banner: preview this mod in the Viewer dock
        eye = QRectF(banner.left() + 12, banner.top() + 12, 30, 30)
        self.eye_hit[idx.row()] = eye
        p.setBrush(QColor(0, 0, 0, 120))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(eye, 8, 8)
        p.drawPixmap(QRectF(eye.center().x() - 9, eye.center().y() - 9, 18, 18).toRect(),
                     theme.icon_pixmap("eye", 18, theme.TEXT_STRONG))

        # images/date pill overlapping the banner's bottom edge, left
        text = f"{m.meta} · {m.date}"
        pw = fm_small.horizontalAdvance(text) + 20
        prect = QRectF(card.x() + 12, banner.bottom() - 11, pw, 22)
        p.setBrush(QColor(theme.BG_APP))
        p.setPen(QColor(theme.ACCENT))
        p.drawRoundedRect(prect, 11, 11)
        p.drawText(prect, Qt.AlignmentFlag.AlignCenter, text)

        # title (16px bold white, max 2 lines)
        fm_title = QFontMetrics(self.f_title)
        l1, l2 = wrap_two(fm_title, m.name, int(w) - 24)
        ty = banner.bottom() + 14
        p.setFont(self.f_title)
        p.setPen(QColor(theme.TEXT_STRONG))
        p.drawText(QRectF(card.x() + 12, ty, w - 24, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft, l1)
        if l2:
            p.drawText(QRectF(card.x() + 12, ty + fm_title.height(), w - 24, fm_title.height()),
                       Qt.AlignmentFlag.AlignLeft, l2)

        # bottom row: target path (left, middle-elided) + status chip (right,
        # clickable) share one line
        label = data.STATUS_TXT[m.status]
        cw = fm_small.horizontalAdvance(label) + 22
        ry = card.bottom() - 10 - 22
        crect = QRectF(card.right() - 12 - cw, ry, cw, 22)
        self.chip_hit[idx.row()] = crect

        fm_desc = QFontMetrics(self.f_desc)
        dw = max(0, int(w) - 24 - cw - 8)
        p.setFont(self.f_desc)
        p.setPen(QColor(theme.TEXT_MUTED))
        p.drawText(QRectF(card.x() + 12, ry, dw, 22), Qt.AlignmentFlag.AlignVCenter,
                   fm_desc.elidedText(m.desc, Qt.TextElideMode.ElideMiddle, dw))

        bg, fg = STATUS_COLORS[m.status]
        p.setBrush(QColor(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(crect, 6, 6)
        p.setFont(self.f_small)
        p.setPen(QColor(fg))
        p.drawText(crect, Qt.AlignmentFlag.AlignCenter, label)

        p.restore()


class ModListView(QListView):
    """IconMode grid; the card width adapts to the viewport, gap fixed at 16 px."""

    chipClicked = Signal(int)     # row whose status chip was clicked
    previewClicked = Signal(int)  # row whose eye button was clicked
    filesDropped = Signal(list)   # file/folder paths dropped onto the grid

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardGrid")
        self.card_min_w = theme.CARD_MIN_W   # slider target; relayout() derives the cells
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.card_delegate = CardDelegate(self)
        self.setItemDelegate(self.card_delegate)
        self.mods: list[data.Mod] = []
        self.item_model = QStandardItemModel(0, 1, self)
        self.setModel(self.item_model)

    # ---- drag & drop (adding mods) ----

    def dragEnterEvent(self, e) -> None:
        if url_paths(e.mimeData()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if url_paths(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = url_paths(e.mimeData())
        if paths:
            e.acceptProposedAction()
            self.filesDropped.emit(paths)

    def set_mods(self, mods: list[data.Mod]) -> None:
        """Replace the card list (title role only; the delegate paints the rest)."""
        self.mods = mods
        self.card_delegate.chip_hit.clear()
        self.card_delegate.eye_hit.clear()
        self.card_delegate.clear_thumbs()
        self.card_delegate.set_hover(-1)
        self.item_model.clear()
        for m in mods:
            item = QStandardItem(m.name)
            item.setEditable(False)
            item.setToolTip(STATUS_TIPS[m.status])   # status action only - no file paths
            self.item_model.appendRow(item)
        self.relayout()

    def relayout(self) -> None:
        # Reserve the scrollbar width and 2 px slack: the cell size must NOT depend
        # on the scrollbar being visible, or toggling it flips the column count and
        # the two states ping-pong forever (maximize = elements shaking).
        vw = self.width() - theme.SCROLLBAR_W - 2
        n = max(2, (vw + theme.GRID_GAP) // (self.card_min_w + theme.GRID_GAP))
        while n > 2 and (vw - n * theme.GRID_GAP) // n < self.card_min_w:
            n -= 1
        w = (vw - n * theme.GRID_GAP) // n
        h = round(w * BANNER_RATIO) + BODY_H
        cell = QSize(w + theme.GRID_GAP, h + theme.GRID_GAP)
        if cell != self.gridSize():
            self.setGridSize(cell)
            self.doItemsLayout()      # re-query sizeHint (uniform-item cache)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.relayout()

    def set_card_min_w(self, w: int) -> None:
        """Card-size slider target: minimum card width - column count (and so the
        actual card size) follows from it."""
        w = max(120, min(480, int(w)))
        if w != self.card_min_w:
            self.card_min_w = w
            self.relayout()

    def _chip_at(self, pos) -> int:
        idx = self.indexAt(pos.toPoint())
        if not idx.isValid():
            return -1
        r = self.card_delegate.chip_hit.get(idx.row())
        return idx.row() if r and r.contains(pos) else -1

    def _eye_at(self, pos) -> int:
        idx = self.indexAt(pos.toPoint())
        if not idx.isValid():
            return -1
        r = self.card_delegate.eye_hit.get(idx.row())
        return idx.row() if r and r.contains(pos) else -1

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            row = self._eye_at(e.position())
            if row >= 0:
                self.previewClicked.emit(row)
                return
            row = self._chip_at(e.position())
            if row >= 0:
                self.chipClicked.emit(row)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        super().mouseMoveEvent(e)
        idx = self.indexAt(e.position().toPoint())
        self.card_delegate.set_hover(idx.row() if idx.isValid() else -1)
        over = self._chip_at(e.position()) >= 0 or self._eye_at(e.position()) >= 0
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over
                                  else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, e) -> None:
        super().leaveEvent(e)
        self.card_delegate.set_hover(-1)
