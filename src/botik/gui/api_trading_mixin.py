"""
TradingMixin — start/stop trading processes and ML training.

Public API: start_trading, stop_trading, stop_all_trading,
            start_training, stop_training.
"""
from __future__ import annotations

import json
import logging
import sys

from .api_helpers import _detect_launcher_mode, _build_subprocess_cmd

log = logging.getLogger("botik.webview")


class TradingMixin:
    """Mixin providing trading control methods to DashboardAPI."""

    def start_trading(self, mode: str = "spot_spread") -> str:
        mode = str(mode).strip()
        proc = self._trading_processes.get(mode)  # type: ignore[attr-defined]
        if not proc:
            return json.dumps({"ok": False, "error": f"unknown mode: {mode}"})
        if proc.running:
            return json.dumps({"ok": False, "error": "already_running"})

        py       = sys.executable
        launcher = _detect_launcher_mode()

        if launcher == "packaged":
            cmd = [py, "--nogui", "--role", "trading", "--mode", mode]
        elif mode == "futures_spike_reversal":
            cmd = [py, "-m", "src.botik.runners.futures_runner"]
        else:
            cmd = [py, "-m", "src.botik.runners.spot_runner"]

        ok, msg = proc.start(cmd)
        self._add_log(  # type: ignore[attr-defined]
            f"[ui] start_trading mode={mode} ok={ok} msg={msg}",
            "futures" if "futures" in mode else "spot",
        )
        return json.dumps({"ok": ok, "msg": msg})

    def stop_trading(self, mode: str = "spot_spread") -> str:
        mode = str(mode).strip()
        proc = self._trading_processes.get(mode)  # type: ignore[attr-defined]
        if not proc:
            return json.dumps({"ok": False, "error": f"unknown mode: {mode}"})
        proc.stop()
        self._add_log(f"[ui] stop_trading mode={mode}", "spot")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    def stop_all_trading(self) -> str:
        for p in self._trading_processes.values():  # type: ignore[attr-defined]
            p.stop()
        self._add_log("[ui] stop_all_trading", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    def start_training(self, ml_mode: str = "train") -> str:
        if self._ml_process.running:  # type: ignore[attr-defined]
            return json.dumps({"ok": False, "error": "already_running"})
        py       = sys.executable
        launcher = _detect_launcher_mode()
        if launcher == "packaged":
            cmd = [py, "--nogui", "--role", "ml"]
        else:
            cmd = [py, "-m", "src.botik.runners.data_runner"]
        ok, msg = self._ml_process.start(cmd)  # type: ignore[attr-defined]
        self._add_log(f"[ui] start_training mode={ml_mode} ok={ok}", "ml")  # type: ignore[attr-defined]
        return json.dumps({"ok": ok, "msg": msg})

    def stop_training(self) -> str:
        self._ml_process.stop()  # type: ignore[attr-defined]
        self._add_log("[ui] stop_training", "ml")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    def start_training_scope(self, scope: str) -> str:
        scope = str(scope).strip().lower()
        if scope not in ("futures", "spot"):
            return json.dumps({"ok": False, "error": "invalid_scope"})
        proc = (
            self._ml_futures_process if scope == "futures"  # type: ignore[attr-defined]
            else self._ml_spot_process                      # type: ignore[attr-defined]
        )
        if proc.running:
            return json.dumps({"ok": False, "error": "already_running"})
        cmd = _build_subprocess_cmd("training", ["--scope", scope])
        ok, msg = proc.start(cmd)
        self._add_log(f"[ui] start_training_scope scope={scope} ok={ok}", f"ml_{scope}")  # type: ignore[attr-defined]
        return json.dumps({"ok": ok, "msg": msg})

    def stop_training_scope(self, scope: str) -> str:
        scope = str(scope).strip().lower()
        if scope not in ("futures", "spot"):
            return json.dumps({"ok": False, "error": "invalid_scope"})
        proc = (
            self._ml_futures_process if scope == "futures"  # type: ignore[attr-defined]
            else self._ml_spot_process                      # type: ignore[attr-defined]
        )
        proc.stop()
        self._add_log(f"[ui] stop_training_scope scope={scope}", f"ml_{scope}")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})
