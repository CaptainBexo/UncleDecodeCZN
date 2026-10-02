"""Localhost static server for the embedded Spine viewer.

QtWebEngine blocks file:// XHR, so the viewer page and its per-model asset
folders (APP/cache/spine) are served from a loopback-only HTTP server instead.
Read-only GETs; one daemon thread; dies with the process.
"""
from __future__ import annotations

import functools
import http.server
import threading

_srv = None


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):      # no per-request logging
        pass


def ensure(root: str) -> str:
    """Start the server once (rooted at `root`) and return its base URL."""
    global _srv
    if _srv is None:
        handler = functools.partial(_Quiet, directory=root)
        _srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=_srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % _srv.server_address[1]
