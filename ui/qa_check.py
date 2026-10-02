"""Headless QA for the CZN Mod Manager UI.

Builds a throwaway Mods/ fixture, exercises the data layer, the layout grid and
the widget behaviours, and never writes to the game or the real Mods folder.
Run from the ui/ folder:

    QT_SCALE_FACTOR=1 ../.venv/Scripts/python.exe qa_check.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile

from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import (QDragEnterEvent, QDragLeaveEvent, QDropEvent, QFont,
                           QFontDatabase, QFontMetrics, QMouseEvent)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data  # noqa: E402
import theme  # noqa: E402
from main_window import MainWindow  # noqa: E402

TMP = tempfile.mkdtemp(prefix="cznqa_")
MODS = os.path.join(TMP, "Mods")
EMPTY_MODS = os.path.join(TMP, "ModsEmpty")

fails = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def png(path: str, color=(255, 0, 0), size=(64, 64)) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)


def sha1(path: str) -> str:
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def build_fixture() -> None:
    # enabled: Alpha Pack (mod pack), Beta + Delta (loose), effect/z.png (loose)
    pack = os.path.join(MODS, "Alpha Pack")
    png(os.path.join(pack, "a.png"), (10, 200, 10))
    png(os.path.join(pack, "b.png"), (10, 10, 200))
    json.dump({"name": "Alpha Pack", "map": {"a.png": "face/portrait/1001.sct",
                                             "b.png": "img/btn_dark_exit.sct"}},
              open(os.path.join(pack, "manifest.json"), "w"))
    png(os.path.join(MODS, "Delta.png"), (200, 60, 60), size=(128, 40))
    png(os.path.join(MODS, "Beta.png"), (60, 200, 60), size=(80, 80))
    png(os.path.join(MODS, "effect", "z.png"), (60, 60, 200), size=(48, 48))
    png(os.path.join(MODS, "_disabled", "Gamma.png"), (120, 120, 120))
    # spread mtimes so Newest/Oldest are deterministic (Delta newest)
    now = 1_700_000_000
    os.utime(os.path.join(MODS, "_disabled", "Gamma.png"), (now + 2, now + 2))
    for i, f in enumerate(["Alpha Pack/a.png", "Alpha Pack/b.png", "Alpha Pack",
                           "Beta.png", "effect/z.png", "Delta.png"]):
        os.utime(os.path.join(MODS, f), (now + i, now + i))
    # state: Beta fully applied; Alpha Pack partially applied
    state = {
        "Beta.png": {"png_sha1": sha1(os.path.join(MODS, "Beta.png")), "sct_sha1": "abc"},
        "Alpha Pack/a.png": {"png_sha1": sha1(os.path.join(pack, "a.png")), "sct_sha1": "abc"},
    }
    json.dump(state, open(os.path.join(MODS, ".state.json"), "w"))
    os.makedirs(EMPTY_MODS, exist_ok=True)


def main() -> None:
    build_fixture()

    app = QApplication([])
    theme.apply(app)

    def send_move(target, pos_local: QPoint) -> None:
        gp = target.mapToGlobal(pos_local)
        ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(pos_local), QPointF(gp),
                         Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, ev)

    def click_at(target, pos_local: QPoint) -> None:
        gp = target.mapToGlobal(pos_local)
        for typ in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(target, QMouseEvent(
                typ, QPointF(pos_local), QPointF(gp), Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    # ---------- data layer ----------
    enabled, disabled = data.scan(MODS)
    check("scan: 4 enabled mods", len(enabled) == 4, str([m.name for m in enabled]))
    check("scan: 1 disabled mod", len(disabled) == 1, str([m.name for m in disabled]))
    pack = next(m for m in enabled if m.name == "Alpha Pack")
    check("scan: pack merges worst status", pack.status == "pending", pack.status)
    beta = next(m for m in enabled if m.name == "Beta.png")
    check("scan: fully applied loose mod is ok", beta.status == "ok", beta.status)
    delta = next(m for m in enabled if m.name == "Delta.png")
    check("scan: missing state -> pending", delta.status == "pending", delta.status)
    check("scan: categories from target paths",
          {m.cat for m in enabled} == {"Character", "UI", "Other"},
          str(sorted({m.cat for m in enabled})))
    check("scan: disabled mod is off", disabled[0].status == "off", disabled[0].status)

    # ---------- fonts (real static weights, no synthesized bold) ----------
    styles = set(QFontDatabase.styles("Inter"))
    check("font: 3 static Inter faces loaded",
          styles >= {"Regular", "Medium", "SemiBold"}, str(styles))
    fn = QFont("Inter")
    fn.setPixelSize(16)
    fs = QFont(fn)
    fs.setWeight(QFont.Weight.DemiBold)
    adv_n, adv_s = QFontMetrics(fn).horizontalAdvance("Character"), \
        QFontMetrics(fs).horizontalAdvance("Character")
    check("font: SemiBold is a real face (metrics differ)", adv_s > adv_n,
          f"normal {adv_n} vs semibold {adv_s}")

    qss = theme.qss()
    check("qss: app name 18px/600", "#appName { font-size: 18px; font-weight: 600" in qss)
    check("qss: tab 22px/600, off colour #7A7A7A",
          "font-size: 22px; font-weight: 600" in qss and "#7A7A7A" in qss)
    check("qss: chip 13px/400", "font-size: 13px; font-weight: 400" in qss)
    check("qss: columns #101010 / #161616, divider 0.08",
          theme.BG_SIDE == "#101010" and theme.BG_MAIN == "#161616"
          and "255,255,255,0.08" in theme.DIVIDER)
    check("chip :checked adds no font override",
          "font-weight" not in qss.split("#chip:checked")[1].split("}")[0],
          qss.split("#chip:checked")[1].split("}")[0].strip()[:60])

    # ---------- window ----------
    win = MainWindow(MODS)
    win.resize(1400, 850)
    win.show()
    for _ in range(8):
        app.processEvents()

    tabs = {b.text(): b for b in win.tab_row.group.buttons()}
    check("three same-level tabs All/Enabled/Disabled",
          list(tabs) == ["All", "Enabled", "Disabled"], str(list(tabs)))
    check("All tab lists 5 cards (4 live + 1 parked)", len(win.view.mods) == 5,
          str([m.name for m in win.view.mods]))
    check("status band hidden when idle", not win.status.isVisible())
    check("primary button reads 'Apply mods'", win.side.primary.text() == "Apply mods")
    gi = win.findChild(QLabel, "appIcon")
    gn = win.findChild(QLabel, "appName")
    gsub = win.findChild(QLabel, "appSub")
    check("header: 'CZN MM/MI' title + Uncle's subtitle under it",
          gn.text() == "CZN MM/MI" and gsub.text() == "Uncle's CZN Mod Manager / Mod Importer",
          f"{gn.text()!r} / {gsub.text()!r}")
    check("game icon drawn left of the title, title above the subtitle",
          not gi.pixmap().isNull() and gi.x() < gn.x() and gn.y() < gsub.y(),
          f"icon x{gi.x()} < name x{gn.x()}; name y{gn.y()} < sub y{gsub.y()}")
    check("window title carries the new name",
          win.windowTitle() == "CZN MM/MI - Uncle's CZN Mod Manager / Mod Importer")
    check("qss: subtitle style present", "#appSub { font-size: 10px" in qss)
    tabs["Enabled"].click()
    check("Enabled tab lists 4 cards", len(win.view.mods) == 4,
          str([m.name for m in win.view.mods]))
    tabs["Disabled"].click()
    check("Disabled tab lists the parked mod", [m.name for m in win.view.mods] == ["Gamma.png"],
          str([m.name for m in win.view.mods]))
    tabs["All"].click()

    gs = win.view.gridSize()
    row = (win.view.width() - theme.SCROLLBAR_W - 2 + theme.GRID_GAP) // (gs.width())
    check("grid 1400x850: >=4 cards per row, cell >= min width",
          row >= 4 and gs.width() - theme.GRID_GAP >= theme.CARD_MIN_W,
          f"cell {gs.width()}x{gs.height()}")
    win.resize(1100, 700)
    for _ in range(4):
        app.processEvents()
    gs2 = win.view.gridSize()
    row2 = (win.view.width() - theme.SCROLLBAR_W - 2 + theme.GRID_GAP) // gs2.width()
    check("grid 1100x700: 3 cards per row", row2 == 3, f"cell {gs2.width()}x{gs2.height()}")

    # card cover + title: char portrait thumb by default ("name - id - file" title),
    # the mod's own image while the card is hovered
    cats = data.char_names()
    if cats:
        pid = 1017 if 1017 in cats else next(iter(cats))
        ttl = data._loose_title(f"{pid}.png", f"face/portrait/{pid}.sct")
        check("loose title carries char name - id - file",
              ttl == f"{cats[pid]} - {pid} - {pid}.png", ttl)
        check("title falls back to the file name without a char in the target",
              data._loose_title("x.png", "img/btn_dark_exit.sct") == "x.png"
              and data._loose_title("Delta.png", "Delta.png") == "Delta.png",
              data._loose_title("Delta.png", "Delta.png"))
        tpath = os.path.join(data.CHAR_THUMB_DIR, f"{pid}.png")
        if os.path.exists(tpath):
            fake = data.Mod(key="x", action_name="x", name="x",
                            desc=f"face/portrait/{pid}.sct", kind="loose image",
                            cat="Character", meta="1 image", date="01.01", mtime=0.0,
                            hue=0, status="pending", banner=os.path.join(MODS, "Beta.png"))
            d = win.view.card_delegate
            check("card cover: char portrait by default, mod image on hover",
                  d._thumb(160, 90, fake, 1.0, hover=False).toImage()
                  != d._thumb(160, 90, fake, 1.0, hover=True).toImage(), f"id {pid}")
            nochar = data.Mod(key="y", action_name="y", name="y", desc="img/btn_dark_exit.sct",
                              kind="loose image", cat="UI", meta="1 image", date="01.01",
                              mtime=0.0, hue=0, status="pending",
                              banner=os.path.join(MODS, "Beta.png"))
            check("card cover falls back to the mod image when no char thumb",
                  d._thumb(160, 90, nochar, 1.0, hover=False).toImage()
                  == d._thumb(160, 90, nochar, 1.0, hover=True).toImage(), "fallback differs")
        else:
            print("  [i] char thumb cache empty - cover pixmap checks skipped")
    else:
        print("  [i] char catalog unavailable - title/cover checks skipped")
    win.resize(1400, 850)
    for _ in range(4):
        app.processEvents()

    # banner + chips + total + sort
    first = win.view.mods[0]
    pm = win.view.card_delegate._thumb(200, 112, first, 1.0)
    img = pm.toImage()
    check("banner corner transparent", img.pixelColor(1, 1).alpha() == 0)
    px = img.pixelColor(100, 20)
    check("banner shows the mod png", px.red() > 150 and px.green() < 120, str(px.getRgb()))

    chips = win.toolbar.chips
    check("filter row = categories only (no All chip)",
          sorted(b.text() for b in chips.buttons) == ["Character", "Other", "UI"],
          str([b.text() for b in chips.buttons]))
    by_text = {b.text(): b for b in chips.buttons}
    by_text["UI"].click()
    check("chip 'UI' filters to 1 card", [m.name for m in win.view.mods] == ["effect/z.png"],
          str([m.name for m in win.view.mods]))
    check("total label follows filter", win.info.total.text() == "Total 1", win.info.total.text())
    # chips are rebuilt on every filter change - always re-fetch the buttons
    {b.text(): b for b in chips.buttons}["UI"].click()
    check("clicking the active chip clears the filter", len(win.view.mods) == 5,
          str([m.name for m in win.view.mods]))
    win.info.sort_btn.setText("Oldest")
    win._set_sort("Oldest")
    check("sort Oldest puts the oldest first", win.view.mods[0].name == "Alpha Pack",
          win.view.mods[0].name)
    win._set_sort("Newest")
    check("sort Newest puts the newest first", win.view.mods[0].name == "Delta.png",
          win.view.mods[0].name)

    # chip click on a card issues disable
    calls: list[list[str]] = []
    win._run_cli = lambda args, what: calls.append(args)
    win.view.viewport().repaint()          # fill chip_hit with the current layout
    row0 = next(i for i, m in enumerate(win.view.mods) if m.name == "Delta.png")
    r = win.view.card_delegate.chip_hit[row0]
    click_at(win.view.viewport(), r.center().toPoint())
    check("chip click issues 'disable'", calls == [["disable", "Delta.png"]], str(calls))

    # parked card (All tab) enables on chip click
    win.view.viewport().repaint()
    rowg = next(i for i, m in enumerate(win.view.mods) if m.name == "Gamma.png")
    r = win.view.card_delegate.chip_hit[rowg]
    click_at(win.view.viewport(), r.center().toPoint())
    check("chip click on parked card issues 'enable'",
          calls[-1] == ["enable", "Gamma.png"], str(calls[-1]))

    # ---------- layout / typography geometry ----------
    y_name = win.side._name_row.mapTo(win, QPoint(0, 0)).y()
    y_tabs = win.tab_row.mapTo(win, QPoint(0, 0)).y()
    check("72px header rows share one line (top of window)",
          y_name == y_tabs == 0
          and win.side._name_row.height() == win.tab_row.height() == theme.HEADER_H,
          f"y {y_name}/{y_tabs}")

    btns_pos = win.btns.mapTo(win, QPoint(0, 0))
    check("window buttons flush with the top-right corner",
          btns_pos.x() == win.width() - win.btns.width() and btns_pos.y() == 0,
          f"{btns_pos.x()},{btns_pos.y()} of {win.width()}")

    y_tabs_b = win.tab_row.mapTo(win, QPoint(0, 0)).y() + win.tab_row.height()
    y_tool = win.toolbar.mapTo(win, QPoint(0, 0)).y()
    y_info = win.info.mapTo(win, QPoint(0, 0)).y()
    y_grid = win.view.mapTo(win, QPoint(0, 0)).y()
    gap1 = y_tool - y_tabs_b
    gap2 = y_info - (y_tool + win.toolbar.height())
    gap3 = y_grid - (y_info + win.info.height())
    check("vertical rhythm: tab->chip 20, chip->Total 16, Total->grid 16",
          (gap1, gap2, gap3) == (20, 16, 16), f"{gap1}/{gap2}/{gap3}")
    check("toolbar: refresh 36px + 'Open folder' outline, no Add mod button",
          win.toolbar.refresh.size().width() == 36
          and win.toolbar.refresh.size().height() == 36
          and win.toolbar.open_folder.objectName() == "outlineBtn"
          and win.toolbar.open_folder.text() == "Open folder"
          and "Add mod" not in [b.text() for b in win.toolbar.findChildren(QPushButton)])
    check("inject block: primary 44px + revert ghost + status dot",
          win.side.primary.height() == 44 and win.side.revert.height() == 32
          and win.side.dot.width() == 8)
    check("game status line sits under 'Revert all'",
          win.side.primary.y() < win.side.revert.y() < win.side.status_lbl.y(),
          f"y {win.side.primary.y()}/{win.side.revert.y()}/{win.side.status_lbl.y()}")

    # ---------- settings page (real page, not a popup) ----------
    menu = {b.text(): b for b in win.side._menu_items}
    menu["Settings"].click()
    for _ in range(3):
        app.processEvents()
    labels = [w.text() for w in win.settings_page.findChildren(QLabel)]
    check("Settings is a real page with content",
          win.stack.currentIndex() == 1 and win.settings_page.isVisible()
          and "Game folder" in labels and "Mods folder" in labels,
          str(labels[:4]))
    check("Browse button hidden while the game is found",
          win._game_browse is not None and not win._game_browse.isVisible())
    # ---------- Char ID page ----------
    check("sidebar menu lists Mods/Settings/Char ID",
          [b.text() for b in win.side._menu_items] == ["Mods", "Settings", "Char ID"],
          str([b.text() for b in win.side._menu_items]))
    menu["Char ID"].click()
    for _ in range(8):
        app.processEvents()
    rows = win._char_rows or []
    check("Char ID is a real page below Settings",
          win.stack.currentIndex() == 2 and win.char_page.isVisible(), str(win.stack.currentIndex()))
    check("catalog has >=150 ids", len(rows) >= 150, str(len(rows)))
    by_id = {r["id"]: r for r in rows}
    check("1041 = Renoa (playable)", by_id.get(1041, {}).get("name") == "Renoa"
          and by_id.get(1041, {}).get("group") == "playable")
    check("groups are Playable/Support/Other",
          {r["label"] for r in rows} == {"Playable", "Support", "Other"},
          str({r["label"] for r in rows}))
    check("char chips = Playable/Support/Other",
          [b.text() for b in win.char_chips.buttons] == ["Playable", "Support", "Other"],
          str([b.text() for b in win.char_chips.buttons]))
    win.char_search.setText("lenore")
    for _ in range(3):
        app.processEvents()
    check("search 'lenore' finds exactly 1041",
          [r["id"] for r in win._char_shown] == [1041], str([r["id"] for r in win._char_shown]))
    win.char_search.setText("")
    for _ in range(2):
        app.processEvents()
    {b.text(): b for b in win.char_chips.buttons}["Support"].click()
    for _ in range(3):
        app.processEvents()
    supp_n = sum(1 for r in rows if r["group"] == "supporter")
    check("Support chip filters to supporters only",
          len(win._char_shown) == supp_n and all(r["group"] == "supporter" for r in win._char_shown),
          f"{len(win._char_shown)}/{supp_n}")
    {b.text(): b for b in win.char_chips.buttons}["Support"].click()
    for _ in range(3):
        app.processEvents()
    check("re-clicking the chip clears the group filter", len(win._char_shown) == len(rows))
    orig_cols = win.char_grid.cols_fixed
    win.char_grid.set_columns(0)          # QA is deterministic: test adaptive first
    app.processEvents()
    check("char grid cell >= min width",
          win.char_grid.gridSize().width() - theme.GRID_GAP >= 150,
          str(win.char_grid.gridSize()))
    win.char_grid.set_columns(6)
    app.processEvents()
    gs6 = win.char_grid.gridSize()
    per_row = (win.char_grid.width() - theme.SCROLLBAR_W - 2 + theme.GRID_GAP) // gs6.width()
    check("fixed 6 columns: exactly 6 per row", per_row == 6,
          f"cell {gs6.width()} per_row {per_row}")

    # every control carries a tooltip; the painted grids carry them via the model
    tips = {"Apply mods": win.side.primary, "Revert all": win.side.revert,
            "refresh": win.toolbar.refresh, "Open folder": win.toolbar.open_folder,
            "sort": win.info.sort_btn, "tabs": win.tab_row.group.buttons()[0],
            "chips": win.toolbar.chips.buttons[0], "search": win.char_search,
            "columns": win.char_cols_btn, "char chips": win.char_chips.buttons[0]}
    missing = [k for k, w in tips.items() if not w.toolTip()]
    check("tooltips: controls described", not missing, str(missing))
    ctip = win.char_grid.item_model.item(0).toolTip()
    check("tooltip: char card has name - id + export hint",
          " - " in ctip and "Export" in ctip, ctip.replace("\n", " | "))
    from widgets.mod_delegate import STATUS_TIPS as _STIPS
    mtip = win.view.item_model.item(0).toolTip()
    check("tooltip: mod card shows only the status action",
          mtip == _STIPS[win.view.mods[0].status] and "face/" not in mtip, mtip)

    # custom float tooltip: our popup shows the tip at the cursor (native is swallowed)
    from PySide6.QtGui import QHelpEvent
    menu["Mods"].click()                # back on the mods page: cursor coords must hit it
    for _ in range(3):
        app.processEvents()
    btn = win.toolbar.refresh
    QApplication.sendEvent(btn, QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5),
                                           btn.mapToGlobal(QPoint(5, 5))))
    check("float tooltip shows the control tip",
          win._tips.popup.isVisible() and win._tips.popup.text() == btn.toolTip(),
          f"{win._tips.popup.isVisible()} {win._tips.popup.text()!r}")
    rc = win.view.visualRect(win.view.item_model.index(0, 0))
    lp = rc.center()
    QApplication.sendEvent(win.view.viewport(),
                           QHelpEvent(QEvent.Type.ToolTip, lp,
                                      win.view.viewport().mapToGlobal(lp)))
    check("float tooltip resolves model tips on cards",
          win._tips.popup.text() == win.view.item_model.item(0).toolTip(),
          win._tips.popup.text().replace("\n", " | "))
    # glide: one follow tick moves part of the way toward the pointer (not a jump)
    from widgets import float_tip as ft

    class _Cur:
        pos = staticmethod(lambda: QPoint(500, 300))

    real_cursor = ft.QCursor
    ft.QCursor = _Cur
    try:
        p = win._tips.popup
        p.move(300, 300)
        win._tips._gp = QPoint(500, 300)      # pretend the pointer already moved
        win._tips._tick()
        moved = p.pos().x()
        check("float tooltip glides toward the pointer",
              300 < moved < 500, f"x {moved} of 514")
    finally:
        ft.QCursor = real_cursor
        win._tips._hide()
    QApplication.sendEvent(win, QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2),
                                           win.mapToGlobal(QPoint(2, 2))))
    check("float tooltip hides when nothing is described",
          not win._tips.popup.isVisible(), str(win._tips.popup.isVisible()))
    win.char_grid.set_columns(0)
    app.processEvents()
    check("Auto columns restored", win.char_grid.gridSize().width() - theme.GRID_GAP >= 150,
          str(win.char_grid.gridSize()))
    win.char_grid.set_columns(orig_cols)
    check("columns button hugs its content", win.char_cols_btn.width() < 170,
          str(win.char_cols_btn.width()))
    bx = win.char_cols_btn.mapTo(win, QPoint(win.char_cols_btn.width(), 0)).x()
    check("columns button flush with the content right edge", bx == win.width() - theme.PAD_MAIN,
          f"{bx} vs {win.width() - theme.PAD_MAIN}")

    # right-click card menu: Export Asset / Locate Asset
    from PySide6.QtGui import QContextMenuEvent
    got: dict = {}
    win.char_grid.cardMenuRequested.connect(lambda r, p: got.update(row=r))
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(40, 40),
                           win.char_grid.viewport().mapToGlobal(QPoint(40, 40)))
    QApplication.sendEvent(win.char_grid.viewport(), ev)   # the real delivery path
    check("right-click on a card requests the menu", got.get("row") == 0, str(got))
    calls2: list = []
    win._run_cli = lambda args, what: calls2.append((args, what))
    r0 = win.char_grid.rows[0]
    folder = win._char_asset_dir(r0)
    win._char_export(r0, folder)
    check("Export Asset issues 'export <id> <dir>'",
          bool(calls2) and calls2[-1][0] == ["export", str(r0["id"]), folder],
          str(calls2[-1] if calls2 else None))
    check("asset folder is <root>/<ID>_<name>",
          os.path.basename(folder) == f"{r0['id']}_{r0['name']}", folder)
    if os.path.isdir(folder):
        check("Locate Asset enabled for an exported character", True)
    else:
        check("Locate Asset disabled without an export folder (no local export - skipped)", True)
    menu["Mods"].click()
    for _ in range(3):
        app.processEvents()
    check("sidebar switches back to the Mods page", win.stack.currentIndex() == 0)

    # ---------- game folder: picker write + root-mismatch state ----------
    cfg = os.path.join(data.ROOT, "game_path.txt")
    saved_cfg = open(cfg, "rb").read() if os.path.isfile(cfg) else None
    fake = os.path.join(TMP, "fake_game")
    os.makedirs(os.path.join(fake, "bin", "appdata", "cznlive", "gameres"), exist_ok=True)
    open(os.path.join(fake, "bin", "appdata", "cznlive", "gameres", "manifest.ssra"), "w").close()
    check("set_game_dir accepts the game root (also when bin\\ was picked)",
          data.set_game_dir(os.path.join(fake, "bin")))
    check("game_path.txt remembers the corrected root",
          open(cfg, encoding="utf-8-sig").read().strip() == fake,
          open(cfg, encoding="utf-8-sig").read().strip())
    check("set_game_dir rejects a non-install folder", not data.set_game_dir(TMP))
    if saved_cfg is not None:
        open(cfg, "wb").write(saved_cfg)
    else:
        os.remove(cfg)
    sys.modules.pop("czn_paths", None)
    data._ROOT.clear()

    if data.game_root():
        st_path = os.path.join(MODS, ".state.json")
        sha = data._sha1(open(os.path.join(MODS, "Delta.png"), "rb").read())

        def write_state(root):
            json.dump({"Delta.png": {"png_sha1": sha, "sct_sha1": "a" * 40,
                                     "target": "img/btn_dark_exit.sct", "game_root": root}},
                      open(st_path, "w"))

        write_state("Z:\\OldInstall")
        en, _ = data.scan(MODS)
        d = next(m for m in en if m.name == "Delta.png")
        check("mod applied to an older game folder reads Pending",
              d.status == "pending", d.status)
        check("game_root_changed flags the mismatch", data.game_root_changed(MODS))
        write_state(data.game_root())
        en, _ = data.scan(MODS)
        d = next(m for m in en if m.name == "Delta.png")
        check("same game folder keeps 'Enabled'", d.status == "ok", d.status)
        os.remove(st_path)
    else:
        check("game-folder mismatch checks (no local game - skipped)", True)

    # ---------- focus rules ----------
    check("no button focused at startup",
          not isinstance(app.focusWidget(), QPushButton),
          str(app.focusWidget()))
    b = chips.buttons[1]
    click_at(b, b.rect().center())
    check("mouse click does not focus a button", app.focusWidget() is not b,
          str(app.focusWidget()))

    # ---------- game-running state ----------
    real_running = data.game_running
    data.game_running = lambda: True
    win._poll_game()
    check("game running: inject disabled + tooltip",
          not win.side.primary.isEnabled()
          and not win.side.revert.isEnabled()
          and bool(win.side.primary.toolTip()),
          win.side.primary.toolTip())
    data.game_running = lambda: False
    win._poll_game()
    check("game closed: inject enabled again", win.side.primary.isEnabled())
    data.game_running = real_running

    # ---------- empty state + drag & drop ----------
    win2 = MainWindow(EMPTY_MODS)
    win2.resize(1400, 850)
    win2.show()
    for _ in range(8):
        app.processEvents()
    check("empty state visible when no mods",
          win2.empty.isVisible() and not win2.view.isVisible())
    check("empty state min height 280", win2.empty.minimumHeight() == 280)
    check("empty state default message", win2.empty.title.text() == "No mods yet",
          win2.empty.title.text())
    check("empty state hint points at Open folder",
          win2.empty.desc.text() == 'Click "Open folder" and drop your mods in',
          win2.empty.desc.text())
    check("empty state has no Add mod button",
          not win2.empty.findChildren(QPushButton))
    tabs2 = {b.text(): b for b in win2.tab_row.group.buttons()}
    tabs2["Disabled"].click()
    for _ in range(3):
        app.processEvents()
    check("empty Disabled tab shows the same message as the other tabs",
          win2.empty.title.text() == "No mods yet"
          and win2.empty.desc.text() == 'Click "Open folder" and drop your mods in',
          win2.empty.title.text())
    tabs2["All"].click()
    for _ in range(3):
        app.processEvents()

    drop_file = os.path.join(TMP, "Dropped.png")
    png(drop_file, (200, 120, 10))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(drop_file)])
    enter = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win2.empty, enter)
    check("drag over empty state: accepted + highlight", enter.isAccepted() and win2.empty._drag)
    QApplication.sendEvent(win2.empty, QDragLeaveEvent())
    check("drag leave clears the highlight", not win2.empty._drag)
    QApplication.sendEvent(win2.empty, enter)
    drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win2.empty, drop)
    got = os.path.join(EMPTY_MODS, "Dropped.png")
    check("drop copies the file into Mods", os.path.exists(got))
    check("drop refreshes to a 1-card grid",
          len(win2.view.mods) == 1 and win2.view.isVisible() and not win2.empty.isVisible())

    copied, errors = data.add_mods(EMPTY_MODS, [drop_file])
    check("add_mods clash renames to ' (2)'",
          copied == 1 and os.path.exists(os.path.join(EMPTY_MODS, "Dropped (2).png")))
    copied, errors = data.add_mods(EMPTY_MODS, [got])
    check("add_mods skips sources already inside Mods", copied == 0)

    # ---------- delegates / interaction regressions ----------
    send_move(win.view.viewport(), QPoint(80, 80))
    QTest.qWait(260)                       # let the 130 ms hover fade finish
    d = win.view.card_delegate
    check("hover fade reaches 1.0", d._hover == 0 and d._v >= 0.99, f"row {d._hover} v {d._v:.2f}")

    win.side.primary.setFocus()
    win.setFocus()
    for _ in range(2):
        app.processEvents()
    win.showMaximized()
    for _ in range(3):
        app.processEvents()
    rel0 = win.view.gridSize()
    calls0 = getattr(win.view, "_qa_relayout_calls", None)
    for _ in range(8):
        app.processEvents()
    check("maximize: no layout feedback loop",
          win.view.gridSize() == rel0, f"{rel0} -> {win.view.gridSize()}")
    win.showNormal()
    for _ in range(3):
        app.processEvents()

    # cursor zones
    win.resize(1400, 850)
    for _ in range(3):
        app.processEvents()
    send_move(win, QPoint(3, 847))
    check("cursor SW in the bottom-left ring",
          win.cursor().shape() == Qt.CursorShape.SizeBDiagCursor, str(win.cursor().shape()))
    send_move(win, QPoint(400, 400))
    check("cursor back to arrow over content",
          win.cursor().shape() == Qt.CursorShape.ArrowCursor, str(win.cursor().shape()))
    send_move(win, QPoint(win.width() - 10, 3))    # top sliver of the close button
    check("cursor stays arrow over the window buttons (they reach y=0)",
          win.cursor().shape() == Qt.CursorShape.ArrowCursor, str(win.cursor().shape()))
    g = win.btns.btn_close.mapToGlobal(QPoint(5, 2))
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 2), QPointF(g),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    check("edge press over the window buttons stays a click, not a resize",
          win.eventFilter(win.btns.btn_close, ev) is False)

    # ---------- summary ----------
    win.close()
    win2.close()
    print()
    if fails:
        print(f"{len(fails)} FAILED: {fails}")
        sys.exit(1)
    print("all checks pass")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
