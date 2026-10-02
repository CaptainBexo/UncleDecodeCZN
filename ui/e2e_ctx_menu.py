"""E2E: real OS right-click in the Viewer -> trimmed menu; Copy image and Save
image (dialog patched) must act on the real context and produce output.

Run from ui/: ../.venv/Scripts/python.exe e2e_ctx_menu.py
"""
import os
import sys
import json
import time
import ctypes

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), "scripts"))

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu
from PySide6.QtWebEngineCore import QWebEnginePage

import data
import theme
from main_window import MainWindow

TMP = os.path.join(data.ROOT, "cache", "e2e_ctx")
MODS = os.path.join(data.ROOT, "dist_exe", "Mods")

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication([])
theme.apply(app)
win = MainWindow(MODS)
win.resize(1200, 750)
win.show()
for _ in range(40):
    app.processEvents(); time.sleep(0.05)

# the real app flow: a mod whose tag targets face/portrait/1017
ren, roff = data.scan(MODS)
m1017 = next((x for x in (*ren, *roff) if x.desc.endswith("face/portrait/1017.sct")), None)
print("m1017:", m1017.desc if m1017 else None)
win.dock.show()
win.dock.move(160, 80)
win.dock.resize(560, 700)
if m1017 is not None:
    win.dock.show_mod(m1017)
for _ in range(600):
    app.processEvents(); time.sleep(0.05)
    if "m=mod_" in win.dock.panel.view.url().toString():
        break
for _ in range(60):
    app.processEvents(); time.sleep(0.05)
print("url:", win.dock.panel.view.url().toString())

view = win.dock.panel.view
res = {}
view.page().runJavaScript(
    "(() => { const r = document.getElementById('c').getBoundingClientRect();"
    " return JSON.stringify({x:r.x, y:r.y, w:r.width, h:r.height,"
    " msg: document.getElementById('msg').textContent}); })()",
    lambda v: res.update(v=v))
for _ in range(60):
    app.processEvents(); time.sleep(0.02)
info = json.loads(res.get("v") or "{}")
print("canvas:", info)
vpos = view.mapTo(win.dock, QPoint(0, 0))
cx = vpos.x() + int(info.get("x", 0) + info.get("w", 100) / 2)
cy = vpos.y() + int(info.get("y", 0) + info.get("h", 100) / 2)
print("click at dock client:", cx, cy)

u32 = ctypes.windll.user32
hwnd = int(win.dock.winId())
scr = QGuiApplication.primaryScreen()
shot = os.path.join(data.ROOT, "ui", "shots", "viewer_ctx_menu.png")
os.makedirs(TMP, exist_ok=True)
dest = os.path.join(TMP, "saved.png")
if os.path.exists(dest):
    os.remove(dest)
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (dest, "PNG (*.png)"))

page = view.page()
out = {}


def act_in_menu():
    """Runs inside the menu's modal loop: the click context is live here."""
    scr.grabWindow(0).save(shot)
    ac = page.action(QWebEnginePage.WebAction.CopyImageToClipboard)
    out["copy_enabled"] = ac.isEnabled()
    ac.trigger()
    for w in app.topLevelWidgets():
        if isinstance(w, QMenu) and w.isVisible():
            for a in w.actions():
                if a.text() == "Save image":
                    out["save_item"] = True
                    a.trigger()             # opens our patched dialog, then writes
            w.close()


QTimer.singleShot(1000, act_in_menu)
lp = (cy << 16) | cx
u32.PostMessageW(hwnd, 0x0204, 2, lp)          # WM_RBUTTONDOWN
u32.PostMessageW(hwnd, 0x0205, 0, lp)          # WM_RBUTTONUP
t0 = time.time()
while time.time() - t0 < 20 and "copy_enabled" not in out:
    app.processEvents(); time.sleep(0.02)
for _ in range(40):
    app.processEvents(); time.sleep(0.02)
print("actions: copy enabled", out.get("copy_enabled"), "| save item fired", out.get("save_item"))
print("menu shot:", os.path.exists(shot), os.path.getsize(shot) if os.path.exists(shot) else 0)

cb = QGuiApplication.clipboard().image()
print("clipboard:", cb.width(), "x", cb.height(), "null:", cb.isNull())

t0 = time.time()
while time.time() - t0 < 10 and not (os.path.exists(dest) and os.path.getsize(dest) > 1000):
    app.processEvents(); time.sleep(0.05)
if os.path.exists(dest):
    from PIL import Image
    im = Image.open(dest)
    print("saved:", dest, im.size, im.mode, os.path.getsize(dest))
else:
    print("saved: MISSING", dest)
print("done")
