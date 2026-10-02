"""Mouse-following floating tooltip that replaces Qt's native QToolTip.

Qt's tooltip is ugly next to the dark theme and vanishes on the first pixel of
mouse movement. This one: a frameless always-on-top label, shown from an app-wide
event filter (the native ToolTip event is swallowed), placed next to the cursor,
then kept glued to the pointer by a small poll timer. It hides once the cursor
leaves the described control, or on click / wheel / key press / window deactivate.

Text lookup mirrors Qt: the widget's own toolTip(), or the ToolTipRole of the
item under the cursor for item views (the painted card grids).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QHelpEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel
from shiboken6 import isValid

OFF_X, OFF_Y = 14, 20       # cursor gap; flips to the other side near screen edges
POLL_MS = 16                # ~60 fps while following the pointer
EASE = 0.45                 # glide: 1.0 = glued, lower = more trail
RADIUS = 8


class FloatTip(QLabel):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("floatTip")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setMaximumWidth(340)

    def paintEvent(self, ev) -> None:
        # QSS backgrounds do not paint on this translucent top-level label - draw the
        # bubble by hand (colour/radius/inset live here; the QSS only carries text)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(26, 26, 30, 242))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                          RADIUS, RADIUS)
        p.end()
        super().paintEvent(ev)

    def target_pos(self, gp: QPoint) -> QPoint:
        """Cursor + offset, flipped at screen edges (pure math - no window move)."""
        x, y = gp.x() + OFF_X, gp.y() + OFF_Y
        scr = QApplication.screenAt(gp) or QApplication.primaryScreen()
        a = scr.availableGeometry()
        if x + self.width() > a.right():
            x = gp.x() - self.width() - OFF_X
        if y + self.height() > a.bottom():
            y = gp.y() - self.height() - OFF_Y
        return QPoint(max(a.left(), x), max(a.top(), y))

    def place(self, gp: QPoint) -> None:
        self.adjustSize()          # once per show - never per follow frame
        self.move(self.target_pos(gp))


def text_at(gp: QPoint) -> str:
    """Tooltip text under the cursor (widget tip, an item view's ToolTipRole, or a
    delegate region tip - painted buttons like the card's eye describe themselves)."""
    w = QApplication.widgetAt(gp)
    while w is not None:
        if isinstance(w, QAbstractItemView):
            pos = w.viewport().mapFromGlobal(gp)
            idx = w.indexAt(pos)
            if idx.isValid():
                hook = getattr(w.itemDelegate(), "tooltip_at", None)
                tip = hook(idx, QPointF(pos)) if hook else ""
                if not tip:
                    tip = idx.data(Qt.ItemDataRole.ToolTipRole)
                if tip:
                    return str(tip)
            return ""
        tip = w.toolTip()
        if tip:
            return tip
        w = w.parentWidget()
    return ""


class TooltipController(QObject):
    """App-wide: one per QApplication (install() is idempotent)."""

    _active = None

    @classmethod
    def install(cls, app: QApplication) -> "TooltipController":
        if cls._active is None:
            cls._active = cls(app)
        return cls._active

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.popup = FloatTip()
        self._gp = QPoint()
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.setTimerType(Qt.TimerType.PreciseTimer)
        self._poll.timeout.connect(self._tick)
        app.installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:
        # the popup can outlive its C++ side during interpreter/app teardown
        # (Qt destroys top-level widgets in ~QApplication) - every entry point
        # must tolerate that instead of cascading RuntimeErrors.
        if not isValid(self.popup):
            return False
        t = ev.type()
        if t == QEvent.Type.ToolTip:
            if isinstance(ev, QHelpEvent):
                self._on_tip(ev.globalPos())
            return True                      # swallowed: the native tip never shows
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel,
                 QEvent.Type.KeyPress, QEvent.Type.WindowDeactivate):
            self._hide()
        return False

    # ---- internals ----------------------------------------------------

    def _on_tip(self, gp: QPoint) -> None:
        text = text_at(gp)
        if not text:
            self._hide()
            return
        self._gp = gp
        self.popup.setText(text)
        self.popup.place(gp)
        self.popup.show()
        self._poll.start()

    def _tick(self) -> None:
        if not isValid(self.popup):
            self._poll.stop()
            return
        gp = QCursor.pos()
        if gp != self._gp:
            self._gp = gp
            if text_at(gp) != self.popup.text():
                self._hide()                     # left the described control
                return
        want = self.popup.target_pos(gp)
        pos = self.popup.pos()
        dx, dy = want.x() - pos.x(), want.y() - pos.y()
        if abs(dx) + abs(dy) <= 2:
            if dx or dy:
                self.popup.move(want)
            return
        self.popup.move(round(pos.x() + dx * EASE), round(pos.y() + dy * EASE))

    def _hide(self) -> None:
        self._poll.stop()
        if isValid(self.popup):
            self.popup.hide()
