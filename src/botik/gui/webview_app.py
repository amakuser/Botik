"""
pywebview-based Dashboard for Botik.

Replaces the tkinter GUI with a native WebView2 window serving dashboard_preview.html.
Python exposes DashboardAPI to JavaScript via window.pywebview.api.*

Module layout
─────────────
api_helpers.py       — ROOT_DIR, paths, _load_yaml, _read_env_map, …
api_db_mixin.py      — DbMixin: static SQLite helper methods
api_models_mixin.py  — ModelsMixin: ML model reading + get_models
api_spot_mixin.py    — SpotMixin: spot reading + get_spot_* + sell_*
api_futures_mixin.py — FuturesMixin: futures reading + get_futures_* + close/update
api_system_mixin.py  — SystemMixin: get_snapshot, get_system_status, get_logs
api_settings_mixin.py — SettingsMixin: load/save settings, api/db/tg checks
api_trading_mixin.py — TradingMixin: start/stop trading & ML training
webview_app.py       — ManagedProcess + DashboardAPI (all mixins) + main()
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

# Ensure project root is on sys.path when run directly
_PROJECT_ROOT = None
try:
    from pathlib import Path as _Path
    _PROJECT_ROOT = _Path(__file__).resolve().parents[3]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
except Exception:
    pass

import webview

from src.botik.version import get_app_version_label
from src.botik.storage.schema import bootstrap_db

from .api_helpers import (
    ROOT_DIR, HTML_PATH,
    STRATEGY_MODE_ORDER,
    _resolve_project_root,
)
from .api_db_mixin import DbMixin
from .api_models_mixin import ModelsMixin
from .api_spot_mixin import SpotMixin
from .api_futures_mixin import FuturesMixin
from .api_system_mixin import SystemMixin
from .api_settings_mixin import SettingsMixin
from .api_trading_mixin import TradingMixin
from .api_data_mixin import DataMixin
from .api_ticker_mixin import TickerMixin
from .api_analytics_mixin import AnalyticsMixin
from .api_backtest_mixin import BacktestMixin
from .api_balance_mixin import BalanceMixin
from .dev_server import BotikDevServer

log = logging.getLogger("botik.webview")


# ─────────────────────────────────────────────────────────────
#  ManagedProcess — wraps a subprocess with start/stop/state
# ─────────────────────────────────────────────────────────────

class ManagedProcess:
    def __init__(self, name: str, on_output) -> None:
        self.name        = name
        self._on_output  = on_output
        self._proc: subprocess.Popen | None = None
        self._lock       = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        with self._lock:
            return self._proc.pid if self._proc else None

    @property
    def state(self) -> str:
        with self._lock:
            if self._proc is None:
                return "stopped"
            rc = self._proc.poll()
            if rc is None:
                return "running"
            return "error" if rc != 0 else "stopped"

    def start(self, cmd: list[str]) -> tuple[bool, str]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return False, "already_running"
            try:
                # CREATE_NO_WINDOW prevents a flash of console on Windows
                _flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(ROOT_DIR),
                    creationflags=_flags,
                )
                threading.Thread(target=self._read_loop, daemon=True).start()
                return True, "ok"
            except Exception as exc:
                self._on_output(f"[{self.name}] start error: {exc}")
                return False, str(exc)

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

    def _read_loop(self) -> None:
        try:
            proc = self._proc
            if proc and proc.stdout:
                for line in proc.stdout:
                    self._on_output(f"[{self.name}] {line.rstrip()}")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  DashboardAPI — exposed to JavaScript via window.pywebview.api
# ─────────────────────────────────────────────────────────────

class DashboardAPI(
    DbMixin,
    ModelsMixin,
    SpotMixin,
    FuturesMixin,
    SystemMixin,
    SettingsMixin,
    TradingMixin,
    DataMixin,
    TickerMixin,
    AnalyticsMixin,
    BacktestMixin,
    BalanceMixin,
):
    """All public methods are callable from JS via window.pywebview.api.*"""

    def __init__(self) -> None:
        self._app_version  = get_app_version_label()
        self._start_time   = time.monotonic()
        self._log_buffer: deque[dict[str, str]] = deque(maxlen=600)
        self._buf_lock     = threading.Lock()

        self._trading_processes: dict[str, ManagedProcess] = {
            mode: ManagedProcess(f"trading:{mode}", self._add_log)
            for mode in STRATEGY_MODE_ORDER
        }
        self._ml_process         = ManagedProcess("ml",         self._add_log)
        self._ml_futures_process = ManagedProcess("ml_futures", self._add_log)
        self._ml_spot_process    = ManagedProcess("ml_spot",    self._add_log)
        self._backfill_process   = ManagedProcess("backfill",   self._add_log)
        self._livedata_process   = ManagedProcess("livedata",   self._add_log)

        self._init_ticker()
        self._init_balance()
        self._add_log("[sys] Dashboard loaded", "sys")

    # ── Core internal helpers ─────────────────────────────────

    def _add_log(self, msg: str, channel: str = "sys") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if channel == "sys" and msg.startswith("["):
            tag = msg[1:msg.find("]")] if "]" in msg else ""
            if "spot" in tag:
                channel = "spot"
            elif "ml" in tag or "training" in tag:
                channel = "ml"
            elif "futures" in tag:
                channel = "futures"
            elif "telegram" in tag:
                channel = "telegram"
        entry = {"ts": ts, "ch": channel, "msg": msg}
        with self._buf_lock:
            self._log_buffer.append(entry)

    def _uptime_str(self) -> str:
        secs = int(time.monotonic() - self._start_time)
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _trading_state(self) -> str:
        states = {p.state for p in self._trading_processes.values()}
        if "running" in states:
            return "running"
        if "error"   in states:
            return "error"
        return "stopped"

    def _running_modes(self) -> list[str]:
        return [m for m, p in self._trading_processes.items() if p.running]


# ─────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not HTML_PATH.exists():
        raise FileNotFoundError(f"dashboard_preview.html not found at: {HTML_PATH}")

    # Pin DB_URL to SQLite so that all sub-processes write to the same DB
    db_url = os.environ.get("DB_URL", "")
    if not db_url or db_url.startswith("sqlite"):
        from pathlib import Path
        sqlite_path = ROOT_DIR / "data" / "botik.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["DB_URL"] = f"sqlite:///{sqlite_path}"

    bootstrap_db()

    api     = DashboardAPI()
    version = api._app_version

    dev_server = BotikDevServer(api=api, version=version)
    dev_server.start()

    html_content = HTML_PATH.read_text(encoding="utf-8")
    window = webview.create_window(
        title=f"Botik Dashboard  {version}",
        html=html_content,
        js_api=api,
        width=1380,
        height=880,
        min_size=(1020, 700),
        background_color="#03070F",
        text_select=False,
    )

    log.info("Starting pywebview window — Botik Dashboard %s", version)

    dev_server.set_window(window)

    def _bootstrap_js(win) -> None:
        """Poll for pywebview bridge readiness, then call _initAPI() in the page.

        pywebviewready and HTML-side polling can miss the bridge in pywebview 6.x
        on Windows.  This runs in a background thread and force-calls _initAPI()
        from Python as soon as window.pywebview.api is confirmed available.
        """
        for _ in range(50):  # up to 10 seconds
            time.sleep(0.2)
            try:
                ready = win.evaluate_js("!!(window.pywebview && window.pywebview.api)")
                if ready:
                    win.evaluate_js("if (typeof _initAPI === 'function') _initAPI();")
                    log.info("[BRIDGE] _initAPI() called from Python — bridge is live")
                    return
            except Exception:
                pass
        log.warning("[BRIDGE] pywebview.api not available after 10s")

    webview.start(debug=False, func=_bootstrap_js, args=[window])
