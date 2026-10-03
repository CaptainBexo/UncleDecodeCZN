"""Lightweight update check: fetch the latest release metadata, compare with the
running version. stdlib only - no extra dependencies, no telemetry, one plain GET.

Host choice lives in UPDATER_URL: the GitHub releases API of the (public) repo,
or a static latest.json ({"version","url","notes","sha256"}) if it ever moves.
"""
from __future__ import annotations

import json
import re
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
        return {"version": str(payload["tag_name"]).lstrip("vV"),
                "url": a["browser_download_url"],
                "page": payload.get("html_url", ""),
                "notes": payload.get("body", ""),
                "sha256": str(a.get("digest", "")).removeprefix("sha256:") or None}
    return {"version": str(payload["version"]),
            "url": payload.get("url", ""),
            "page": payload.get("url", ""),
            "notes": payload.get("notes", ""),
            "sha256": payload.get("sha256")}


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
