"""
BotikDevServer — HTTP IPC server embedded in the botik process.
Runs on localhost:9989 (or env BOTIK_DEV_PORT).

Endpoints
─────────
  GET  /ping                        → {"ok": true, "version": "...", "uptime_s": N}
  GET  /screenshot                  → image/png  (PrintWindow — no focus steal, works minimized)
  POST /navigate  {"tab": "home"}   → {"ok": true, "tab": "home"}
  GET  /api/<method>                → JSON result of api.<method>()
  POST /api/<method>  {kwargs}      → JSON result of api.<method>(**kwargs)

Usage (from webview_app.py main()):
  from .dev_server import BotikDevServer
  server = BotikDevServer(api=api, version=version)
  server.start()                    # daemon thread, non-blocking
  # later pass window object:
  server.set_window(window)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any

log = logging.getLogger("botik.dev_server")

DEV_PORT = int(os.environ.get("BOTIK_DEV_PORT", "9989"))

# ─── Windows GDI helpers for silent window capture ───────────────────────────

_gdi32  = ctypes.windll.gdi32
_user32 = ctypes.windll.user32

_PW_RENDERFULLCONTENT = 2  # capture layered/composited children (WebView2)


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          ctypes.wintypes.DWORD),
        ("biWidth",         ctypes.wintypes.LONG),
        ("biHeight",        ctypes.wintypes.LONG),
        ("biPlanes",        ctypes.wintypes.WORD),
        ("biBitCount",      ctypes.wintypes.WORD),
        ("biCompression",   ctypes.wintypes.DWORD),
        ("biSizeImage",     ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed",       ctypes.wintypes.DWORD),
        ("biClrImportant",  ctypes.wintypes.DWORD),
    ]


_SW_SHOWNOACTIVATE = 4
_SW_SHOWMINIMIZED  = 2


def _capture_hwnd_silent(hwnd: int) -> bytes:
    """
    Capture window via PrintWindow(PW_RENDERFULLCONTENT).
    If the window is minimized, temporarily shows it without activating,
    waits for WebView2 to re-render, captures, then minimizes again.
    Returns raw PNG bytes.
    """
    from PIL import Image  # type: ignore[import]

    was_minimized = bool(_user32.IsIconic(hwnd))
    if was_minimized:
        _user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)
        time.sleep(1.5)  # let WebView2 render

    rect = ctypes.wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right  - rect.left
    h = rect.bottom - rect.top

    if w < 10 or h < 10:
        if was_minimized:
            _user32.ShowWindow(hwnd, _SW_SHOWMINIMIZED)
        raise RuntimeError(f"Window too small for screenshot: {w}x{h}")

    hwnd_dc = _user32.GetDC(hwnd)
    mem_dc  = _gdi32.CreateCompatibleDC(hwnd_dc)
    bmp     = _gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    old_bmp = _gdi32.SelectObject(mem_dc, bmp)

    try:
        _user32.PrintWindow(hwnd, mem_dc, _PW_RENDERFULLCONTENT)

        bmi = _BITMAPINFOHEADER()
        bmi.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth       = w
        bmi.biHeight      = -h   # negative = top-down DIB
        bmi.biPlanes      = 1
        bmi.biBitCount    = 32
        bmi.biCompression = 0    # BI_RGB

        pixel_buf = ctypes.create_string_buffer(w * h * 4)
        _gdi32.GetDIBits(mem_dc, bmp, 0, h, pixel_buf, ctypes.byref(bmi), 0)
    finally:
        _gdi32.SelectObject(mem_dc, old_bmp)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(hwnd, hwnd_dc)

    # BGRA → RGBA
    data = bytearray(pixel_buf.raw)
    for i in range(0, len(data), 4):
        data[i], data[i + 2] = data[i + 2], data[i]

    if was_minimized:
        _user32.ShowWindow(hwnd, _SW_SHOWMINIMIZED)

    img = Image.frombytes("RGBA", (w, h), bytes(data))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _find_hwnd_by_pid(pid: int) -> int | None:
    """Enumerate visible top-level windows and return HWND belonging to pid."""
    found: list[int] = []
    pid_out = ctypes.c_ulong(0)

    def _cb(hwnd: int, _: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if pid_out.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value.strip():
                found.append(hwnd)
        return True

    _EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    _user32.EnumWindows(_EnumProc(_cb), 0)
    return found[0] if found else None


# ─── Page-load JS snippets called after navigate ─────────────────────────────

_PAGE_LOAD_JS: dict[str, str] = {
    "spot":       "_loadSpotPageData();",
    "futures":    "_loadFuturesPositions();",
    "analytics":  "_loadAnalytics();",
    "data":       "_loadDataPage();",
    "models":     "_loadModelsData();",
    "ops":        "_loadOpsPage();",
    "backtest":   "_loadBacktestPage();",
    "orderbook":  "_pollOrderbook();",
    "logs":       "_pollLogs();",
    "home":       "",
    "market":     "",
    "telegram":   "_loadTelegramPage();",
    "settings":   "settingsLoad();",
}


# ─── HTTP handler ─────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    server: "BotikDevHTTPServer"
    protocol_version = "HTTP/1.1"  # needed for urllib compatibility

    # suppress default per-request log lines
    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("dev_server: " + fmt, *args)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_png(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, msg: str, status: int = 500) -> None:
        self._send_json({"ok": False, "error": msg}, status)

    def _read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ── routing ─────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path == "/ping":
            self._handle_ping()
        elif path == "/screenshot":
            self._handle_screenshot()
        elif path == "/rebuild-html":
            self._handle_rebuild_html()
        elif path.startswith("/api/"):
            method = path[5:]
            self._handle_api(method, {})
        else:
            self._send_error_json(f"Unknown route: {path}", 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        body = self._read_body_json()
        if path == "/navigate":
            self._handle_navigate(body)
        elif path == "/inspect":
            self._handle_inspect(body)
        elif path.startswith("/api/"):
            method = path[5:]
            self._handle_api(method, body)
        else:
            self._send_error_json(f"Unknown route: {path}", 404)

    # ── handlers ─────────────────────────────────────────────────────────────

    def _handle_ping(self) -> None:
        srv = self.server.botik_server
        self._send_json({
            "ok":       True,
            "version":  srv.version,
            "uptime_s": int(time.monotonic() - srv.start_time),
            "port":     DEV_PORT,
        })

    def _handle_screenshot(self) -> None:
        srv = self.server.botik_server
        hwnd = srv.get_hwnd()
        if not hwnd:
            self._send_error_json("Window HWND not found — is botik running?")
            return
        try:
            png = _capture_hwnd_silent(hwnd)
            self._send_png(png)
            log.debug("Screenshot captured, %d bytes", len(png))
        except Exception as exc:
            log.exception("Screenshot failed")
            self._send_error_json(str(exc))

    def _handle_rebuild_html(self) -> None:
        """GET /rebuild-html — reassemble dashboard from component pages and save to disk.

        Writes the assembled HTML to dashboard_preview.html.
        The window must be restarted to pick up the changes.
        """
        try:
            from .api_helpers import assemble_dashboard_html
            html = assemble_dashboard_html()
            self._send_json({"ok": True, "bytes": len(html), "note": "restart to apply"})
            log.info("[dev_server] HTML rebuilt (%d bytes)", len(html))
        except Exception as exc:
            log.exception("rebuild-html failed")
            self._send_error_json(str(exc))

    def _handle_navigate(self, body: dict) -> None:
        tab = str(body.get("tab", "")).strip()
        if not tab:
            self._send_error_json("Missing 'tab' field", 400)
            return
        srv = self.server.botik_server
        window = srv.window
        if not window:
            self._send_error_json("pywebview window not yet available")
            return
        extra_js = _PAGE_LOAD_JS.get(tab, "")
        js = f"_navigateToPage('{tab}'); {extra_js}"
        try:
            window.evaluate_js(js)
            log.debug("Navigated to tab=%s", tab)
            self._send_json({"ok": True, "tab": tab})
        except Exception as exc:
            log.exception("navigate evaluate_js failed")
            self._send_error_json(str(exc))

    def _handle_inspect(self, body: dict) -> None:
        """POST /inspect {"js": "<script>"} — run JS in WebView2, return result as JSON."""
        script = str(body.get("js", "")).strip()
        if not script:
            self._send_error_json("Missing 'js' field", 400)
            return
        srv = self.server.botik_server
        window = srv.window
        if not window:
            self._send_error_json("pywebview window not yet available")
            return
        try:
            result = window.evaluate_js(script)
            self._send_json({"ok": True, "result": result})
        except Exception as exc:
            log.exception("inspect js execution failed")
            self._send_error_json(str(exc))

    def _handle_api(self, method: str, kwargs: dict) -> None:
        srv = self.server.botik_server
        api = srv.api
        if not api:
            self._send_error_json("DashboardAPI not available")
            return
        fn = getattr(api, method, None)
        if fn is None or not callable(fn) or method.startswith("_"):
            self._send_error_json(f"Method not found: {method}", 404)
            return
        try:
            result = fn(**kwargs) if kwargs else fn()
            # API methods return JSON strings; pass through as-is
            if isinstance(result, str):
                body = result.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json(result)
        except Exception as exc:
            log.exception("api/%s failed", method)
            self._send_error_json(str(exc))


# ─── Server class ─────────────────────────────────────────────────────────────

class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BotikDevServer:
    """
    Wraps the HTTP server with lifecycle management.
    Call start() once; call set_window(window) after pywebview creates the window.
    """

    def __init__(self, api: Any, version: str) -> None:
        self.api        = api
        self.version    = version
        self.window: Any | None = None
        self.start_time = time.monotonic()
        self._hwnd_cache: int | None   = None
        self._hwnd_pid:   int          = os.getpid()
        self._http: _ThreadedHTTPServer | None = None

    # ── public API ────────────────────────────────────────────────────────

    def set_window(self, window: Any) -> None:
        """Call after webview.create_window() to attach the pywebview window."""
        self.window = window

    def get_hwnd(self) -> int | None:
        """Return (and cache) the HWND of this process's main window."""
        if self._hwnd_cache and _user32.IsWindow(self._hwnd_cache):
            return self._hwnd_cache
        hwnd = _find_hwnd_by_pid(self._hwnd_pid)
        if hwnd:
            self._hwnd_cache = hwnd
        return hwnd

    def start(self) -> None:
        """Start the HTTP server on a daemon thread. Non-blocking."""
        try:
            http_server = _ThreadedHTTPServer(("127.0.0.1", DEV_PORT), _Handler)
            http_server.botik_server = self  # type: ignore[attr-defined]
            self._http = http_server
            t = threading.Thread(target=http_server.serve_forever, daemon=True, name="botik-dev-srv")
            t.start()
            log.info("[dev_server] Listening on http://127.0.0.1:%d", DEV_PORT)
        except OSError as exc:
            log.warning("[dev_server] Could not start on port %d: %s", DEV_PORT, exc)

    def stop(self) -> None:
        if self._http:
            self._http.shutdown()
            self._http = None
