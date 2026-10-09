"""Lightweight update check: fetch the latest release metadata, compare with the
running version. stdlib only - no extra dependencies, no telemetry, one plain GET.

Host choice lives in UPDATER_URL: the GitHub releases API of the (public) repo,
or a static latest.json ({"version","url","notes","sha256"}) if it ever moves.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

from PySide6.QtCore import QThread, Signal

import version

UPDATER_URL = "https://api.github.com/repos/CaptainBexo/UncleDecodeCZN/releases/latest"
TIMEOUT_S = 6


def _parts(v: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", str(v))[:3]) or (0,)


def newer(current: str, latest: str) -> bool:
    """True when `latest` is a strictly newer version than `current`."""
    a, b = _parts(latest), _parts(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def parse(payload: dict) -> dict:
    """Normalize both payload shapes; KeyError/ValueError = unusable response."""
    if "tag_name" in payload:                       # GitHub releases/latest
        assets = payload.get("assets") or []
        zips = [a for a in assets if str(a.get("browser_download_url", "")).endswith(".zip")]
        if not zips:
            raise ValueError("no zip asset in the release")
        a = zips[0]
        exes = [x for x in assets if str(x.get("browser_download_url", "")).endswith(".exe")]
        exe = exes[0] if exes else None
        return {"version": str(payload["tag_name"]).lstrip("vV"),
                "url": a["browser_download_url"],
                "page": payload.get("html_url", ""),
                "notes": payload.get("body", ""),
                "sha256": str(a.get("digest", "")).removeprefix("sha256:") or None,
                "exe_url": exe["browser_download_url"] if exe else "",
                "exe_sha256": (str(exe.get("digest", "")).removeprefix("sha256:") or None) if exe else None}
    return {"version": str(payload["version"]),
            "url": payload.get("url", ""),
            "page": payload.get("url", ""),
            "notes": payload.get("notes", ""),
            "sha256": payload.get("sha256"),
            "exe_url": payload.get("exe_url", ""),
            "exe_sha256": payload.get("exe_sha256")}


def fetch(url: str = UPDATER_URL) -> dict:
    """GET + parse; raises on any failure (the caller decides how quiet to be)."""
    req = urllib.request.Request(url, headers={"User-Agent": "czn-updater",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return parse(json.loads(r.read().decode("utf-8")))


class UpdateCheck(QThread):
    """Runs fetch() off the UI thread; result = normalized dict or None (+ why)."""
    done = Signal(object, str)                      # (result|None, error text)

    def run(self) -> None:
        try:
            self.done.emit(fetch(), "")
        except Exception as e:                      # noqa: BLE001 - offline/timeout/bad json
            self.done.emit(None, "%s" % e)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Download(QThread):
    """Downloads the release exe to `<running exe>.new`, sha256-checked before
    it is accepted. The swap itself happens later, from the exit script."""
    progress = Signal(int, int)                     # (done_bytes, total_bytes)
    done = Signal(bool, str, str)                   # (ok, staged path, error)

    def __init__(self, url: str, sha256: str | None, target: str, parent=None) -> None:
        super().__init__(parent)
        self._url, self._sha, self._target = url, sha256, target

    def run(self) -> None:
        part = self._target + ".part"
        try:
            req = urllib.request.Request(self._url, headers={"User-Agent": "czn-updater"})
            with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    self.progress.emit(done, total)
            if self._sha and sha256_file(part).lower() != self._sha.lower():
                os.remove(part)
                self.done.emit(False, "", "checksum mismatch")
                return
            os.replace(part, self._target)
            self.done.emit(True, self._target, "")
        except Exception as e:                      # noqa: BLE001 - offline/timeout/disk
            try:
                os.remove(part)
            except OSError:
                pass
            self.done.emit(False, "", "%s" % e)


def write_swap_script(pid: int, exe_path: str, relaunch: bool = False) -> str:
    """A cmd script: waits for `pid` to exit, swaps `exe_path` with its staged
    `<exe_path>.new`, cleans up. relaunch=True starts the new exe right away
    (self-restart); False just leaves it for the next manual open. On repeated
    lock failures the old exe is put back, so the worst case is 'update did
    not apply', never a missing exe."""
    exe_path = os.path.abspath(exe_path)
    new, bak = exe_path + ".new", exe_path + ".old"
    rel_line = f'start "" "{exe_path}"\n' if relaunch else ""
    bat = os.path.join(tempfile.gettempdir(), "czn_update_%d.bat" % pid)
    script = f"""@echo off
setlocal EnableDelayedExpansion
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (
  ping -n 2 127.0.0.1 >nul
  goto wait
)
set N=0
:swapold
move /y "{exe_path}" "{bak}" >nul 2>&1
if errorlevel 1 (
  set /a N+=1
  if !N! geq 60 goto fail
  ping -n 2 127.0.0.1 >nul
  goto swapold
)
set N=0
:swapnew
move /y "{new}" "{exe_path}" >nul 2>&1
if errorlevel 1 (
  set /a N+=1
  if !N! geq 60 goto restore
  ping -n 2 127.0.0.1 >nul
  goto swapnew
)
{rel_line}del "{bak}" >nul 2>&1
del "%~f0" >nul 2>&1
exit /b 0
:restore
if not exist "{exe_path}" move /y "{bak}" "{exe_path}" >nul 2>&1
del "%~f0" >nul 2>&1
exit /b 1
:fail
del "%~f0" >nul 2>&1
exit /b 1
"""
    # cmd reads batches in the ANSI codepage; the exe path may be non-ASCII
    with open(bat, "w", encoding="mbcs", newline="\r\n") as f:
        f.write(script)
    return bat
