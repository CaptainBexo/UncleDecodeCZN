"""Design tokens, generated QSS, local fonts and SVG icon helpers.

Fonts: three STATIC Inter faces (Regular/Medium/SemiBold) load through
QFontDatabase, so font-weight in the QSS resolves to a real face - never to
synthesized bold.
"""
from __future__ import annotations

import os
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "assets", "icons")
FONT_DIR = os.path.join(HERE, "assets", "fonts")
FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf")

# ---- palette (spec tokens) ----
BG_SIDE = "#101010"             # sidebar column
BG_MAIN = "#161616"             # content column
BG_APP = BG_MAIN                # alias for painted surfaces on the content side
BG_CARD = "#232323"
BG_CARD_HOVER = "#2C2C2C"
BG_CHIP = "#2B2B2B"
BG_CHIP_HOVER = "#333333"
BG_SELECTED = "#2A2A2A"
BG_MENU_HOVER = "#313131"       # hover is a lighter shade of selected
DIVIDER = "rgba(255,255,255,0.08)"
TEXT_STRONG = "#FFFFFF"
TEXT = "#D6D6D6"
TEXT_MUTED = "#8C8C8C"
TEXT_GHOST = "#BDBDBD"          # ghost button label
TEXT_TOTAL = "#9A9A9A"          # "Total N" / sort label
TAB_OFF = "#7A7A7A"             # unselected page tab
ACCENT = "#3D6AFF"
ACCENT_SOFT_BG = "#E6ECFF"
ACCENT_SOFT_TEXT = "#3D6AFF"
ACCENT_WASH = "rgba(61,106,255,0.06)"   # drop-target wash
DASH = "rgba(255,255,255,0.12)"         # empty-state dashed frame
OUTLINE_BORDER = "rgba(255,255,255,0.18)"
HOVER_WASH = "rgba(255,255,255,0.06)"   # ghost button hover
WARNING = "#F0B232"
DANGER = "#F23F42"
GAME_OFF = "#8C8C8C"            # status dot: game closed
GAME_ON = "#3ECF6A"             # status dot: game running
SCROLL_THUMB = "#3A3A3A"
INK = "#141414"                 # text color on white surfaces

# ---- type scale ----
F_APP = 18                       # app name in the sidebar (600)
F_PAGE = 22                      # page title tabs (600)
F_BTN = 14                       # buttons + menu rows (500)
F_CHIP = 13                      # filter chips / total / sort (400)
F_CARD = 16                      # card title (600)
F_BODY = 14                      # base
F_SMALL = 12                     # captions, badges

# ---- metrics ----
R_CARD = 16
R_MENU = 8
R_PRIMARY = 10                   # primary button
HEADER_H = 72                    # app-name row == tab row (top line of both columns)
SIDEBAR_W = 240
PAD_SIDE = 16                    # sidebar horizontal padding
PAD_MAIN = 32                    # content horizontal padding
CARD_MIN_W = 232
GRID_GAP = 16
SCROLLBAR_W = 8


def qss() -> str:
    """Single stylesheet built from the tokens above (applied once, in apply())."""
    return f"""
QWidget {{ color: {TEXT}; font-size: {F_BODY}px; background: transparent; }}
#root {{ background: {BG_MAIN}; }}

#sideBar {{ background: {BG_SIDE}; border-right: 1px solid {DIVIDER}; }}
#mainCol {{ background: {BG_MAIN}; }}

/* columns run full height; each starts with its own draggable 72px header row */
#winBtn, #winBtnClose {{ background: transparent; border: 2px solid transparent; }}
#winBtn:hover {{ background: rgba(255,255,255,0.08); }}
#winBtnClose:hover {{ background: {DANGER}; }}

#appName {{ font-size: {F_APP}px; font-weight: 600; color: {TEXT_STRONG}; }}
#appSub {{ font-size: 10px; font-weight: 400; color: {TEXT_MUTED}; }}

#menuItem {{ background: transparent; border: 2px solid transparent; border-radius: {R_MENU}px;
             color: {TEXT}; font-size: {F_BTN}px; font-weight: 500; text-align: left; padding: 0 10px; }}
#menuItem:hover {{ background: {BG_MENU_HOVER}; }}
#menuItem:checked {{ background: {BG_SELECTED}; color: {TEXT_STRONG}; }}

#sideSep {{ background: {DIVIDER}; border: none; }}

#injectStatus {{ font-size: {F_CHIP}px; color: {TEXT}; }}

#primaryBtn {{ background: #FFFFFF; border: 2px solid transparent; border-radius: {R_PRIMARY}px;
               color: {INK}; font-size: {F_BTN}px; font-weight: 600; }}
#primaryBtn:hover {{ background: #E8E8E8; }}
#primaryBtn:disabled {{ background: #FFFFFF; color: {INK}; }}

#ghostBtn {{ background: transparent; border: 2px solid transparent; border-radius: {R_MENU}px;
             color: {TEXT_GHOST}; font-size: {F_CHIP}px; padding: 0 10px; }}
#ghostBtn:hover {{ background: {HOVER_WASH}; color: {TEXT}; }}
#ghostBtn:disabled {{ color: #555555; }}

#outlineBtn {{ background: transparent; border: 1px solid {OUTLINE_BORDER}; border-radius: 18px;
               color: {TEXT_STRONG}; font-size: {F_BTN}px; font-weight: 500; padding: 0 16px; }}
#outlineBtn:hover {{ background: {HOVER_WASH}; }}

#iconBtn {{ background: transparent; border: 2px solid transparent; border-radius: {R_MENU}px; }}
#iconBtn:hover {{ background: {HOVER_WASH}; }}

#statusLine {{ color: {TEXT_MUTED}; font-size: {F_SMALL}px; }}

#tabBtn {{ background: transparent; border: 2px solid transparent; border-radius: 6px;
           color: {TAB_OFF}; font-size: {F_PAGE}px; font-weight: 600; padding: 0; }}
#tabBtn:checked {{ color: {TEXT_STRONG}; }}
#tabBtn:hover:!checked {{ color: {TEXT}; }}

#chip {{ background: {BG_CHIP}; border: 2px solid transparent; border-radius: 18px;
         color: #FFFFFF; font-size: {F_CHIP}px; font-weight: 400; padding: 0 16px; }}
#chip:hover {{ background: {BG_CHIP_HOVER}; }}
#chip:checked {{ background: #FFFFFF; color: {INK}; }}

#totalLbl {{ color: {TEXT_TOTAL}; font-size: {F_CHIP}px; }}
#sortBtn {{ background: transparent; border: 2px solid transparent; border-radius: {R_MENU}px;
            color: {TEXT_TOTAL}; font-size: {F_CHIP}px; padding: 0 10px; }}
#sortBtn:hover {{ background: {BG_CHIP}; }}

#pageTitle {{ font-size: {F_PAGE}px; font-weight: 600; color: {TEXT_STRONG}; }}
#setKey {{ color: {TEXT_TOTAL}; font-size: {F_CHIP}px; }}
#setVal {{ color: {TEXT}; font-size: {F_CHIP}px; }}

#searchBox {{ background: {BG_CARD}; border: 1px solid {DIVIDER}; border-radius: {R_MENU}px;
              color: {TEXT}; font-size: {F_CHIP}px; padding: 0 8px; }}
#searchBox:focus {{ border-color: {ACCENT}; }}

#spineList {{ background: {BG_CARD}; border: 1px solid {DIVIDER}; border-radius: {R_MENU}px;
              padding: 6px; color: {TEXT}; outline: none; }}
#spineList::item {{ padding: 6px 8px; border-radius: 5px; }}
#spineList::item:hover {{ background: {BG_CARD_HOVER}; }}
#spineList::item:selected {{ background: {BG_SELECTED}; color: {TEXT_STRONG}; }}

#emptyTitle {{ font-size: {F_CARD}px; font-weight: 600; color: {TEXT_STRONG}; }}
#emptyDesc {{ font-size: {F_CHIP}px; color: {TEXT_MUTED}; }}

QScrollBar:vertical {{ background: transparent; width: {SCROLLBAR_W}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {SCROLL_THUMB}; border-radius: 4px; min-height: 40px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: transparent; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: {SCROLLBAR_W}px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {SCROLL_THUMB}; border-radius: 4px; min-width: 40px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: transparent; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QMenu {{ background: {BG_CARD}; border: 1px solid {DIVIDER}; border-radius: {R_MENU}px; padding: 6px; }}
QMenu::item {{ padding: 7px 16px; border-radius: 6px; color: {TEXT}; font-size: {F_BTN}px;
               font-weight: 500; }}
QMenu::item:selected {{ background: {BG_CHIP}; color: {TEXT_STRONG}; }}
QMenu::item:disabled {{ color: #5A5A5A; }}

#floatTip {{ color: {TEXT_STRONG}; font-size: 12px; padding: 7px 11px; }}

QToolTip {{ background: #1C1C1C; color: {TEXT}; border: 1px solid {DIVIDER};
            padding: 4px 8px; font-size: {F_SMALL}px; }}

/* Focus ring for keyboard users only: buttons use Qt.TabFocus, so a mouse click
   never focuses them (and never lights this up). */
#winBtn:focus, #winBtnClose:focus, #menuItem:focus, #chip:focus, #tabBtn:focus,
#sortBtn:focus, #primaryBtn:focus, #ghostBtn:focus, #outlineBtn:focus,
#iconBtn:focus {{ border: 2px solid {ACCENT}; }}
"""


def apply(app) -> None:
    """Load the bundled Inter faces and set the single generated stylesheet."""
    for f in FONT_FILES:
        QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, f))
    base = QFont("Inter")
    base.setPixelSize(F_BODY)
    app.setFont(base)
    app.setStyleSheet(qss())


# ---- SVG icons (local set, thin strokes, recolored by mask) ----

@lru_cache(maxsize=512)
def icon_pixmap(name: str, size: int, color: str) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(os.path.join(ICON_DIR, name + ".svg"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), QColor(color))
    p.end()
    return pm


def icon(name: str, size: int, color: str = TEXT, active: str | None = None,
         disabled: str | None = None) -> QIcon:
    ic = QIcon(icon_pixmap(name, size, color))
    if active:
        ic.addPixmap(icon_pixmap(name, size, active), QIcon.Mode.Active)
    if disabled:
        ic.addPixmap(icon_pixmap(name, size, disabled), QIcon.Mode.Disabled)
    return ic
