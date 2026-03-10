"""
Desktop GUI launcher for local operation (Windows/Linux desktop).

Features:
- Start/stop trading and ML processes.
- Live logs inside the app.
- Preflight run button.
- Settings tab to edit .env and config.yaml directly.
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk, messagebox

import yaml

from src.botik.risk.position import apply_fill
from src.botik.version import get_app_version_label
from src.botik.gui.theme import apply_dark_theme
from src.botik.gui.ui_components import card, labeled_combobox, labeled_entry
from src.botik.utils.runtime import runtime_root


ROOT_DIR = runtime_root(__file__, levels_up=3)
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
GUI_LOG_PATH = ROOT_DIR / "logs" / "gui.log"

STRATEGY_PRESET_LABELS: dict[str, str] = {
    "Spot Spread (Maker)": "spot_spread",
    "Spot Spike Burst": "spot_spike",
    "Futures Spike Reversal": "futures_spike_reversal",
}
STRATEGY_PRESET_MODES = {mode: label for label, mode in STRATEGY_PRESET_LABELS.items()}
STRATEGY_MODE_ORDER = ["spot_spread", "spot_spike", "futures_spike_reversal"]

STRATEGY_MODE_RUNTIME: dict[str, dict[str, str]] = {
    "spot_spread": {"category": "spot", "runtime_strategy": "spread_maker", "strategy_label": "SPREAD"},
    "spot_spike": {"category": "spot", "runtime_strategy": "spread_maker", "strategy_label": "SPIKE_BURST"},
    "futures_spike_reversal": {
        "category": "linear",
        "runtime_strategy": "spike_reversal",
        "strategy_label": "SPIKE_REV",
    },
}


# Windows sleep control flags (SetThreadExecutionState).
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_AWAYMODE_REQUIRED = 0x00000040


def _default_python() -> str:
    win_venv = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    posix_venv = ROOT_DIR / ".venv" / "bin" / "python"
    if win_venv.exists():
        return str(win_venv)
    if posix_venv.exists():
        return str(posix_venv)
    return sys.executable


def _read_env_map(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip()
    return data


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    consumed: set[str] = set()
    out: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                consumed.add(key)
                continue
        out.append(line)

    for key, val in updates.items():
        if key not in consumed:
            out.append(f"{key}={val}")

    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _table_exists_local(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (str(table_name),),
    ).fetchone()
    return bool(row)


def _table_columns_local(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(r[1]) for r in rows if len(r) > 1 and r[1]}


def _latest_table_ts(
    conn: sqlite3.Connection,
    table_name: str,
    *,
    preferred_columns: tuple[str, ...] = ("updated_at_utc", "created_at_utc", "finished_at_utc", "started_at_utc"),
) -> str:
    if not _table_exists_local(conn, table_name):
        return "-"
    cols = _table_columns_local(conn, table_name)
    ts_col = next((c for c in preferred_columns if c in cols), "")
    if not ts_col:
        return "-"
    try:
        row = conn.execute(f"SELECT COALESCE(MAX({ts_col}), '') FROM {table_name}").fetchone()
    except sqlite3.Error:
        return "-"
    value = str((row[0] if row else "") or "").strip()
    return value or "-"


def runtime_capabilities_for_mode(mode: str) -> dict[str, str]:
    mode_norm = str(mode or "").strip().lower()
    if mode_norm == "paper":
        return {"reconciliation": "unsupported", "protection": "unsupported"}
    return {"reconciliation": "supported", "protection": "supported"}


def load_runtime_ops_status_snapshot(db_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "spot_holdings_freshness": "-",
        "futures_positions_freshness": "-",
        "futures_orders_freshness": "-",
        "reconciliation_issues_freshness": "-",
        "futures_funding_freshness": "-",
        "futures_liq_snapshots_freshness": "-",
        "reconciliation_last_status": "skipped",
        "reconciliation_last_timestamp": "-",
        "reconciliation_last_trigger": "-",
        "reconciliation_summary_issues": None,
        "futures_protection_counts": {},
        "futures_protection_line": "none",
        "futures_risk_telemetry_line": "funding=none | liq=none",
    }
    if not db_path.exists():
        return out
    conn = sqlite3.connect(str(db_path))
    try:
        out["spot_holdings_freshness"] = _latest_table_ts(conn, "spot_holdings")
        out["futures_positions_freshness"] = _latest_table_ts(conn, "futures_positions")
        out["futures_orders_freshness"] = _latest_table_ts(conn, "futures_open_orders")
        out["reconciliation_issues_freshness"] = _latest_table_ts(conn, "reconciliation_issues")
        out["futures_funding_freshness"] = _latest_table_ts(conn, "futures_funding_events")
        out["futures_liq_snapshots_freshness"] = _latest_table_ts(conn, "futures_liquidation_risk_snapshots")

        funding_line = "funding=none"
        if _table_exists_local(conn, "futures_funding_events"):
            funding_row = conn.execute(
                """
                SELECT COALESCE(symbol, ''), COALESCE(funding_fee, 0), COALESCE(funding_time_ms, 0)
                FROM futures_funding_events
                ORDER BY COALESCE(funding_time_ms, 0) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if funding_row:
                funding_line = (
                    f"funding={str(funding_row[0] or '-')} fee={float(funding_row[1] or 0):.6f}"
                    f" t={int(funding_row[2] or 0)}"
                )

        liq_line = "liq=none"
        if _table_exists_local(conn, "futures_liquidation_risk_snapshots"):
            liq_row = conn.execute(
                """
                SELECT COALESCE(symbol, ''), distance_to_liq_bps, COALESCE(created_at_utc, '')
                FROM futures_liquidation_risk_snapshots
                ORDER BY created_at_utc DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if liq_row:
                dist = liq_row[1]
                dist_text = "-" if dist is None else f"{float(dist):.2f}bps"
                liq_line = f"liq={str(liq_row[0] or '-')} dist={dist_text} @ {str(liq_row[2] or '-')}"
        out["futures_risk_telemetry_line"] = f"{funding_line} | {liq_line}"

        if _table_exists_local(conn, "reconciliation_runs"):
            row = conn.execute(
                """
                SELECT
                    COALESCE(status, ''),
                    COALESCE(trigger_source, ''),
                    COALESCE(finished_at_utc, started_at_utc, ''),
                    COALESCE(summary_json, '')
                FROM reconciliation_runs
                ORDER BY COALESCE(finished_at_utc, started_at_utc) DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                status = str(row[0] or "").strip().lower() or "skipped"
                out["reconciliation_last_status"] = status
                out["reconciliation_last_trigger"] = str(row[1] or "").strip() or "-"
                out["reconciliation_last_timestamp"] = str(row[2] or "").strip() or "-"
                summary_text = str(row[3] or "").strip()
                if summary_text:
                    try:
                        summary = json.loads(summary_text)
                    except Exception:
                        summary = {}
                    if isinstance(summary, dict):
                        issues_value = summary.get("issues_created")
                        if isinstance(issues_value, (int, float)):
                            out["reconciliation_summary_issues"] = int(issues_value)

        if _table_exists_local(conn, "futures_positions"):
            rows = conn.execute(
                """
                SELECT LOWER(COALESCE(protection_status, '')), COUNT(*)
                FROM futures_positions
                WHERE ABS(COALESCE(qty, 0.0)) > 0
                GROUP BY LOWER(COALESCE(protection_status, ''))
                """
            ).fetchall()
            counts: dict[str, int] = {}
            for status, count in rows:
                status_key = str(status or "").strip() or "unknown"
                counts[status_key] = int(count or 0)
            out["futures_protection_counts"] = counts
            if counts:
                preferred = ["protected", "pending", "repairing", "unprotected", "failed", "unknown"]
                parts: list[str] = []
                for key in preferred:
                    if key in counts:
                        parts.append(f"{key}={counts[key]}")
                for key in sorted(k for k in counts.keys() if k not in preferred):
                    parts.append(f"{key}={counts[key]}")
                out["futures_protection_line"] = " | ".join(parts)
    except sqlite3.Error:
        return out
    finally:
        conn.close()
    return out


class ManagedProcess:
    def __init__(self, name: str, on_output: Callable[[str], None]) -> None:
        self.name = name
        self.on_output = on_output
        self.proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self.last_exit_code: int | None = None
        self.state: str = "stopped"  # stopped | running | error

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
        if self.running:
            return False
        self.last_exit_code = None
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.state = "running"
        self.on_output(f"[{self.name}] started: {' '.join(cmd)}")
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        return True

    def _read_output(self) -> None:
        if self.proc is None or self.proc.stdout is None:
            return
        for line in self.proc.stdout:
            self.on_output(f"[{self.name}] {line.rstrip()}")
        code = self.proc.wait()
        self.last_exit_code = code
        self.state = "stopped" if code == 0 else "error"
        self.on_output(f"[{self.name}] exited with code {code}")

    def stop(self) -> bool:
        if not self.running or self.proc is None:
            return False
        self.on_output(f"[{self.name}] stopping...")
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.on_output(f"[{self.name}] force kill")
            self.proc.kill()
        self.last_exit_code = 0
        self.state = "stopped"
        self.on_output(f"[{self.name}] stopped")
        return True


class SleepBlocker:
    """
    Keeps Windows system awake while GUI is running.
    """

    def __init__(self, on_output: Callable[[str], None]) -> None:
        self.on_output = on_output
        self.enabled = False
        self.flags = 0

    def enable(self) -> None:
        if os.name != "nt":
            return
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_AWAYMODE_REQUIRED
            result = kernel32.SetThreadExecutionState(flags)
            if not result:
                # Fallback for systems where Away Mode is not supported.
                flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
                result = kernel32.SetThreadExecutionState(flags)
            if result:
                self.enabled = True
                self.flags = flags
                self.on_output("[ui] sleep blocker enabled")
            else:
                self.on_output("[ui] warning: failed to enable sleep blocker")
        except Exception as exc:
            self.on_output(f"[ui] warning: sleep blocker error: {exc}")

    def disable(self) -> None:
        if os.name != "nt":
            return
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            if self.enabled:
                self.on_output("[ui] sleep blocker disabled")
        except Exception as exc:
            self.on_output(f"[ui] warning: failed to disable sleep blocker: {exc}")
        finally:
            self.enabled = False
            self.flags = 0


class BotikGui:
    def __init__(self) -> None:
        self.app_version = get_app_version_label()
        self.root = tk.Tk()
        self.root.title(f"Botik Desktop {self.app_version}")
        self.root.geometry("1180x790")
        self.root.minsize(1020, 700)
        if os.name == "nt":
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.trading_processes: dict[str, ManagedProcess] = {
            mode: ManagedProcess(f"trading:{mode}", self._enqueue_log)
            for mode in STRATEGY_MODE_ORDER
        }
        # Backward-compatible alias for legacy code paths.
        self.trading = self.trading_processes["spot_spread"]
        self.ml = ManagedProcess("ml", self._enqueue_log)
        self.sleep_blocker = SleepBlocker(self._enqueue_log)

        self.python_var = tk.StringVar(value=_default_python())
        self.config_var = tk.StringVar(value=str(DEFAULT_CONFIG_PATH))
        self.runtime_python_name_var = tk.StringVar(value="")
        self.runtime_config_name_var = tk.StringVar(value="")

        self.env_vars: dict[str, tk.StringVar] = {
            "TELEGRAM_BOT_TOKEN": tk.StringVar(),
            "TELEGRAM_CHAT_ID": tk.StringVar(),
            "BYBIT_API_KEY": tk.StringVar(),
            "BYBIT_API_SECRET_KEY": tk.StringVar(),
            "BYBIT_RSA_PRIVATE_KEY_PATH": tk.StringVar(),
        }

        self.cfg_execution_mode = tk.StringVar(value="paper")
        self.cfg_start_paused = tk.BooleanVar(value=True)
        self.cfg_bybit_host = tk.StringVar(value="api-demo.bybit.com")
        self.cfg_ws_host = tk.StringVar(value="stream.bybit.com")
        self.cfg_market_category = tk.StringVar(value="spot")
        self.cfg_runtime_strategy = tk.StringVar(value="spread_maker")
        self.cfg_symbols = tk.StringVar(value="BTCUSDT,ETHUSDT")
        self.cfg_target_profit = tk.StringVar(value="0.0002")
        self.cfg_safety_buffer = tk.StringVar(value="0.0001")
        self.cfg_stop_loss = tk.StringVar(value="0.003")
        self.cfg_take_profit = tk.StringVar(value="0.005")
        self.cfg_hold_timeout = tk.StringVar(value="180")
        self.cfg_min_active_usdt = tk.StringVar(value="1.0")
        self.cfg_maker_only = tk.BooleanVar(value=True)
        self.strategy_mode_var = tk.StringVar(value=STRATEGY_PRESET_MODES["spot_spread"])
        self.enable_spot_spread_var = tk.BooleanVar(value=True)
        self.enable_spot_spike_var = tk.BooleanVar(value=False)
        self.enable_futures_spike_var = tk.BooleanVar(value=False)
        self.spike_threshold_bps_var = tk.StringVar(value="10")
        self.spike_min_trades_var = tk.StringVar(value="6")
        self.spike_slices_var = tk.StringVar(value="6")
        self.spike_qty_scale_var = tk.StringVar(value="0.20")
        self.spike_scanner_top_k_var = tk.StringVar(value="120")
        self.spike_universe_size_var = tk.StringVar(value="240")
        self.spike_ml_interval_var = tk.StringVar(value="90")

        self.balance_total_var = tk.StringVar(value="n/a")
        self.balance_available_var = tk.StringVar(value="n/a")
        self.balance_wallet_var = tk.StringVar(value="n/a")
        self.open_orders_var = tk.StringVar(value="0")
        self.api_status_var = tk.StringVar(value="not checked")
        self.snapshot_time_var = tk.StringVar(value="-")
        self.runtime_capabilities_var = tk.StringVar(value="capabilities: n/a")
        self.reconciliation_status_var = tk.StringVar(value="reconciliation: n/a")
        self.panel_freshness_var = tk.StringVar(value="freshness: n/a")
        self.futures_protection_status_var = tk.StringVar(value="protection: n/a")
        self.ml_model_id_var = tk.StringVar(value="bootstrap")
        self.ml_training_state_var = tk.StringVar(value="idle")
        self.ml_progress_text_var = tk.StringVar(value="0%")
        self.ml_net_edge_var = tk.StringVar(value="n/a")
        self.ml_win_rate_var = tk.StringVar(value="n/a")
        self.ml_fill_rate_var = tk.StringVar(value="n/a")
        self.ml_fill_details_var = tk.StringVar(value="0/0 signals")
        self.ml_metrics_compact_var = tk.StringVar(value="edge=n/a | win=n/a | fill=n/a")
        self.stats_orders_total_var = tk.StringVar(value="0")
        self.stats_outcomes_total_var = tk.StringVar(value="0")
        self.stats_positive_var = tk.StringVar(value="0")
        self.stats_negative_var = tk.StringVar(value="0")
        self.stats_neutral_var = tk.StringVar(value="0")
        self.stats_net_pnl_var = tk.StringVar(value="0.000000")
        self.stats_avg_pnl_var = tk.StringVar(value="0.000000")
        self.stats_balance_events_var = tk.StringVar(value="0")
        self.stats_balance_delta_var = tk.StringVar(value="0.000000")
        self.models_summary_var = tk.StringVar(value="models=0")
        self.ml_training_paused = False
        self.ml_runtime_mode = "bootstrap"
        self._ml_progress_running = False
        self._ml_chart_points: deque[float] = deque(maxlen=60)
        self._stats_cum_pnl_points: deque[float] = deque(maxlen=240)
        self.stats_pnl_canvas: tk.Canvas | None = None
        self.stats_history_tree: ttk.Treeview | None = None
        self.stats_balance_tree: ttk.Treeview | None = None
        self.stats_spot_holdings_tree: ttk.Treeview | None = None
        self.stats_futures_positions_tree: ttk.Treeview | None = None
        self.stats_futures_orders_tree: ttk.Treeview | None = None
        self.stats_reconciliation_issues_tree: ttk.Treeview | None = None
        self.models_tree: ttk.Treeview | None = None
        self.log_text_full: tk.Text | None = None
        self.log_level_filter_combo: ttk.Combobox | None = None
        self.log_pair_filter_combo: ttk.Combobox | None = None
        self.log_jump_main: ttk.Button | None = None
        self.log_jump_full: ttk.Button | None = None
        self.log_scroll_main: ttk.Scrollbar | None = None
        self.log_scroll_full: ttk.Scrollbar | None = None
        self.log_filter_level_var = tk.StringVar(value="ALL")
        self.log_filter_pair_var = tk.StringVar(value="ALL")
        self.log_filter_query_var = tk.StringVar(value="")
        self._log_messages: deque[str] = deque(maxlen=50_000)
        self._known_log_pairs: set[str] = set()
        self._log_autoscroll_main = True
        self._log_autoscroll_full = True
        self._log_menu_target: tk.Text | None = None
        self._runtime_refresh_interval_ms = 5000
        self._max_ui_log_lines_main = 1800
        self._max_ui_log_lines_full = 8000
        self._max_log_batch_per_tick = 280
        self._log_backlog_soft_limit = 5000
        self._log_backlog_keep = 2000
        self._suppressed_pairfilter_logs = 0
        self._suppressed_policy_logs = 0
        self._suppressed_logs_last_flush = time.monotonic()
        self.notebook: ttk.Notebook | None = None
        self.statistics_notebook: ttk.Notebook | None = None
        self.settings_notebook: ttk.Notebook | None = None
        self.settings_main_tab: ttk.Frame | None = None
        self._ui_colors: dict[str, str] = {}
        self._heavy_refresh_min_interval_sec = 12.0
        self._last_heavy_refresh_ts = 0.0
        self._cached_heavy_snapshot: dict[str, Any] = {
            "history_rows_full": [],
            "history_total": 0,
            "outcomes_summary": {
                "total": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "sum_net_pnl_quote": 0.0,
                "avg_net_pnl_quote": 0.0,
            },
            "stats_cum_pnl_chart": [],
            "balance_rows": [],
            "balance_delta_total": 0.0,
            "spot_holdings_rows": [],
            "futures_positions_rows": [],
            "futures_orders_rows": [],
            "reconciliation_issue_rows": [],
            "model_rows": [],
        }

        self._suspend_autosave = False
        self._autosave_env_after_id: str | None = None
        self._autosave_cfg_after_id: str | None = None
        self._runtime_refresh_lock = threading.Lock()
        self._runtime_refresh_inflight = False
        self._telegram_thread: threading.Thread | None = None
        self._telegram_stop_event: threading.Event | None = None
        self._telegram_missing_token_reported = False

        self._setup_style()
        self._build_ui()
        self._setup_edit_shortcuts()
        self._setup_autosave()
        self.load_settings()
        self._refresh_runtime_labels()
        self._start_telegram_control_if_configured()
        self.sleep_blocker.enable()

        self._update_status()
        self._drain_logs()
        self._schedule_runtime_refresh(initial_delay_ms=1000)
        self.root.bind("<Escape>", self._toggle_window_state)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_edit_shortcuts(self) -> None:
        self._edit_menu_target: tk.Widget | None = None
        self.edit_menu = tk.Menu(self.root, tearoff=0)
        self.edit_menu.add_command(label="Cut", command=lambda: self._edit_action("cut"))
        self.edit_menu.add_command(label="Copy", command=lambda: self._edit_action("copy"))
        self.edit_menu.add_command(label="Paste", command=lambda: self._edit_action("paste"))
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Select All", command=lambda: self._edit_action("select_all"))

        # Global edit shortcuts for focused Entry/Text widgets, independent from keyboard layout.
        self.root.bind_all("<Control-KeyPress>", self._on_ctrl_keypress, add="+")
        self.root.bind_all("<Shift-Insert>", lambda e: self._edit_action("paste", event=e), add="+")

    def _on_ctrl_keypress(self, event: tk.Event) -> str | None:
        keycode_map = {
            67: "copy",       # C
            88: "cut",        # X
            86: "paste",      # V
            65: "select_all", # A
        }
        keysym_map = {
            "c": "copy", "с": "copy",
            "x": "cut", "ч": "cut",
            "v": "paste", "м": "paste",
            "a": "select_all", "ф": "select_all",
        }
        action = keycode_map.get(getattr(event, "keycode", -1))
        if action is None:
            action = keysym_map.get(str(getattr(event, "keysym", "")).lower())
        if action is None:
            return None
        return self._edit_action(action, event=event)

    def _setup_autosave(self) -> None:
        for var in self.env_vars.values():
            var.trace_add("write", lambda *_: self._schedule_autosave_env())

        cfg_vars: list[tk.Variable] = [
            self.cfg_execution_mode,
            self.cfg_start_paused,
            self.cfg_bybit_host,
            self.cfg_ws_host,
            self.cfg_market_category,
            self.cfg_runtime_strategy,
            self.cfg_symbols,
            self.cfg_target_profit,
            self.cfg_safety_buffer,
            self.cfg_stop_loss,
            self.cfg_take_profit,
            self.cfg_hold_timeout,
            self.cfg_min_active_usdt,
            self.cfg_maker_only,
            self.enable_spot_spread_var,
            self.enable_spot_spike_var,
            self.enable_futures_spike_var,
            self.config_var,
        ]
        for var in cfg_vars:
            var.trace_add("write", lambda *_: self._schedule_autosave_cfg())
        self.python_var.trace_add("write", lambda *_: self._refresh_runtime_labels())
        self.config_var.trace_add("write", lambda *_: self._refresh_runtime_labels())

    def _refresh_runtime_labels(self) -> None:
        py_name = Path(self.python_var.get()).name or "python"
        cfg_name = Path(self.config_var.get()).name or "config.yaml"
        self.runtime_python_name_var.set(py_name)
        self.runtime_config_name_var.set(cfg_name)

    def _schedule_autosave_env(self) -> None:
        if self._suspend_autosave:
            return
        if self._autosave_env_after_id is not None:
            self.root.after_cancel(self._autosave_env_after_id)
        self._autosave_env_after_id = self.root.after(500, self._autosave_env)

    def _schedule_autosave_cfg(self) -> None:
        if self._suspend_autosave:
            return
        if self._autosave_cfg_after_id is not None:
            self.root.after_cancel(self._autosave_cfg_after_id)
        self._autosave_cfg_after_id = self.root.after(700, self._autosave_cfg)

    def _autosave_env(self) -> None:
        self._autosave_env_after_id = None
        self.save_env(show_popup=False)

    def _autosave_cfg(self) -> None:
        self._autosave_cfg_after_id = None
        self.save_config(show_popup=False)

    def _flush_autosave(self) -> None:
        if self._autosave_env_after_id is not None:
            self.root.after_cancel(self._autosave_env_after_id)
            self._autosave_env_after_id = None
            self.save_env(show_popup=False)
        if self._autosave_cfg_after_id is not None:
            self.root.after_cancel(self._autosave_cfg_after_id)
            self._autosave_cfg_after_id = None
            self.save_config(show_popup=False)

    def _setup_style(self) -> None:
        self._ui_colors = apply_dark_theme(self.root)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, style="Root.TFrame", padding=12)
        root_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = ttk.Label(
            root_frame,
            text=f"Botik Control Console {self.app_version}",
            style="Title.TLabel",
        )
        self.title_label.pack(anchor=tk.W)
        ttk.Label(
            root_frame,
            text="Desktop mode for local monitoring and settings. Server mode stays CLI/systemd.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        notebook = ttk.Notebook(root_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook = notebook

        self.control_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.logs_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.settings_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.statistics_tab = ttk.Frame(notebook, style="Root.TFrame")
        notebook.add(self.control_tab, text="Главная")
        notebook.add(self.logs_tab, text="Логи")
        notebook.add(self.settings_tab, text="Настройки")
        notebook.add(self.statistics_tab, text="Статистика")

        settings_shell = ttk.Frame(self.settings_tab, style="Root.TFrame")
        settings_shell.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.settings_notebook = ttk.Notebook(settings_shell)
        self.settings_notebook.pack(fill=tk.BOTH, expand=True)
        self.settings_main_tab = ttk.Frame(self.settings_notebook, style="Root.TFrame")
        self.spike_tab = ttk.Frame(self.settings_notebook, style="Root.TFrame")
        self.settings_notebook.add(self.settings_main_tab, text="Параметры")
        self.settings_notebook.add(self.spike_tab, text="Стратегии")

        statistics_shell = ttk.Frame(self.statistics_tab, style="Root.TFrame")
        statistics_shell.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.statistics_notebook = ttk.Notebook(statistics_shell)
        self.statistics_notebook.pack(fill=tk.BOTH, expand=True)
        self.stats_tab = ttk.Frame(self.statistics_notebook, style="Root.TFrame")
        self.models_tab = ttk.Frame(self.statistics_notebook, style="Root.TFrame")
        self.statistics_notebook.add(self.stats_tab, text="Сделки")
        self.statistics_notebook.add(self.models_tab, text="Модели")

        self._build_control_tab()
        self._build_logs_tab()
        self._build_settings_tab()
        self._build_spike_tab()
        self._build_stats_tab()
        self._build_models_tab()
        self._attach_context_menu_to_entries(self.root)

    def _is_edit_widget(self, widget: tk.Widget | None) -> bool:
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text))

    def _attach_context_menu_to_entries(self, parent: tk.Widget) -> None:
        for child in parent.winfo_children():
            if isinstance(child, (tk.Entry, ttk.Entry, tk.Text)):
                child.bind("<Button-3>", self._show_edit_menu)
                child.bind("<Button-2>", self._show_edit_menu)
                child.bind("<Shift-F10>", self._show_edit_menu)
                child.bind("<Menu>", self._show_edit_menu)
            self._attach_context_menu_to_entries(child)

    def _show_edit_menu(self, event: tk.Event) -> None:
        self._edit_menu_target = event.widget
        x_root = getattr(event, "x_root", 0) or self.root.winfo_pointerx()
        y_root = getattr(event, "y_root", 0) or self.root.winfo_pointery()
        try:
            self.edit_menu.tk_popup(x_root, y_root)
        finally:
            self.edit_menu.grab_release()

    def _edit_action(self, action: str, event: tk.Event | None = None) -> str | None:
        widget = event.widget if event is not None else self._edit_menu_target
        if widget is None or not self._is_edit_widget(widget):
            widget = self.root.focus_get()
            if widget is None or not self._is_edit_widget(widget):
                return None

        if action == "copy":
            widget.event_generate("<<Copy>>")
        elif action == "cut":
            widget.event_generate("<<Cut>>")
        elif action == "paste":
            widget.event_generate("<<Paste>>")
        elif action == "select_all":
            widget.event_generate("<<SelectAll>>")
        return "break" if event is not None else None

    def _build_control_tab(self) -> None:
        split = ttk.Panedwindow(self.control_tab, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        left = ttk.Frame(split, style="Root.TFrame")
        right = ttk.Frame(split, style="Root.TFrame")
        split.add(left, weight=4)
        split.add(right, weight=2)

        path_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        path_card.pack(fill=tk.X)
        ttk.Label(path_card, text="Runtime", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W, columnspan=4)
        ttk.Label(path_card, text="Python", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Label(path_card, textvariable=self.runtime_python_name_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=6)
        ttk.Label(path_card, text="Config", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, pady=6, padx=(18, 0))
        ttk.Label(path_card, textvariable=self.runtime_config_name_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=6)

        action_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        action_card.pack(fill=tk.X, pady=8)
        ttk.Label(action_card, text="Actions", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)

        ttk.Button(action_card, text="Старт торгов", command=self.start_trading, style="Start.TButton").grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Остановить торги", command=self.stop_trading, style="Stop.TButton").grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Pause Training", command=self.pause_training).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=3
        )

        ttk.Button(action_card, text="Run Preflight", command=self.run_preflight, style="Accent.TButton").grid(
            row=2, column=0, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Clear Log", command=self.clear_log).grid(row=2, column=1, sticky=tk.EW, padx=4, pady=3)
        ttk.Button(action_card, text="Copy Chart", command=self.copy_ml_chart).grid(row=2, column=2, sticky=tk.EW, padx=4, pady=3)
        ttk.Button(action_card, text="Copy Selected", command=self.copy_selected_log).grid(row=3, column=0, sticky=tk.EW, padx=4, pady=3)
        ttk.Button(action_card, text="Copy All", command=self.copy_all_log).grid(row=3, column=1, sticky=tk.EW, padx=4, pady=3)
        ttk.Button(action_card, text="Help", command=self.show_help).grid(row=3, column=2, sticky=tk.EW, padx=4, pady=3)
        ttk.Label(action_card, text="Tip: right click in log for copy menu", style="Body.TLabel").grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=4, pady=(4, 2)
        )

        for i in range(3):
            action_card.columnconfigure(i, weight=1)

        strategy_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        strategy_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(strategy_card, text="Стратегии (мульти-выбор)", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Checkbutton(strategy_card, text="Spot Spread (Maker)", variable=self.enable_spot_spread_var).grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(strategy_card, text="Spot Spike Burst", variable=self.enable_spot_spike_var).grid(
            row=1, column=1, sticky=tk.W, pady=4, padx=(12, 0)
        )
        ttk.Checkbutton(
            strategy_card,
            text="Futures Spike Reversal",
            variable=self.enable_futures_spike_var,
        ).grid(row=1, column=2, sticky=tk.W, pady=4, padx=(12, 0))
        ttk.Label(
            strategy_card,
            text="Start (Trade+ML) запускает все отмеченные стратегии одновременно.",
            style="Body.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(2, 0))
        strategy_card.columnconfigure(3, weight=1)

        account_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        account_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(account_card, text="Счет и ордера", style="Section.TLabel").grid(
            row=0, column=0, columnspan=6, sticky=tk.W
        )
        ttk.Label(account_card, text="Баланс USDT", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Label(account_card, textvariable=self.balance_total_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Доступно", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.balance_available_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Кошелек", style="Body.TLabel").grid(row=1, column=4, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.balance_wallet_var, style="Body.TLabel").grid(row=1, column=5, sticky=tk.W, pady=4)

        ttk.Label(account_card, text="Открытые ордера", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Label(account_card, textvariable=self.open_orders_var, style="Body.TLabel").grid(row=2, column=1, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="API", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.api_status_var, style="Body.TLabel").grid(row=2, column=3, columnspan=2, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Обновлено", style="Body.TLabel").grid(row=2, column=5, sticky=tk.E, pady=4)
        ttk.Label(account_card, textvariable=self.snapshot_time_var, style="Body.TLabel").grid(row=2, column=6, sticky=tk.W, pady=4, padx=(6, 0))
        ttk.Button(account_card, text="Обновить данные", command=self.refresh_runtime_snapshot).grid(
            row=1, column=6, rowspan=1, sticky=tk.E, padx=(14, 0), pady=2
        )
        ttk.Button(account_card, text="Закрыть выбранную позицию", command=self.manual_close_selected_position).grid(
            row=2, column=6, sticky=tk.E, padx=(14, 0), pady=2
        )
        account_card.columnconfigure(6, weight=1)
        account_card.rowconfigure(3, weight=1)

        orders_grid = ttk.Frame(account_card, style="Card.TFrame")
        orders_grid.grid(row=3, column=0, columnspan=7, sticky=tk.NSEW, pady=(8, 0))
        orders_grid.columnconfigure(0, weight=1, uniform="orders")
        orders_grid.columnconfigure(1, weight=1, uniform="orders")
        orders_grid.rowconfigure(0, weight=1)

        open_card = ttk.Frame(orders_grid, style="Card.TFrame")
        open_card.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))
        ttk.Label(open_card, text="Открытые ордера / HOLD позиции", style="Body.TLabel").pack(anchor=tk.W)
        open_table_wrap = ttk.Frame(open_card, style="Card.TFrame")
        open_table_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        open_table_wrap.columnconfigure(0, weight=1)
        open_table_wrap.rowconfigure(0, weight=1)
        self.open_orders_tree = ttk.Treeview(
            open_table_wrap,
            columns=(
                "n",
                "symbol",
                "market",
                "strategy",
                "side",
                "price",
                "now",
                "qty",
                "usd",
                "entry",
                "target",
                "pnl",
                "pnl_usdt",
                "heat",
                "status",
            ),
            show="headings",
            height=11,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 96),
            ("market", "Mkt", 54),
            ("strategy", "Strategy", 98),
            ("side", "Side", 58),
            ("price", "Order", 90),
            ("now", "Now", 90),
            ("qty", "Qty", 80),
            ("usd", "USD", 80),
            ("entry", "Entry", 90),
            ("target", "Target", 90),
            ("pnl", "PnL%", 70),
            ("pnl_usdt", "PnL USDT", 88),
            ("heat", "Exit", 78),
            ("status", "Status", 150),
        ]:
            self.open_orders_tree.heading(col, text=title)
            self.open_orders_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.open_orders_tree.column("status", stretch=True)
        self.open_orders_tree.tag_configure("pnl_pos", foreground="#5FE08C")
        self.open_orders_tree.tag_configure("pnl_neg", foreground="#FF7F7F")
        self.open_orders_tree.tag_configure("pnl_neutral", foreground="#A0B6D8")
        self.open_orders_tree.tag_configure("exit_ready", foreground="#5FE08C")
        self.open_orders_tree.tag_configure("exit_wait", foreground="#FFD166")
        self.open_orders_tree.tag_configure("exit_risk", foreground="#FF7F7F")
        open_scroll_y = ttk.Scrollbar(open_table_wrap, orient=tk.VERTICAL, command=self.open_orders_tree.yview)
        open_scroll_x = ttk.Scrollbar(open_table_wrap, orient=tk.HORIZONTAL, command=self.open_orders_tree.xview)
        self.open_orders_tree.configure(yscrollcommand=open_scroll_y.set, xscrollcommand=open_scroll_x.set)
        self.open_orders_tree.grid(row=0, column=0, sticky=tk.NSEW)
        open_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        open_scroll_x.grid(row=1, column=0, sticky=tk.EW)

        history_card = ttk.Frame(orders_grid, style="Card.TFrame")
        history_card.grid(row=0, column=1, sticky=tk.NSEW, padx=(6, 0))
        ttk.Label(history_card, text="История ордеров (локальная БД)", style="Body.TLabel").pack(anchor=tk.W)
        history_table_wrap = ttk.Frame(history_card, style="Card.TFrame")
        history_table_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        history_table_wrap.columnconfigure(0, weight=1)
        history_table_wrap.rowconfigure(0, weight=1)
        self.order_history_tree = ttk.Treeview(
            history_table_wrap,
            columns=("n", "date", "time", "symbol", "side", "status", "price", "qty", "entry", "exit"),
            show="headings",
            height=11,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("date", "Дата", 95),
            ("time", "Время", 95),
            ("symbol", "Symbol", 90),
            ("side", "Side", 60),
            ("status", "Status", 90),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
            ("entry", "Entry", 90),
            ("exit", "Exit", 90),
        ]:
            self.order_history_tree.heading(col, text=title)
            self.order_history_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.order_history_tree.column("status", stretch=True)
        history_scroll_y = ttk.Scrollbar(history_table_wrap, orient=tk.VERTICAL, command=self.order_history_tree.yview)
        history_scroll_x = ttk.Scrollbar(history_table_wrap, orient=tk.HORIZONTAL, command=self.order_history_tree.xview)
        self.order_history_tree.configure(yscrollcommand=history_scroll_y.set, xscrollcommand=history_scroll_x.set)
        self.order_history_tree.grid(row=0, column=0, sticky=tk.NSEW)
        history_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        history_scroll_x.grid(row=1, column=0, sticky=tk.EW)

        status_card = ttk.Frame(right, style="Card.TFrame", padding=10)
        status_card.pack(fill=tk.X)
        ttk.Label(status_card, text="Status", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.mode_label = ttk.Label(status_card, text="execution.mode: unknown", style="Body.TLabel")
        self.mode_label.pack(anchor=tk.W, pady=3)
        self.version_label = ttk.Label(status_card, text=f"app.version: {self.app_version}", style="Body.TLabel")
        self.version_label.pack(anchor=tk.W, pady=3)
        self.trading_row = ttk.Frame(status_card, style="Card.TFrame")
        self.trading_row.pack(fill=tk.X, pady=3)
        self.trading_led = tk.Canvas(
            self.trading_row,
            width=14,
            height=14,
            highlightthickness=0,
            bg=self._ui_colors.get("card", "#16263F"),
        )
        self.trading_led.pack(side=tk.LEFT, padx=(0, 6))
        self.trading_label = ttk.Label(self.trading_row, text="trading: stopped", style="Body.TLabel")
        self.trading_label.pack(side=tk.LEFT)
        self.ml_row = ttk.Frame(status_card, style="Card.TFrame")
        self.ml_row.pack(fill=tk.X, pady=3)
        self.ml_led = tk.Canvas(
            self.ml_row,
            width=14,
            height=14,
            highlightthickness=0,
            bg=self._ui_colors.get("card", "#16263F"),
        )
        self.ml_led.pack(side=tk.LEFT, padx=(0, 6))
        self.ml_label = ttk.Label(self.ml_row, text="ml: stopped", style="Body.TLabel")
        self.ml_label.pack(side=tk.LEFT)
        ttk.Separator(status_card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(6, 6))
        ttk.Label(status_card, textvariable=self.runtime_capabilities_var, style="Body.TLabel", justify=tk.LEFT).pack(
            anchor=tk.W, pady=2
        )
        ttk.Label(status_card, textvariable=self.reconciliation_status_var, style="Body.TLabel", justify=tk.LEFT).pack(
            anchor=tk.W, pady=2
        )
        ttk.Label(status_card, textvariable=self.panel_freshness_var, style="Body.TLabel", justify=tk.LEFT).pack(
            anchor=tk.W, pady=2
        )
        ttk.Label(
            status_card,
            textvariable=self.futures_protection_status_var,
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=2)

        ml_card = ttk.Frame(right, style="Card.TFrame", padding=10)
        ml_card.pack(fill=tk.X, pady=8)
        ttk.Label(ml_card, text="ML Panel", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Button(ml_card, text="Copy Chart", command=self.copy_ml_chart).grid(row=0, column=3, sticky=tk.E)

        ttk.Label(ml_card, text="Model", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Label(ml_card, textvariable=self.ml_model_id_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(ml_card, text="State", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, pady=3, padx=(12, 0))
        ttk.Label(ml_card, textvariable=self.ml_training_state_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=3)

        ttk.Label(ml_card, text="Progress", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.ml_progress = ttk.Progressbar(ml_card, mode="indeterminate", maximum=100)
        self.ml_progress.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=3, padx=(0, 8))
        self.ml_progress_label = ttk.Label(
            ml_card,
            textvariable=self.ml_progress_text_var,
            style="Body.TLabel",
            justify=tk.LEFT,
        )
        self.ml_progress_label.grid(row=2, column=3, sticky=tk.W, pady=3)
        self.ml_progress_label.configure(wraplength=210)

        ttk.Label(ml_card, text="Metrics", style="Body.TLabel").grid(row=3, column=0, sticky=tk.NW, pady=(2, 0))
        ml_metrics_label = ttk.Label(
            ml_card,
            textvariable=self.ml_metrics_compact_var,
            style="Body.TLabel",
            justify=tk.LEFT,
        )
        ml_metrics_label.grid(row=3, column=1, columnspan=3, sticky=tk.EW, pady=(2, 0))
        ml_metrics_label.configure(wraplength=300)

        self.ml_chart_canvas = tk.Canvas(
            ml_card,
            height=48,
            bg=self._ui_colors.get("bg_soft", "#111D33"),
            highlightthickness=1,
            highlightbackground=self._ui_colors.get("line", "#2A4063"),
        )
        self.ml_chart_canvas.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(6, 0))
        for i in range(4):
            ml_card.columnconfigure(i, weight=1)

        hint = ttk.Frame(right, style="Card.TFrame", padding=10)
        hint.pack(fill=tk.X, pady=8)
        ttk.Label(hint, text="Hint", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hint,
            text="Use Start (Trade+ML) for unified runtime.\nPause Training keeps trading active and pauses ML updates.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=6)

        log_card = ttk.Frame(right, style="Card.TFrame", padding=10)
        log_card.pack(fill=tk.X, pady=(0, 4))
        log_head = ttk.Frame(log_card, style="Card.TFrame")
        log_head.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(log_head, text="Live Log (compact)", style="Section.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        self.log_jump_main = ttk.Button(log_head, text="⬇", width=3, command=lambda: self._jump_log_to_end("main"))
        self.log_jump_main.pack(side=tk.RIGHT)
        self.log_jump_main.pack_forget()

        log_body = ttk.Frame(log_card, style="Card.TFrame")
        log_body.pack(fill=tk.X, expand=False)
        self.log_text = tk.Text(
            log_body,
            wrap=tk.WORD,
            height=8,
            bg=self._ui_colors.get("log_bg", "#0F1A2B"),
            fg=self._ui_colors.get("log_fg", "#D8E8FF"),
            insertbackground=self._ui_colors.get("log_fg", "#D8E8FF"),
            relief=tk.FLAT,
            font=("Consolas", 10),
        )
        log_scroll = ttk.Scrollbar(log_body, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_scroll_main = log_scroll
        self.log_text.configure(yscrollcommand=lambda a, b: self._on_log_yview("main", a, b))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.bind("<Control-c>", self._on_ctrl_c)
        self.log_text.bind("<Button-3>", self._show_log_context_menu)
        self.log_text.bind("<Button-4>", lambda _e: self._update_log_jump_buttons())
        self.log_text.bind("<Button-5>", lambda _e: self._update_log_jump_buttons())
        self.log_text.bind("<MouseWheel>", lambda _e: self._update_log_jump_buttons())
        self.log_text.bind("<KeyRelease>", lambda _e: self._update_log_jump_buttons())
        self.log_menu = tk.Menu(self.root, tearoff=0)
        self.log_menu.add_command(label="Copy Selected", command=self.copy_selected_log)
        self.log_menu.add_command(label="Copy All", command=self.copy_all_log)

    def _build_logs_tab(self) -> None:
        logs_root = ttk.Frame(self.logs_tab, style="Root.TFrame")
        logs_root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        logs_card = card(logs_root, padding=10)
        logs_card.pack(fill=tk.BOTH, expand=True)
        head = ttk.Frame(logs_card, style="Card.TFrame")
        head.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(head, text="Торговые логи", style="Section.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        self.log_jump_full = ttk.Button(head, text="⬇", width=3, command=lambda: self._jump_log_to_end("full"))
        self.log_jump_full.pack(side=tk.RIGHT)
        self.log_jump_full.pack_forget()

        filters = ttk.Frame(logs_card, style="Card.TFrame")
        filters.pack(fill=tk.X, pady=(0, 8))
        self.log_pair_filter_combo = labeled_combobox(
            filters,
            label="Фильтр пары",
            variable=self.log_filter_pair_var,
            values=["ALL"],
            width=16,
        )
        self.log_level_filter_combo = labeled_combobox(
            filters,
            label="Уровень лога",
            variable=self.log_filter_level_var,
            values=["ALL", "INFO", "WARNING", "ERROR", "DEBUG"],
            width=14,
        )
        labeled_entry(
            filters,
            label="Поиск",
            variable=self.log_filter_query_var,
            width=32,
        )
        ttk.Button(filters, text="Сброс", command=self._clear_log_filters).pack(side=tk.LEFT, pady=(18, 0))

        if self.log_pair_filter_combo is not None:
            self.log_pair_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        if self.log_level_filter_combo is not None:
            self.log_level_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        self.log_filter_level_var.trace_add("write", lambda *_: self._on_log_filter_changed())
        self.log_filter_pair_var.trace_add("write", lambda *_: self._on_log_filter_changed())
        self.log_filter_query_var.trace_add("write", lambda *_: self._on_log_filter_changed())

        body = ttk.Frame(logs_card, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        self.log_text_full = tk.Text(
            body,
            wrap=tk.WORD,
            height=28,
            bg=self._ui_colors.get("log_bg", "#0F1A2B"),
            fg=self._ui_colors.get("log_fg", "#D8E8FF"),
            insertbackground=self._ui_colors.get("log_fg", "#D8E8FF"),
            relief=tk.FLAT,
            font=("Consolas", 10),
        )
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.log_text_full.yview)
        self.log_scroll_full = scroll
        self.log_text_full.configure(yscrollcommand=lambda a, b: self._on_log_yview("full", a, b))
        self.log_text_full.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text_full.bind("<Control-c>", self._on_ctrl_c)
        self.log_text_full.bind("<Button-3>", self._show_log_context_menu)
        self.log_text_full.bind("<Button-4>", lambda _e: self._update_log_jump_buttons())
        self.log_text_full.bind("<Button-5>", lambda _e: self._update_log_jump_buttons())
        self.log_text_full.bind("<MouseWheel>", lambda _e: self._update_log_jump_buttons())
        self.log_text_full.bind("<KeyRelease>", lambda _e: self._update_log_jump_buttons())
        self._refresh_full_log_filtered_view()

    def _build_stats_tab(self) -> None:
        stats_root = ttk.Frame(self.stats_tab, style="Root.TFrame")
        stats_root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        summary_card = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        summary_card.pack(fill=tk.X)
        ttk.Label(summary_card, text="Статистика закрытий", style="Section.TLabel").grid(
            row=0, column=0, columnspan=8, sticky=tk.W
        )
        ttk.Button(summary_card, text="Обновить статистику", command=self.refresh_runtime_snapshot).grid(
            row=0, column=7, sticky=tk.E
        )
        ttk.Label(summary_card, text="Ордера в истории", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Label(summary_card, textvariable=self.stats_orders_total_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Закрытые outcomes", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_outcomes_total_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Плюс", style="Body.TLabel").grid(row=1, column=4, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_positive_var, style="Body.TLabel").grid(row=1, column=5, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Минус", style="Body.TLabel").grid(row=1, column=6, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_negative_var, style="Body.TLabel").grid(row=1, column=7, sticky=tk.W, pady=4)

        ttk.Label(summary_card, text="Ноль", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Label(summary_card, textvariable=self.stats_neutral_var, style="Body.TLabel").grid(row=2, column=1, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Сумма net_pnl_quote", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_net_pnl_var, style="Body.TLabel").grid(row=2, column=3, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Средний net_pnl_quote", style="Body.TLabel").grid(row=2, column=4, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_avg_pnl_var, style="Body.TLabel").grid(row=2, column=5, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Δquote events", style="Body.TLabel").grid(row=2, column=6, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(summary_card, textvariable=self.stats_balance_delta_var, style="Body.TLabel").grid(row=2, column=7, sticky=tk.W, pady=4)
        ttk.Label(summary_card, text="Событий баланса", style="Body.TLabel").grid(row=3, column=6, sticky=tk.W, padx=(16, 0), pady=2)
        ttk.Label(summary_card, textvariable=self.stats_balance_events_var, style="Body.TLabel").grid(row=3, column=7, sticky=tk.W, pady=2)
        ttk.Label(summary_card, text="Cumulative PnL (outcomes)", style="Body.TLabel").grid(
            row=4, column=0, columnspan=8, sticky=tk.W, pady=(8, 2)
        )
        self.stats_pnl_canvas = tk.Canvas(
            summary_card,
            height=78,
            bg=self._ui_colors.get("bg_soft", "#111D33"),
            highlightthickness=1,
            highlightbackground=self._ui_colors.get("line", "#2A4063"),
        )
        self.stats_pnl_canvas.grid(row=5, column=0, columnspan=8, sticky=tk.EW, pady=(2, 0))
        for i in range(8):
            summary_card.columnconfigure(i, weight=1)

        full_card = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        full_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(full_card, text="История ордеров (полная, локальная БД)", style="Section.TLabel").pack(anchor=tk.W)

        table_wrap = ttk.Frame(full_card, style="Card.TFrame")
        table_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.stats_history_tree = ttk.Treeview(
            table_wrap,
            columns=("n", "date", "time", "symbol", "side", "status", "price", "qty", "entry", "exit"),
            show="headings",
            height=28,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("date", "Дата", 95),
            ("time", "Время", 95),
            ("symbol", "Symbol", 90),
            ("side", "Side", 60),
            ("status", "Status", 90),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
            ("entry", "Entry", 90),
            ("exit", "Exit", 90),
        ]:
            self.stats_history_tree.heading(col, text=title)
            self.stats_history_tree.column(col, width=width, anchor=tk.W)
        stats_scroll = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.stats_history_tree.yview)
        self.stats_history_tree.configure(yscrollcommand=stats_scroll.set)
        self.stats_history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stats_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        balance_card = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        balance_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(balance_card, text="История изменения баланса (исполнения)", style="Section.TLabel").pack(anchor=tk.W)

        balance_wrap = ttk.Frame(balance_card, style="Card.TFrame")
        balance_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.stats_balance_tree = ttk.Treeview(
            balance_wrap,
            columns=("n", "date", "time", "symbol", "side", "qty", "price", "fee_q", "delta_q", "cum_q"),
            show="headings",
            height=10,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("date", "Дата", 95),
            ("time", "Время", 95),
            ("symbol", "Symbol", 92),
            ("side", "Side", 60),
            ("qty", "Qty", 92),
            ("price", "Price", 92),
            ("fee_q", "FeeQ", 82),
            ("delta_q", "DeltaQ", 96),
            ("cum_q", "CumQ", 96),
        ]:
            self.stats_balance_tree.heading(col, text=title)
            self.stats_balance_tree.column(col, width=width, anchor=tk.W)
        bal_scroll = ttk.Scrollbar(balance_wrap, orient=tk.VERTICAL, command=self.stats_balance_tree.yview)
        self.stats_balance_tree.configure(yscrollcommand=bal_scroll.set)
        self.stats_balance_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bal_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        domain_card = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        domain_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(domain_card, text="Spot/Futures/Reconciliation", style="Section.TLabel").pack(anchor=tk.W)

        domain_notebook = ttk.Notebook(domain_card)
        domain_notebook.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        spot_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        futures_pos_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        futures_ord_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        issues_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        domain_notebook.add(spot_frame, text="Spot Holdings")
        domain_notebook.add(futures_pos_frame, text="Futures Positions")
        domain_notebook.add(futures_ord_frame, text="Futures Orders")
        domain_notebook.add(issues_frame, text="Reconciliation Issues")

        spot_wrap = ttk.Frame(spot_frame, style="Card.TFrame")
        spot_wrap.pack(fill=tk.BOTH, expand=True)
        self.stats_spot_holdings_tree = ttk.Treeview(
            spot_wrap,
            columns=("n", "symbol", "base", "free", "locked", "entry", "reason", "source", "recovered", "auto_sell"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 96),
            ("base", "Base", 64),
            ("free", "Free", 90),
            ("locked", "Locked", 90),
            ("entry", "AvgEntry", 90),
            ("reason", "HoldReason", 150),
            ("source", "Source", 150),
            ("recovered", "Recovered", 86),
            ("auto_sell", "AutoSell", 82),
        ]:
            self.stats_spot_holdings_tree.heading(col, text=title)
            self.stats_spot_holdings_tree.column(col, width=width, anchor=tk.W)
        spot_scroll = ttk.Scrollbar(spot_wrap, orient=tk.VERTICAL, command=self.stats_spot_holdings_tree.yview)
        self.stats_spot_holdings_tree.configure(yscrollcommand=spot_scroll.set)
        self.stats_spot_holdings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        spot_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        fut_pos_wrap = ttk.Frame(futures_pos_frame, style="Card.TFrame")
        fut_pos_wrap.pack(fill=tk.BOTH, expand=True)
        self.stats_futures_positions_tree = ttk.Treeview(
            fut_pos_wrap,
            columns=("n", "symbol", "side", "qty", "entry", "mark", "liq", "upnl", "tp", "sl", "protection"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 96),
            ("side", "Side", 62),
            ("qty", "Qty", 90),
            ("entry", "Entry", 90),
            ("mark", "Mark", 90),
            ("liq", "Liq", 90),
            ("upnl", "UPnL", 90),
            ("tp", "TakeProfit", 92),
            ("sl", "StopLoss", 92),
            ("protection", "Protection", 110),
        ]:
            self.stats_futures_positions_tree.heading(col, text=title)
            self.stats_futures_positions_tree.column(col, width=width, anchor=tk.W)
        fut_pos_scroll = ttk.Scrollbar(fut_pos_wrap, orient=tk.VERTICAL, command=self.stats_futures_positions_tree.yview)
        self.stats_futures_positions_tree.configure(yscrollcommand=fut_pos_scroll.set)
        self.stats_futures_positions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fut_pos_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        fut_ord_wrap = ttk.Frame(futures_ord_frame, style="Card.TFrame")
        fut_ord_wrap.pack(fill=tk.BOTH, expand=True)
        self.stats_futures_orders_tree = ttk.Treeview(
            fut_ord_wrap,
            columns=("n", "symbol", "side", "order_id", "link_id", "type", "price", "qty", "status"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 96),
            ("side", "Side", 62),
            ("order_id", "OrderID", 130),
            ("link_id", "LinkID", 130),
            ("type", "Type", 70),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
            ("status", "Status", 120),
        ]:
            self.stats_futures_orders_tree.heading(col, text=title)
            self.stats_futures_orders_tree.column(col, width=width, anchor=tk.W)
        fut_ord_scroll = ttk.Scrollbar(fut_ord_wrap, orient=tk.VERTICAL, command=self.stats_futures_orders_tree.yview)
        self.stats_futures_orders_tree.configure(yscrollcommand=fut_ord_scroll.set)
        self.stats_futures_orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fut_ord_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        issues_wrap = ttk.Frame(issues_frame, style="Card.TFrame")
        issues_wrap.pack(fill=tk.BOTH, expand=True)
        self.stats_reconciliation_issues_tree = ttk.Treeview(
            issues_wrap,
            columns=("n", "ts", "domain", "type", "symbol", "severity", "status"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("ts", "Created", 150),
            ("domain", "Domain", 90),
            ("type", "IssueType", 210),
            ("symbol", "Symbol", 96),
            ("severity", "Severity", 80),
            ("status", "Status", 80),
        ]:
            self.stats_reconciliation_issues_tree.heading(col, text=title)
            self.stats_reconciliation_issues_tree.column(col, width=width, anchor=tk.W)
        issues_scroll = ttk.Scrollbar(issues_wrap, orient=tk.VERTICAL, command=self.stats_reconciliation_issues_tree.yview)
        self.stats_reconciliation_issues_tree.configure(yscrollcommand=issues_scroll.set)
        self.stats_reconciliation_issues_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        issues_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_models_tab(self) -> None:
        models_root = ttk.Frame(self.models_tab, style="Root.TFrame")
        models_root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        top_card = ttk.Frame(models_root, style="Card.TFrame", padding=10)
        top_card.pack(fill=tk.X)
        ttk.Label(top_card, text="Реестр моделей и качество", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(top_card, textvariable=self.models_summary_var, style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Button(top_card, text="Обновить", command=self.refresh_runtime_snapshot).grid(row=0, column=1, sticky=tk.E)
        ttk.Button(top_card, text="Активировать выбранную модель", command=self.activate_selected_model).grid(
            row=1, column=1, sticky=tk.E, pady=(6, 0)
        )
        top_card.columnconfigure(0, weight=1)

        table_card = ttk.Frame(models_root, style="Card.TFrame", padding=10)
        table_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.models_tree = ttk.Treeview(
            table_card,
            columns=(
                "model_id",
                "created",
                "active",
                "outcomes",
                "plus",
                "minus",
                "winrate",
                "net_pnl",
                "edge",
                "fill",
            ),
            show="headings",
            height=24,
        )
        for col, title, width in [
            ("model_id", "Model", 180),
            ("created", "Created", 150),
            ("active", "Active", 64),
            ("outcomes", "Outcomes", 86),
            ("plus", "Plus", 64),
            ("minus", "Minus", 64),
            ("winrate", "WinRate", 86),
            ("net_pnl", "NetPnL", 92),
            ("edge", "Edge bps", 86),
            ("fill", "FillRate", 86),
        ]:
            self.models_tree.heading(col, text=title)
            self.models_tree.column(col, width=width, anchor=tk.W)
        self.models_tree.tag_configure("model_active", foreground="#5FE08C")
        model_scroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.models_tree.yview)
        self.models_tree.configure(yscrollcommand=model_scroll.set)
        self.models_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        model_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_spike_tab(self) -> None:
        spike_root = ttk.Frame(self.spike_tab, style="Root.TFrame")
        spike_root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        info_card = ttk.Frame(spike_root, style="Card.TFrame", padding=10)
        info_card.pack(fill=tk.X)
        ttk.Label(info_card, text="Strategy Launcher", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            info_card,
            text=(
                "Выберите режим торговли и запускайте его прямо из GUI.\n"
                "Для каждого пресета автоматически обновляются config-поля рынка и стратегии."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(6, 0))

        mode_card = ttk.Frame(spike_root, style="Card.TFrame", padding=10)
        mode_card.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(mode_card, text="Preset", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(mode_card, text="Trading mode", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            mode_card,
            textvariable=self.strategy_mode_var,
            values=list(STRATEGY_PRESET_LABELS.keys()),
            state="readonly",
            width=30,
        ).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(
            mode_card,
            text="Spot Spread = классический maker.\nSpot Spike = burst на спайках.\nFutures Spike Reversal = linear + reverse + taker.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=2, sticky=tk.W, padx=(16, 0))
        mode_card.columnconfigure(2, weight=1)

        params_card = ttk.Frame(spike_root, style="Card.TFrame", padding=10)
        params_card.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(params_card, text="Spike Preset Params", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Label(params_card, text="spike_threshold_bps", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(params_card, textvariable=self.spike_threshold_bps_var, width=14).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(params_card, text="spike_min_trades_per_min", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(params_card, textvariable=self.spike_min_trades_var, width=14).grid(row=1, column=3, sticky=tk.W)

        ttk.Label(params_card, text="spike_burst_slices", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(params_card, textvariable=self.spike_slices_var, width=14).grid(row=2, column=1, sticky=tk.W)
        ttk.Label(params_card, text="spike_burst_qty_scale", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(params_card, textvariable=self.spike_qty_scale_var, width=14).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(params_card, text="scanner_top_k", style="Body.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Entry(params_card, textvariable=self.spike_scanner_top_k_var, width=14).grid(row=3, column=1, sticky=tk.W)
        ttk.Label(params_card, text="auto_universe_size", style="Body.TLabel").grid(row=3, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(params_card, textvariable=self.spike_universe_size_var, width=14).grid(row=3, column=3, sticky=tk.W)

        ttk.Label(params_card, text="ml.run_interval_sec", style="Body.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Entry(params_card, textvariable=self.spike_ml_interval_var, width=14).grid(row=4, column=1, sticky=tk.W)
        for i in range(4):
            params_card.columnconfigure(i, weight=1)

        actions_card = ttk.Frame(spike_root, style="Card.TFrame", padding=10)
        actions_card.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions_card, text="Apply Selected Preset", command=self.apply_selected_strategy).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions_card, text="Apply Spike Params Only", command=self.apply_spike_preset).pack(side=tk.LEFT, padx=6)
        ttk.Label(
            actions_card,
            text="Запуск/остановка торговли выполняются только с вкладки Control.",
            style="Body.TLabel",
        ).pack(side=tk.LEFT, padx=10)

    def _build_settings_tab(self) -> None:
        settings_parent = self.settings_main_tab if self.settings_main_tab is not None else self.settings_tab
        settings_root = ttk.Frame(settings_parent, style="Root.TFrame")
        settings_root.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

        env_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        env_card.pack(fill=tk.X)
        ttk.Label(env_card, text=".env Secrets", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W)

        secret_fields = {"TELEGRAM_BOT_TOKEN", "BYBIT_API_KEY", "BYBIT_API_SECRET_KEY"}
        row = 1
        for key, var in self.env_vars.items():
            ttk.Label(env_card, text=key, style="Body.TLabel").grid(row=row, column=0, sticky=tk.W, pady=4)
            show = "*" if key in secret_fields else ""
            ttk.Entry(env_card, textvariable=var, width=100, show=show).grid(row=row, column=1, sticky=tk.EW, padx=8)
            row += 1
        env_card.columnconfigure(1, weight=1)

        cfg_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        cfg_card.pack(fill=tk.X, pady=8)
        ttk.Label(cfg_card, text="config.yaml Quick Settings", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W)

        ttk.Label(cfg_card, text="execution.mode", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(cfg_card, textvariable=self.cfg_execution_mode, values=["paper", "live"], state="readonly", width=14).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(cfg_card, text="start_paused", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Checkbutton(cfg_card, variable=self.cfg_start_paused).grid(row=1, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="bybit.host", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_bybit_host, width=28).grid(row=2, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="ws_public_host", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_ws_host, width=28).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="bybit.market_category", style="Body.TLabel").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(
            cfg_card,
            textvariable=self.cfg_market_category,
            values=["spot", "linear"],
            state="readonly",
            width=14,
        ).grid(row=3, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="strategy.runtime_strategy", style="Body.TLabel").grid(row=3, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Combobox(
            cfg_card,
            textvariable=self.cfg_runtime_strategy,
            values=["spread_maker", "spike_reversal"],
            state="readonly",
            width=18,
        ).grid(row=3, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="symbols (comma)", style="Body.TLabel").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_symbols, width=28).grid(row=4, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="entry_mode", style="Body.TLabel").grid(row=4, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Label(cfg_card, text="auto by strategy", style="Body.TLabel").grid(row=4, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="target_profit", style="Body.TLabel").grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_target_profit, width=16).grid(row=5, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="safety_buffer", style="Body.TLabel").grid(row=5, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_safety_buffer, width=16).grid(row=5, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="stop_loss_pct", style="Body.TLabel").grid(row=6, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_stop_loss, width=16).grid(row=6, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="take_profit_pct", style="Body.TLabel").grid(row=6, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_take_profit, width=16).grid(row=6, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="hold_timeout_sec", style="Body.TLabel").grid(row=7, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_hold_timeout, width=16).grid(row=7, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="min_active_position_usdt", style="Body.TLabel").grid(row=7, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_min_active_usdt, width=16).grid(row=7, column=3, sticky=tk.W)

        btn_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        btn_card.pack(fill=tk.X)
        ttk.Button(btn_card, text="Reload From Files", command=self.load_settings).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            btn_card,
            text="Auto-save is ON: changes in fields are written to .env/config.yaml automatically.",
            style="Body.TLabel",
        ).pack(side=tk.LEFT, padx=12)

    @staticmethod
    def _is_noisy_runtime_log(text: str) -> tuple[bool, str]:
        if "PairFilter symbol=" in text:
            return True, "pairfilter"
        if "Policy=ML, sym=" in text:
            return True, "policy"
        return False, ""

    def _flush_suppressed_log_summary(self, force: bool = False) -> None:
        now_mono = time.monotonic()
        if not force and (now_mono - self._suppressed_logs_last_flush) < 2.0:
            return
        total = self._suppressed_pairfilter_logs + self._suppressed_policy_logs
        if total <= 0:
            self._suppressed_logs_last_flush = now_mono
            return
        summary = (
            f"[ui] noisy logs condensed: PairFilter={self._suppressed_pairfilter_logs} "
            f"PolicyML={self._suppressed_policy_logs}"
        )
        self._suppressed_pairfilter_logs = 0
        self._suppressed_policy_logs = 0
        self._suppressed_logs_last_flush = now_mono
        self.log_queue.put(summary)
        try:
            GUI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with GUI_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts} {summary}\n")
        except OSError:
            pass

    @staticmethod
    def _trim_text_widget(widget: tk.Text, max_lines: int) -> None:
        if max_lines <= 0:
            return
        try:
            line_count = int(float(widget.index("end-1c").split(".")[0]))
        except Exception:
            return
        overflow = line_count - max_lines
        if overflow > 0:
            widget.delete("1.0", f"{overflow + 1}.0")

    def _enqueue_log(self, text: str) -> None:
        noisy, noisy_kind = self._is_noisy_runtime_log(text)
        if noisy:
            if noisy_kind == "pairfilter":
                self._suppressed_pairfilter_logs += 1
            elif noisy_kind == "policy":
                self._suppressed_policy_logs += 1
            self._flush_suppressed_log_summary()
            return

        self._flush_suppressed_log_summary()
        self.log_queue.put(text)
        try:
            GUI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with GUI_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts} {text}\n")
        except OSError:
            pass

    def _invoke_on_ui_thread(self, fn: Callable[[], Any], timeout_sec: float = 45.0) -> Any:
        if threading.current_thread() is threading.main_thread():
            return fn()

        done = threading.Event()
        box: dict[str, Any] = {}

        def runner() -> None:
            try:
                box["result"] = fn()
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc
            finally:
                done.set()

        self.root.after(0, runner)
        if not done.wait(timeout=timeout_sec):
            raise TimeoutError("UI thread action timed out")
        if "error" in box:
            raise RuntimeError(str(box["error"]))
        return box.get("result")

    def _start_telegram_control_if_configured(self) -> None:
        env_data = _read_env_map(ENV_PATH)
        token = (env_data.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (env_data.get("TELEGRAM_CHAT_ID") or "").strip() or None
        if not token:
            if not self._telegram_missing_token_reported:
                self._enqueue_log("[telegram-gui] TELEGRAM_BOT_TOKEN not set; remote control disabled")
                self._telegram_missing_token_reported = True
            return
        self._telegram_missing_token_reported = False
        if self._telegram_thread is not None and self._telegram_thread.is_alive():
            return

        from src.botik.control.telegram_gui import GuiTelegramActions, start_gui_telegram_bot_in_thread

        self._telegram_stop_event = threading.Event()
        actions = GuiTelegramActions(
            status=self.telegram_status_text,
            balance=self.telegram_balance_text,
            orders=self.telegram_orders_text,
            start_trading=self.telegram_start_trading,
            stop_trading=self.telegram_stop_trading,
            pull_updates=self.telegram_pull_updates,
            restart_soft=self.telegram_restart_soft,
            restart_hard=self.telegram_restart_hard,
        )
        self._telegram_thread = start_gui_telegram_bot_in_thread(
            token=token,
            actions=actions,
            allowed_chat_id=chat_id,
            stop_event=self._telegram_stop_event,
        )
        self._enqueue_log("[telegram-gui] control bot started")

    def _git_short_head(self) -> str:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return "unknown"
        return (proc.stdout or "").strip() or "unknown"

    def _git_pull_ff_only(self) -> tuple[bool, str]:
        before = self._git_short_head()
        pull = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        output = ((pull.stdout or "") + "\n" + (pull.stderr or "")).strip()
        after = self._git_short_head()
        ok = pull.returncode == 0
        if ok:
            msg = f"git pull OK: {before} -> {after}"
            if output:
                msg += f"\n{output}"
            self._enqueue_log(f"[update] {msg}")
            return True, msg
        msg = f"git pull failed (code={pull.returncode})\n{output}".strip()
        self._enqueue_log(f"[update] {msg}")
        return False, msg

    def _live_rest_context(self) -> dict[str, str]:
        raw_cfg = self._load_yaml()
        env_data = _read_env_map(ENV_PATH)
        mode = str(((raw_cfg.get("execution") or {}).get("mode") or "paper")).strip().lower()
        host = str((raw_cfg.get("bybit") or {}).get("host") or "api-demo.bybit.com").strip()
        enabled_modes = self._extract_enabled_strategy_modes_from_raw(raw_cfg)
        categories: list[str] = []
        for strategy_mode in enabled_modes:
            category = self._mode_runtime(strategy_mode).get("category", "spot")
            if category not in categories:
                categories.append(category)
        if not categories:
            category = str((raw_cfg.get("bybit") or {}).get("market_category") or "spot").strip().lower()
            if category not in {"spot", "linear"}:
                category = "spot"
            categories = [category]
        api_key = (
            env_data.get("BYBIT_API_KEY")
            or os.environ.get("BYBIT_API_KEY")
            or ""
        ).strip()
        api_secret = (
            env_data.get("BYBIT_API_SECRET_KEY")
            or env_data.get("BYBIT_API_SECRET")
            or os.environ.get("BYBIT_API_SECRET_KEY")
            or os.environ.get("BYBIT_API_SECRET")
            or ""
        ).strip()
        rsa_key_path = (
            env_data.get("BYBIT_RSA_PRIVATE_KEY_PATH")
            or os.environ.get("BYBIT_RSA_PRIVATE_KEY_PATH")
            or ""
        ).strip()
        return {
            "mode": mode,
            "host": host,
            "categories": ",".join(categories),
            "api_key": api_key,
            "api_secret": api_secret,
            "rsa_key_path": rsa_key_path,
        }

    async def _cancel_open_orders_live(
        self,
        host: str,
        category: str,
        api_key: str,
        api_secret: str,
        rsa_key_path: str,
    ) -> tuple[bool, str]:
        from src.botik.execution.bybit_rest import BybitRestClient

        client = BybitRestClient(
            base_url=f"https://{host}",
            api_key=api_key,
            api_secret=api_secret or None,
            rsa_private_key_path=rsa_key_path or None,
            category=category,
        )

        before = await client.get_open_orders()
        if before.get("retCode") != 0:
            return False, f"get_open_orders failed: retCode={before.get('retCode')} retMsg={before.get('retMsg')}"
        before_list = (before.get("result") or {}).get("list") or []
        before_count = len(before_list)

        cancel = await client.cancel_all_orders()
        if cancel.get("retCode") != 0:
            return False, f"cancel_all_orders failed: retCode={cancel.get('retCode')} retMsg={cancel.get('retMsg')}"

        await asyncio.sleep(0.6)
        after = await client.get_open_orders()
        if after.get("retCode") != 0:
            return False, f"get_open_orders(after) failed: retCode={after.get('retCode')} retMsg={after.get('retMsg')}"
        after_count = len((after.get("result") or {}).get("list") or [])
        if after_count > 0:
            return False, f"cancel_all incomplete: before={before_count} after={after_count}"
        return True, f"cancel_all OK: before={before_count} after={after_count}"

    def _cancel_open_orders_best_effort(self) -> tuple[bool, str]:
        ctx = self._invoke_on_ui_thread(self._live_rest_context)
        mode = str(ctx.get("mode") or "paper").lower()
        if mode != "live":
            return True, "mode=paper: открытых ордеров на бирже нет"
        api_key = str(ctx.get("api_key") or "")
        api_secret = str(ctx.get("api_secret") or "")
        rsa_key_path = str(ctx.get("rsa_key_path") or "")
        if not api_key or (not api_secret and not rsa_key_path):
            return False, "нет API-ключей для cancel_all"
        categories_raw = str(ctx.get("categories") or "spot")
        categories = [c.strip().lower() for c in categories_raw.split(",") if c.strip()]
        categories = [c for c in categories if c in {"spot", "linear"}] or ["spot"]
        messages: list[str] = []
        ok_all = True
        for category in categories:
            ok, msg = asyncio.run(
                self._cancel_open_orders_live(
                    host=str(ctx.get("host") or "api-demo.bybit.com"),
                    category=category,
                    api_key=api_key,
                    api_secret=api_secret,
                    rsa_key_path=rsa_key_path,
                )
            )
            ok_all = ok_all and ok
            messages.append(f"{category}: {msg}")
        return ok_all, " | ".join(messages)

    @staticmethod
    def _pick_close_price(reference_price: float, side: str) -> float:
        px = max(float(reference_price), 0.0)
        if px <= 0:
            return 0.0
        side_u = str(side or "").strip().upper()
        if side_u == "SELL":
            return px * 0.998
        if side_u == "BUY":
            return px * 1.002
        return px

    async def _manual_close_live(
        self,
        *,
        host: str,
        category: str,
        api_key: str,
        api_secret: str,
        rsa_key_path: str,
        symbol: str,
        side: str,
        qty: float,
        reference_price: float,
    ) -> tuple[bool, str]:
        from src.botik.execution.bybit_rest import BybitRestClient

        if qty <= 0:
            return False, "qty <= 0"
        if reference_price <= 0:
            return False, "invalid reference price"

        client = BybitRestClient(
            base_url=f"https://{host}",
            api_key=api_key,
            api_secret=api_secret or None,
            rsa_private_key_path=rsa_key_path or None,
            category=category,
        )
        side_u = str(side or "").strip().upper()
        if side_u not in {"BUY", "SELL"}:
            return False, f"unsupported side={side}"

        qty_str = self._fmt_price_or_blank(qty, precision=8)
        if not qty_str:
            return False, "invalid qty after format"
        close_price = self._pick_close_price(reference_price, side_u)
        price_str = self._fmt_price_or_blank(close_price, precision=8)
        if not price_str:
            return False, "invalid close price after format"

        order_link_id = f"manual-close-{symbol}-{uuid.uuid4().hex[:10]}"
        ret = await client.place_order(
            symbol=symbol,
            side=side_u.capitalize(),
            qty=qty_str,
            price=price_str,
            order_link_id=order_link_id,
            time_in_force="IOC",
        )
        if ret.get("retCode") != 0:
            return False, f"retCode={ret.get('retCode')} retMsg={ret.get('retMsg')}"
        order_id = str((ret.get("result") or {}).get("orderId") or "")
        return True, f"manual close sent: {symbol} {side_u} qty={qty_str} price={price_str} orderId={order_id}"

    def _selected_open_order_row(self) -> list[Any] | None:
        selected = self.open_orders_tree.selection() if self.open_orders_tree is not None else ()
        if not selected:
            return None
        item_id = selected[0]
        values = self.open_orders_tree.item(item_id, "values") if self.open_orders_tree is not None else ()
        row = list(values or [])
        return row if row else None

    def manual_close_selected_position(self) -> None:
        row = self._selected_open_order_row()
        if not row:
            messagebox.showwarning("Manual Close", "Выберите строку в таблице открытых ордеров/HOLD.")
            return
        if len(row) < 15:
            messagebox.showwarning("Manual Close", "Недостаточно данных в выбранной строке.")
            return

        symbol = str(row[1] or "").strip().upper()
        market = str(row[2] or "").strip().lower()
        side = str(row[4] or "").strip().upper()
        qty = abs(self._safe_float(row[7]))
        now_price = self._safe_float(row[6])
        order_price = self._safe_float(row[5])
        entry_price = self._safe_float(row[9])
        status = str(row[14] or "").strip()

        if not symbol or side not in {"BUY", "SELL"} or qty <= 0:
            messagebox.showwarning("Manual Close", "Невозможно определить symbol/side/qty из выбранной строки.")
            return

        reference_price = now_price if now_price > 0 else (order_price if order_price > 0 else entry_price)
        if reference_price <= 0:
            messagebox.showwarning("Manual Close", "Нет валидной цены (Now/Order/Entry) для manual close.")
            return

        ctx = self._live_rest_context()
        mode = str(ctx.get("mode") or "paper").lower()
        if mode != "live":
            messagebox.showwarning("Manual Close", "Manual close доступен только при execution.mode=live.")
            return
        api_key = str(ctx.get("api_key") or "")
        api_secret = str(ctx.get("api_secret") or "")
        rsa_key_path = str(ctx.get("rsa_key_path") or "")
        if not api_key or (not api_secret and not rsa_key_path):
            messagebox.showerror("Manual Close", "Нет API-ключей/секрета.")
            return

        category = "linear" if market == "linear" else "spot"
        if not messagebox.askyesno(
            "Manual Close",
            f"Отправить IOC закрытие?\n{symbol} {side} qty={qty:.8f}\nstatus={status}\ncategory={category}",
        ):
            return

        def worker() -> None:
            ok, msg = asyncio.run(
                self._manual_close_live(
                    host=str(ctx.get("host") or "api-demo.bybit.com"),
                    category=category,
                    api_key=api_key,
                    api_secret=api_secret,
                    rsa_key_path=rsa_key_path,
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    reference_price=reference_price,
                )
            )
            self._enqueue_log(f"[manual-close] {'OK' if ok else 'FAIL'} {msg}")
            self.root.after(0, self.refresh_runtime_snapshot)

        threading.Thread(target=worker, daemon=True).start()

    def activate_selected_model(self) -> None:
        if self.models_tree is None:
            return
        selected = self.models_tree.selection()
        if not selected:
            messagebox.showwarning("Models", "Выберите модель в таблице.")
            return
        row = list(self.models_tree.item(selected[0], "values") or [])
        if len(row) < 1:
            messagebox.showwarning("Models", "Не удалось прочитать выбранную модель.")
            return
        model_id = str(row[0] or "").strip()
        if not model_id:
            messagebox.showwarning("Models", "Пустой model_id.")
            return
        if not messagebox.askyesno("Models", f"Сделать модель активной?\n{model_id}"):
            return

        raw_cfg = self._load_yaml()
        db_path = self._resolve_db_path(raw_cfg)
        if not db_path.exists():
            messagebox.showerror("Models", f"DB not found: {db_path}")
            return
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "model_registry"):
                messagebox.showerror("Models", "Таблица model_registry не найдена.")
                return
            exists = conn.execute(
                "SELECT 1 FROM model_registry WHERE model_id=? LIMIT 1",
                (model_id,),
            ).fetchone()
            if not exists:
                messagebox.showerror("Models", f"model_id not found: {model_id}")
                return
            conn.execute("UPDATE model_registry SET is_active=0")
            conn.execute("UPDATE model_registry SET is_active=1 WHERE model_id=?", (model_id,))
            conn.commit()
        finally:
            conn.close()
        self._enqueue_log(f"[models] activated model_id={model_id}")
        self.refresh_runtime_snapshot()

    def _telegram_status_text_ui(self) -> str:
        current_version = get_app_version_label()
        mode = self._load_execution_mode()
        running_modes = self._running_trading_modes()
        running_txt = ",".join(running_modes) if running_modes else "none"
        return (
            "GUI supervisor:\n"
            f"version={current_version}\n"
            f"trading={self._trading_group_state().upper()} ({running_txt})\n"
            f"ml={self._status_text(self.ml)}\n"
            f"ml.model={self.ml_model_id_var.get()}\n"
            f"ml.state={self.ml_training_state_var.get()}\n"
            f"execution.mode={mode}\n"
            f"commit={self._git_short_head()}\n"
            "Примечание: запущенный trading-процесс использует код версии на момент старта."
        )

    def _refresh_app_version(self) -> None:
        latest = get_app_version_label()
        if latest == self.app_version:
            return
        self.app_version = latest
        self.root.title(f"Botik Desktop {self.app_version}")
        self.title_label.config(text=f"Botik Control Console {self.app_version}")
        self.version_label.config(text=f"app.version: {self.app_version}")
        self._enqueue_log(f"[ui] app.version updated -> {self.app_version}")

    def telegram_status_text(self) -> str:
        return str(self._invoke_on_ui_thread(self._telegram_status_text_ui))

    def telegram_balance_text(self) -> str:
        snapshot = self._invoke_on_ui_thread(self._load_runtime_snapshot)
        return (
            "Средства:\n"
            f"баланс={snapshot.get('balance_total', 'n/a')}\n"
            f"доступно={snapshot.get('balance_available', 'n/a')}\n"
            f"кошелек={snapshot.get('balance_wallet', 'n/a')}\n"
            f"api={snapshot.get('api_status', 'n/a')}\n"
            f"обновлено={snapshot.get('updated_at', '-')}"
        )

    def telegram_orders_text(self) -> str:
        snapshot = self._invoke_on_ui_thread(self._load_runtime_snapshot)
        rows = list(snapshot.get("open_orders_rows") or [])
        lines = [f"Активные ордера: {snapshot.get('open_orders_count', 0)}"]
        for row in rows[:12]:
            row_list = list(row)
            if len(row_list) >= 15:
                symbol = row_list[1]
                market = row_list[2]
                strategy = row_list[3]
                side = row_list[4]
                order_price = row_list[5]
                now_price = row_list[6]
                qty = row_list[7]
                usd = row_list[8]
                pnl = row_list[11]
                pnl_quote = row_list[12]
                status = row_list[14]
                lines.append(
                    f"{symbol} {market}/{strategy} {side} order={order_price} now={now_price} qty={qty} usd={usd} pnl={pnl} pnl_q={pnl_quote} status={status}"
                )
            elif len(row_list) >= 9:
                symbol = row_list[1]
                side = row_list[2]
                price = row_list[3]
                qty = row_list[4]
                usd = row_list[5]
                status = row_list[8]
                lines.append(f"{symbol} {side} price={price} qty={qty} usd={usd} status={status}")
            elif len(row_list) >= 6:
                symbol = row_list[1]
                side = row_list[2]
                price = row_list[3]
                qty = row_list[4]
                status = row_list[5]
                lines.append(f"{symbol} {side} price={price} qty={qty} status={status}")
        lines.append(f"api={snapshot.get('api_status', 'n/a')}")
        return "\n".join(lines)

    def telegram_start_trading(self) -> str:
        return str(self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False)))

    def telegram_stop_trading(self) -> str:
        return str(self._invoke_on_ui_thread(self._stop_trading_impl))

    def telegram_pull_updates(self) -> str:
        ok, msg = self._git_pull_ff_only()
        if self._running_trading_modes():
            msg += "\nTrading уже запущен на старой версии. Нужен рестарт для применения обновлений."
        return msg if ok else f"Ошибка обновления:\n{msg}"

    def telegram_restart_soft(self) -> str:
        lines: list[str] = []
        ok_cancel_before, msg_cancel_before = self._cancel_open_orders_best_effort()
        lines.append(f"[1/4] cancel before stop: {msg_cancel_before}")
        lines.append(f"[2/4] {self._invoke_on_ui_thread(self._stop_trading_impl)}")
        ok_cancel_after, msg_cancel_after = self._cancel_open_orders_best_effort()
        lines.append(f"[3/4] cancel after stop: {msg_cancel_after}")
        lines.append(f"[4/4] {self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False))}")
        if not ok_cancel_before or not ok_cancel_after:
            lines.append("Внимание: cancel_all не полностью успешен, проверьте open orders.")
        return "\n".join(lines)

    def telegram_restart_hard(self) -> str:
        lines: list[str] = []
        ok_pull, pull_msg = self._git_pull_ff_only()
        lines.append(f"[1/3] update: {pull_msg}")
        lines.append(f"[2/3] {self._invoke_on_ui_thread(self._stop_trading_impl)}")
        lines.append(f"[3/3] {self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False))}")
        if not ok_pull:
            lines.append("Обновление не применилось, запущена текущая локальная версия.")
        return "\n".join(lines)

    @staticmethod
    def _detect_log_level(text: str) -> str:
        upper = str(text or "").upper()
        if "ERROR" in upper:
            return "ERROR"
        if "WARNING" in upper or "WARN" in upper:
            return "WARNING"
        if "DEBUG" in upper:
            return "DEBUG"
        if "INFO" in upper:
            return "INFO"
        return "INFO"

    @staticmethod
    def _detect_log_pair(text: str) -> str:
        upper = str(text or "").upper()
        found = re.search(r"\b([A-Z0-9]{2,}(?:USDT|USDC|USD|BTC|ETH))\b", upper)
        return str(found.group(1) if found else "")

    def _log_matches_full_filters(self, text: str) -> bool:
        msg = str(text or "")
        level_filter = str(self.log_filter_level_var.get() or "ALL").strip().upper()
        pair_filter = str(self.log_filter_pair_var.get() or "ALL").strip().upper()
        query_filter = str(self.log_filter_query_var.get() or "").strip().lower()

        if level_filter not in {"", "ALL"} and self._detect_log_level(msg) != level_filter:
            return False
        if pair_filter not in {"", "ALL"} and pair_filter not in msg.upper():
            return False
        if query_filter and query_filter not in msg.lower():
            return False
        return True

    def _sync_log_pair_filter_values(self) -> None:
        if self.log_pair_filter_combo is None:
            return
        values = ["ALL", *sorted(self._known_log_pairs)]
        self.log_pair_filter_combo.configure(values=values)
        current = str(self.log_filter_pair_var.get() or "ALL").strip().upper() or "ALL"
        if current != "ALL" and current not in self._known_log_pairs:
            self.log_filter_pair_var.set("ALL")

    def _append_full_log_line(self, msg: str) -> None:
        if self.log_text_full is None:
            return
        if not self._log_matches_full_filters(msg):
            return
        self.log_text_full.insert(tk.END, msg + "\n")
        if self._log_autoscroll_full:
            self.log_text_full.see(tk.END)

    def _refresh_full_log_filtered_view(self) -> None:
        if self.log_text_full is None:
            return
        self.log_text_full.delete("1.0", tk.END)
        for msg in self._log_messages:
            if self._log_matches_full_filters(msg):
                self.log_text_full.insert(tk.END, msg + "\n")
        self._trim_text_widget(self.log_text_full, self._max_ui_log_lines_full)
        if self._log_autoscroll_full:
            self.log_text_full.see(tk.END)
        self._update_log_jump_buttons()

    def _on_log_filter_changed(self) -> None:
        self._refresh_full_log_filtered_view()

    def _clear_log_filters(self) -> None:
        self.log_filter_level_var.set("ALL")
        self.log_filter_pair_var.set("ALL")
        self.log_filter_query_var.set("")
        self._on_log_filter_changed()

    def _drain_logs(self) -> None:
        got = False
        dropped = 0
        pair_values_changed = False
        while self.log_queue.qsize() > self._log_backlog_soft_limit:
            try:
                self.log_queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
            if self.log_queue.qsize() <= self._log_backlog_keep:
                break
        if dropped > 0:
            msg = f"[ui] log backlog trimmed: dropped={dropped}"
            self._log_messages.append(msg)
            self.log_text.insert(tk.END, msg + "\n")
            if self._log_autoscroll_main:
                self.log_text.see(tk.END)
            self._append_full_log_line(msg)
            got = True

        processed = 0
        while processed < max(int(self._max_log_batch_per_tick), 1):
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            got = True
            processed += 1
            self._log_messages.append(msg)
            pair = self._detect_log_pair(msg)
            if pair and pair not in self._known_log_pairs:
                self._known_log_pairs.add(pair)
                pair_values_changed = True
            self.log_text.insert(tk.END, msg + "\n")
            if self._log_autoscroll_main:
                self.log_text.see(tk.END)
            self._append_full_log_line(msg)
        if pair_values_changed:
            self._sync_log_pair_filter_values()
        if got:
            self._trim_text_widget(self.log_text, self._max_ui_log_lines_main)
            if self.log_text_full is not None:
                self._trim_text_widget(self.log_text_full, self._max_ui_log_lines_full)
            self._update_log_jump_buttons()
        self.root.after(120, self._drain_logs)

    def _on_log_yview(self, which: str, first: str, last: str) -> None:
        try:
            last_pos = float(last)
        except (TypeError, ValueError):
            last_pos = 1.0
        if which == "main":
            if self.log_scroll_main is not None:
                self.log_scroll_main.set(first, last)
            self._log_autoscroll_main = last_pos >= 0.999
        else:
            if self.log_scroll_full is not None:
                self.log_scroll_full.set(first, last)
            self._log_autoscroll_full = last_pos >= 0.999
        self._update_log_jump_buttons()

    def _update_log_jump_buttons(self) -> None:
        if self.log_jump_main is not None:
            visible = bool(self.log_jump_main.winfo_manager())
            if self._log_autoscroll_main and visible:
                self.log_jump_main.pack_forget()
            elif not self._log_autoscroll_main and not visible:
                self.log_jump_main.pack(side=tk.RIGHT)
        if self.log_jump_full is not None:
            visible = bool(self.log_jump_full.winfo_manager())
            if self._log_autoscroll_full and visible:
                self.log_jump_full.pack_forget()
            elif not self._log_autoscroll_full and not visible:
                self.log_jump_full.pack(side=tk.RIGHT)

    def _jump_log_to_end(self, which: str) -> None:
        if which == "main":
            self.log_text.see(tk.END)
            self._log_autoscroll_main = True
        elif self.log_text_full is not None:
            self.log_text_full.see(tk.END)
            self._log_autoscroll_full = True
        self._update_log_jump_buttons()

    def _load_execution_mode(self) -> str:
        cfg_path = Path(self.config_var.get())
        if not cfg_path.exists():
            return "config not found"
        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return "config parse error"
        mode = ((raw.get("execution") or {}).get("mode") or "live").strip().lower()
        return mode

    def _set_led(self, canvas: tk.Canvas, color: str) -> None:
        canvas.delete("all")
        canvas.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _toggle_window_state(self, _event: tk.Event | None = None) -> str:
        if os.name == "nt":
            state = str(self.root.state()).lower()
            self.root.state("normal" if state == "zoomed" else "zoomed")
        else:
            try:
                full = bool(self.root.attributes("-fullscreen"))
            except tk.TclError:
                full = False
            self.root.attributes("-fullscreen", not full)
        return "break"

    def _status_text(self, proc: ManagedProcess) -> str:
        if proc.state == "running":
            return "RUNNING"
        if proc.state == "error":
            code = proc.last_exit_code if proc.last_exit_code is not None else "?"
            return f"ERROR (exit={code})"
        return "STOPPED"

    def _status_color(self, proc: ManagedProcess) -> str:
        if proc.state == "running":
            return "#28A745"  # green
        if proc.state == "error":
            return "#D93025"  # red
        return "#7A7A7A"  # gray

    def _update_status(self) -> None:
        self._refresh_app_version()
        mode = self._load_execution_mode()
        self.mode_label.config(text=f"execution.mode: {mode}")
        running_modes = self._running_trading_modes()
        trading_state = self._trading_group_state()
        if running_modes:
            self.trading_label.config(text=f"trading: RUNNING ({','.join(running_modes)})")
        elif trading_state == "error":
            self.trading_label.config(text="trading: ERROR")
        else:
            self.trading_label.config(text="trading: STOPPED")
        self.ml_label.config(text=f"ml: {self._status_text(self.ml)}")
        if trading_state == "running":
            trading_color = "#28A745"
        elif trading_state == "error":
            trading_color = "#D93025"
        else:
            trading_color = "#7A7A7A"
        self._set_led(self.trading_led, trading_color)
        self._set_led(self.ml_led, self._status_color(self.ml))
        if self.ml.running and not self.ml_training_paused:
            mode = str(self.ml_runtime_mode or "bootstrap").strip().lower()
            if mode == "bootstrap":
                self.ml_training_state_var.set("bootstrap")
            elif mode == "online":
                self.ml_training_state_var.set("online")
            elif mode == "predict":
                self.ml_training_state_var.set("predict")
            else:
                self.ml_training_state_var.set("training")
            if not self._ml_progress_running:
                self.ml_progress.start(9)
                self._ml_progress_running = True
        else:
            if self._ml_progress_running:
                self.ml_progress.stop()
                self._ml_progress_running = False
            if self.ml.running and self.ml_training_paused:
                self.ml_training_state_var.set("paused")
            elif self.ml.state == "error":
                self.ml_training_state_var.set("error")
            else:
                self.ml_training_state_var.set("stopped")
        self.root.after(500, self._update_status)

    def _cmd(self, *parts: str) -> list[str]:
        return [self.python_var.get(), *parts]

    @staticmethod
    def _normalize_strategy_modes(modes: list[str] | tuple[str, ...] | None) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in modes or []:
            mode = str(raw or "").strip().lower()
            if mode not in STRATEGY_MODE_ORDER or mode in seen:
                continue
            seen.add(mode)
            out.append(mode)
        if not out:
            out = ["spot_spread"]
        return out

    @staticmethod
    def _mode_runtime(mode: str) -> dict[str, str]:
        return dict(STRATEGY_MODE_RUNTIME.get(mode, STRATEGY_MODE_RUNTIME["spot_spread"]))

    def _enabled_strategy_modes_from_ui(self) -> list[str]:
        modes: list[str] = []
        if bool(self.enable_spot_spread_var.get()):
            modes.append("spot_spread")
        if bool(self.enable_spot_spike_var.get()):
            modes.append("spot_spike")
        if bool(self.enable_futures_spike_var.get()):
            modes.append("futures_spike_reversal")
        return self._normalize_strategy_modes(modes)

    def _set_enabled_strategy_modes_ui(self, modes: list[str]) -> None:
        normalized = set(self._normalize_strategy_modes(modes))
        self.enable_spot_spread_var.set("spot_spread" in normalized)
        self.enable_spot_spike_var.set("spot_spike" in normalized)
        self.enable_futures_spike_var.set("futures_spike_reversal" in normalized)
        if not any([self.enable_spot_spread_var.get(), self.enable_spot_spike_var.get(), self.enable_futures_spike_var.get()]):
            self.enable_spot_spread_var.set(True)

    def _extract_enabled_strategy_modes_from_raw(self, raw_cfg: dict[str, Any]) -> list[str]:
        strategy = raw_cfg.get("strategy") or {}
        raw_modes = strategy.get("ui_enabled_strategy_modes")
        if isinstance(raw_modes, list):
            return self._normalize_strategy_modes([str(m) for m in raw_modes])
        preset = self._detect_strategy_preset(raw_cfg)
        return self._normalize_strategy_modes([preset])

    def _running_trading_modes(self) -> list[str]:
        return [mode for mode, proc in self.trading_processes.items() if proc.running]

    def _trading_group_state(self) -> str:
        procs = list(self.trading_processes.values())
        if any(p.running for p in procs):
            return "running"
        if any(p.state == "error" for p in procs):
            return "error"
        return "stopped"

    def _load_yaml(self) -> dict:
        cfg_path = Path(self.config_var.get())
        if not cfg_path.exists():
            return {}
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _fmt_num(value: Any, precision: int = 4) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "n/a"
        return f"{v:.{precision}f}"

    @staticmethod
    def _fmt_price_or_blank(value: Any, precision: int = 8) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v <= 0:
            return ""
        return f"{v:.{precision}f}".rstrip("0").rstrip(".")

    @staticmethod
    def _fmt_usd_notional(price: Any, qty: Any) -> str:
        try:
            p = float(price)
            q = abs(float(qty))
        except (TypeError, ValueError):
            return ""
        if p <= 0 or q <= 0:
            return ""
        return f"{p * q:.2f}"

    @staticmethod
    def _fmt_pct_or_blank(value: Any, precision: int = 2) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        return f"{v:.{precision}f}%"

    @staticmethod
    def _infer_strategy_label(order_link_id: Any, fallback: str = "") -> str:
        link = str(order_link_id or "").strip().lower()
        if link.startswith("spkrev-"):
            return "SPIKE_REV"
        if link.startswith("spk-"):
            return "SPIKE_BURST"
        if link.startswith("mm-"):
            return "SPREAD"
        if link.startswith("px-"):
            return "EXIT_QUOTE"
        if link.startswith("force-exit-"):
            return "FORCE_EXIT"
        value = str(fallback or "").strip().upper()
        return value

    @staticmethod
    def _reindex_rows(rows: list[tuple[Any, ...]], width: int) -> list[tuple[Any, ...]]:
        out: list[tuple[Any, ...]] = []
        for idx, row in enumerate(rows, start=1):
            row_list = list(row)
            if len(row_list) < width:
                row_list.extend([""] * (width - len(row_list)))
            row_list = row_list[:width]
            row_list[0] = str(idx)
            out.append(tuple(row_list))
        return out

    @staticmethod
    def _expected_exit_from_entry(entry_price: float, raw_cfg: dict[str, Any]) -> float:
        if entry_price <= 0:
            return 0.0
        strategy_cfg = raw_cfg.get("strategy") or {}
        fees_cfg = raw_cfg.get("fees") or {}
        target = max(float(strategy_cfg.get("target_profit") or 0.0), 0.0)
        safety = max(float(strategy_cfg.get("safety_buffer") or 0.0), 0.0)
        maker_fee = max(float(fees_cfg.get("maker_rate") or 0.0), 0.0)
        return entry_price * (1.0 + target + safety + (2.0 * maker_fee))

    @staticmethod
    def _split_local_datetime(ts_raw: str) -> tuple[str, str]:
        raw = str(ts_raw or "").strip()
        if not raw:
            return "", ""
        try:
            normalized = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone()
            return local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M:%S")
        except Exception:
            return "", raw

    def _resolve_db_path(self, raw_cfg: dict[str, Any]) -> Path:
        rel = str((raw_cfg.get("storage") or {}).get("path") or "data/botik.db")
        path = Path(rel)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    def _resolve_training_pause_flag(self, raw_cfg: dict[str, Any]) -> Path:
        rel = str((raw_cfg.get("ml") or {}).get("training_pause_flag_path") or "data/ml/training.paused")
        path = Path(rel)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    def _resolve_botik_log_path(self, raw_cfg: dict[str, Any]) -> Path:
        rel = str((raw_cfg.get("logging") or {}).get("dir") or "logs")
        path = Path(rel)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path / "botik.log"

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        return bool(row)

    def _read_ml_metrics(self, db_path: Path) -> dict[str, Any]:
        base = {
            "model_id": "bootstrap",
            "net_edge_mean": 0.0,
            "win_rate": 0.0,
            "fill_rate": 0.0,
            "fill_filled_signals": 0,
            "fill_total_signals": 0,
            "chart": [],
            "closed_count": 0,
            "executions_total": 0,
            "paired_closed_signals": 0,
            "filled_orders": 0,
        }
        if not db_path.exists():
            return base
        conn = sqlite3.connect(str(db_path))
        try:
            if self._table_exists(conn, "model_registry"):
                row = conn.execute(
                    """
                    SELECT model_id
                    FROM model_registry
                    WHERE is_active = 1
                    ORDER BY created_at_utc DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row and row[0]:
                    base["model_id"] = str(row[0])

            if self._table_exists(conn, "signals"):
                sid_row = conn.execute(
                    """
                    SELECT COALESCE(model_id, active_model_id, '')
                    FROM signals
                    WHERE COALESCE(model_id, active_model_id, '') <> ''
                    ORDER BY ts_signal_ms DESC
                    LIMIT 1
                    """
                ).fetchone()
                if sid_row and sid_row[0]:
                    base["model_id"] = str(sid_row[0])

            if self._table_exists(conn, "outcomes"):
                out_rows = conn.execute(
                    """
                    SELECT COALESCE(net_edge_bps, 0.0), COALESCE(was_profitable, 0)
                    FROM outcomes
                    ORDER BY closed_at_utc DESC
                    LIMIT 200
                    """
                ).fetchall()
                base["closed_count"] = int(conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0])
                if out_rows:
                    clipped = [max(min(float(r[0] or 0.0), 5000.0), -5000.0) for r in out_rows]
                    base["net_edge_mean"] = float(sum(clipped) / len(clipped))
                    base["win_rate"] = float(sum(int(r[1] or 0) for r in out_rows) / len(out_rows))

            if self._table_exists(conn, "signals"):
                fill_row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_signals,
                        SUM(
                            CASE
                                WHEN EXISTS (
                                    SELECT 1 FROM executions_raw e
                                    WHERE e.signal_id = s.signal_id
                                ) THEN 1
                                ELSE 0
                            END
                        ) AS filled_signals
                    FROM (
                        SELECT signal_id
                        FROM signals
                        ORDER BY ts_signal_ms DESC
                        LIMIT 200
                    ) s
                    """
                ).fetchone()
                total = int(fill_row[0] or 0) if fill_row else 0
                filled = int(fill_row[1] or 0) if fill_row else 0
                base["fill_rate"] = float(filled / total) if total > 0 else 0.0
                base["fill_total_signals"] = total
                base["fill_filled_signals"] = filled

            if self._table_exists(conn, "executions_raw"):
                base["executions_total"] = int(conn.execute("SELECT COUNT(*) FROM executions_raw").fetchone()[0])
                pair_row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT signal_id
                        FROM executions_raw
                        WHERE COALESCE(signal_id, '') <> ''
                        GROUP BY signal_id
                        HAVING
                            SUM(CASE WHEN lower(COALESCE(side, '')) = 'buy' THEN 1 ELSE 0 END) > 0
                            AND
                            SUM(CASE WHEN lower(COALESCE(side, '')) = 'sell' THEN 1 ELSE 0 END) > 0
                    ) x
                    """
                ).fetchone()
                base["paired_closed_signals"] = int(pair_row[0] or 0) if pair_row else 0

            if self._table_exists(conn, "order_events"):
                filled_row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM order_events
                    WHERE upper(COALESCE(order_status, '')) = 'FILLED'
                    """
                ).fetchone()
                base["filled_orders"] = int(filled_row[0] or 0) if filled_row else 0

            if self._table_exists(conn, "model_stats"):
                stat_row = conn.execute(
                    """
                    SELECT COALESCE(model_id, ''), COALESCE(net_edge_mean, 0.0), COALESCE(win_rate, 0.0), COALESCE(fill_rate, 0.0)
                    FROM model_stats
                    ORDER BY ts_ms DESC
                    LIMIT 1
                    """
                ).fetchone()
                if stat_row:
                    if stat_row[0]:
                        base["model_id"] = str(stat_row[0])
                    base["net_edge_mean"] = float(stat_row[1] or 0.0)
                    base["win_rate"] = float(stat_row[2] or 0.0)
                    base["fill_rate"] = float(stat_row[3] or 0.0)

                chart_rows = conn.execute(
                    """
                    SELECT COALESCE(net_edge_mean, 0.0)
                    FROM model_stats
                    ORDER BY ts_ms DESC
                    LIMIT 60
                    """
                ).fetchall()
                if chart_rows:
                    base["chart"] = [float(r[0] or 0.0) for r in reversed(chart_rows)]

            if not base["chart"] and self._table_exists(conn, "outcomes"):
                fallback_rows = conn.execute(
                    """
                    SELECT COALESCE(net_edge_bps, 0.0)
                    FROM outcomes
                    ORDER BY closed_at_utc DESC
                    LIMIT 60
                    """
                ).fetchall()
                base["chart"] = [float(r[0] or 0.0) for r in reversed(fallback_rows)]
            return base
        finally:
            conn.close()

    def _read_latest_symbol_prices(self, db_path: Path) -> dict[str, float]:
        if not db_path.exists():
            return {}
        conn = sqlite3.connect(str(db_path))
        try:
            prices: dict[str, float] = {}
            if self._table_exists(conn, "signals"):
                rows = conn.execute(
                    """
                    SELECT s.symbol, COALESCE(s.mid, s.entry_price, 0.0)
                    FROM signals s
                    JOIN (
                        SELECT symbol, MAX(ts_signal_ms) AS max_ts
                        FROM signals
                        GROUP BY symbol
                    ) last ON last.symbol = s.symbol AND last.max_ts = s.ts_signal_ms
                    """
                ).fetchall()
                for sym_raw, price_raw in rows:
                    symbol = str(sym_raw or "").upper().strip()
                    price = float(price_raw or 0.0)
                    if symbol and price > 0:
                        prices[symbol] = price

            if self._table_exists(conn, "executions_raw"):
                rows = conn.execute(
                    """
                    SELECT e.symbol, COALESCE(e.exec_price, 0.0)
                    FROM executions_raw e
                    JOIN (
                        SELECT symbol, MAX(COALESCE(exec_time_ms, 0)) AS max_ts
                        FROM executions_raw
                        GROUP BY symbol
                    ) last ON last.symbol = e.symbol AND last.max_ts = COALESCE(e.exec_time_ms, 0)
                    """
                ).fetchall()
                for sym_raw, price_raw in rows:
                    symbol = str(sym_raw or "").upper().strip()
                    if not symbol or symbol in prices:
                        continue
                    price = float(price_raw or 0.0)
                    if price > 0:
                        prices[symbol] = price
            return prices
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    @staticmethod
    def _extract_log_symbol(line: str) -> str:
        marker = "symbol="
        start = line.find(marker)
        if start < 0:
            return ""
        pos = start + len(marker)
        end = pos
        while end < len(line):
            ch = line[end]
            if ch in {" ", ",", ";", "|"}:
                break
            end += 1
        return line[pos:end].strip().upper()

    def _read_dust_blocked_symbols(self, log_path: Path, max_bytes: int = 350_000) -> set[str]:
        if not log_path.exists():
            return set()
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(size - max(max_bytes, 4_096), 0), os.SEEK_SET)
                chunk = handle.read()
        except OSError:
            return set()

        text = chunk.decode("utf-8", errors="replace")
        blocked: set[str] = set()
        for line in reversed(text.splitlines()):
            if "symbol=" not in line:
                continue
            dust_force_exit = "Force-exit skipped as dust" in line
            dust_exit_quote = "Position-exit quote skipped" in line and "invalid_qty_after_normalization" in line
            if not dust_force_exit and not dust_exit_quote:
                continue
            symbol = self._extract_log_symbol(line)
            if symbol:
                blocked.add(symbol)
        return blocked

    def _annotate_open_rows(
        self,
        rows: list[tuple[Any, ...]],
        latest_price: dict[str, float],
        dust_blocked_symbols: set[str],
    ) -> list[tuple[Any, ...]]:
        out: list[tuple[Any, ...]] = []
        for row in rows:
            values = list(row)
            if len(values) < 15:
                values.extend([""] * (15 - len(values)))
            values = values[:15]

            symbol = str(values[1] or "").upper().strip()
            side = str(values[4] or "").strip().lower()
            order_price = self._safe_float(values[5])
            now_price = self._safe_float(values[6])
            qty = abs(self._safe_float(values[7]))
            entry = self._safe_float(values[9])
            target = self._safe_float(values[10])
            status = str(values[14] or "").strip()
            strategy = str(values[3] or "").strip().upper()
            if not strategy:
                strategy = "HOLD" if status.upper().startswith("HOLD") else ""
            values[3] = strategy

            if now_price <= 0 and symbol:
                now_price = float(latest_price.get(symbol, 0.0))
            if order_price <= 0 and status.upper().startswith("HOLD"):
                order_price = target

            pnl_pct: float | None = None
            if entry > 0 and now_price > 0:
                direction = 1.0 if side in {"sell", ""} else -1.0
                pnl_pct = ((now_price - entry) / entry) * 100.0 * direction

            status_upper = status.upper()
            if status_upper.startswith("HOLD"):
                if symbol in dust_blocked_symbols:
                    status = "HOLD:DUST_BLOCKED"
                elif target > 0 and now_price > 0:
                    status = "HOLD:WAIT_TARGET" if now_price < target else "HOLD:EXIT_READY"
                else:
                    status = "HOLD"

            values[5] = self._fmt_price_or_blank(order_price, precision=8)
            values[6] = self._fmt_price_or_blank(now_price, precision=8)
            values[7] = self._fmt_price_or_blank(qty, precision=8)
            ref_price = now_price if now_price > 0 else order_price
            if ref_price > 0 and qty > 0:
                values[8] = self._fmt_usd_notional(ref_price, qty)
            values[11] = self._fmt_pct_or_blank(pnl_pct, precision=2) if pnl_pct is not None else ""
            pnl_quote: float | None = None
            if entry > 0 and now_price > 0 and qty > 0:
                if side in {"sell", ""}:
                    pnl_quote = (now_price - entry) * qty
                else:
                    pnl_quote = (entry - now_price) * qty
            values[12] = self._fmt_num(pnl_quote, precision=4) if pnl_quote is not None else ""

            progress_text = ""
            if entry > 0 and target > 0 and abs(target - entry) > 1e-12 and now_price > 0:
                progress = ((now_price - entry) / (target - entry)) * 100.0
                progress_text = f"{progress:.0f}%"
            values[13] = progress_text
            values[14] = status
            out.append(tuple(values))
        return self._reindex_rows(out, width=15)

    def _schedule_runtime_refresh(self, initial_delay_ms: int | None = None) -> None:
        delay_ms = self._runtime_refresh_interval_ms if initial_delay_ms is None else int(initial_delay_ms)
        self.root.after(delay_ms, self._runtime_refresh_tick)

    def _runtime_refresh_tick(self) -> None:
        self.refresh_runtime_snapshot()
        self._schedule_runtime_refresh()

    def refresh_runtime_snapshot(self) -> None:
        with self._runtime_refresh_lock:
            if self._runtime_refresh_inflight:
                return
            self._runtime_refresh_inflight = True
        threading.Thread(target=self._load_runtime_snapshot_worker, daemon=True).start()

    def _load_runtime_snapshot_worker(self) -> None:
        try:
            snapshot = self._load_runtime_snapshot()
            self.root.after(0, lambda s=snapshot: self._apply_runtime_snapshot(s))
        except Exception as exc:
            self._enqueue_log(f"[ui] runtime snapshot error: {exc}")
        finally:
            with self._runtime_refresh_lock:
                self._runtime_refresh_inflight = False

    def _load_runtime_snapshot(self) -> dict[str, Any]:
        raw_cfg = self._load_yaml()
        env_data = _read_env_map(ENV_PATH)
        mode = str(((raw_cfg.get("execution") or {}).get("mode") or "paper")).strip().lower()
        enabled_modes = self._extract_enabled_strategy_modes_from_raw(raw_cfg)
        primary_mode = enabled_modes[0] if enabled_modes else "spot_spread"
        primary_runtime = self._mode_runtime(primary_mode)
        market_label = str(primary_runtime.get("category") or "spot").upper()
        strategy_label = str(primary_runtime.get("strategy_label") or "SPREAD").upper()
        ml_mode = str(((raw_cfg.get("ml") or {}).get("mode") or "bootstrap")).strip().lower()
        if ml_mode not in {"bootstrap", "train", "predict", "online"}:
            ml_mode = "bootstrap"
        db_path = self._resolve_db_path(raw_cfg)
        botik_log_path = self._resolve_botik_log_path(raw_cfg)
        pause_flag_path = self._resolve_training_pause_flag(raw_cfg)
        runtime_caps = runtime_capabilities_for_mode(mode)
        ops_status = load_runtime_ops_status_snapshot(db_path)
        batch_size = max(int((raw_cfg.get("ml") or {}).get("train_batch_size") or 50), 1)
        ml_metrics = self._read_ml_metrics(db_path)
        closed_count = int(ml_metrics.get("closed_count", 0))
        paired_count = int(ml_metrics.get("paired_closed_signals", 0))
        progress_anchor = max(closed_count, paired_count)
        progress_pct = float((progress_anchor % batch_size) / batch_size * 100.0)
        latest_price = self._read_latest_symbol_prices(db_path)
        dust_blocked_symbols = self._read_dust_blocked_symbols(botik_log_path)
        hold_rows = self._read_local_hold_rows(
            db_path,
            raw_cfg,
            latest_price=latest_price,
            dust_blocked_symbols=dust_blocked_symbols,
            market_label=market_label,
            strategy_label=strategy_label,
        )
        history_rows_main = self._read_local_order_history(db_path, raw_cfg, limit=10)
        try:
            active_tab = str(self._invoke_on_ui_thread(self._active_tab_key, timeout_sec=1.5))
        except Exception:
            active_tab = "control"
        now_mono = time.monotonic()
        heavy_due = (now_mono - float(self._last_heavy_refresh_ts)) >= float(self._heavy_refresh_min_interval_sec)
        need_heavy_refresh = heavy_due or active_tab in {"stats", "models"}
        if need_heavy_refresh:
            history_rows_full = self._read_local_order_history(db_path, raw_cfg, limit=3000)
            history_total = self._read_order_history_count(db_path)
            outcomes_summary = self._read_outcomes_summary(db_path)
            stats_cum_pnl_chart = self._read_cumulative_pnl_chart(db_path, max_points=240)
            balance_rows, balance_delta_total = self._read_balance_flow_events(db_path, max_rows=500)
            spot_holdings_rows = self._read_spot_holdings_rows(db_path, limit=400)
            futures_positions_rows = self._read_futures_positions_rows(db_path, limit=400)
            futures_orders_rows = self._read_futures_open_orders_rows(db_path, limit=400)
            reconciliation_issue_rows = self._read_reconciliation_issue_rows(db_path, limit=400)
            model_rows = self._read_model_registry_rows(db_path, limit=400)
            self._cached_heavy_snapshot = {
                "history_rows_full": history_rows_full,
                "history_total": int(history_total),
                "outcomes_summary": dict(outcomes_summary),
                "stats_cum_pnl_chart": list(stats_cum_pnl_chart),
                "balance_rows": list(balance_rows),
                "balance_delta_total": float(balance_delta_total),
                "spot_holdings_rows": list(spot_holdings_rows),
                "futures_positions_rows": list(futures_positions_rows),
                "futures_orders_rows": list(futures_orders_rows),
                "reconciliation_issue_rows": list(reconciliation_issue_rows),
                "model_rows": list(model_rows),
            }
            self._last_heavy_refresh_ts = now_mono
        else:
            cached = dict(self._cached_heavy_snapshot)
            history_rows_full = list(cached.get("history_rows_full") or [])
            history_total = int(cached.get("history_total") or 0)
            outcomes_summary = dict(cached.get("outcomes_summary") or {})
            stats_cum_pnl_chart = list(cached.get("stats_cum_pnl_chart") or [])
            balance_rows = list(cached.get("balance_rows") or [])
            balance_delta_total = float(cached.get("balance_delta_total") or 0.0)
            spot_holdings_rows = list(cached.get("spot_holdings_rows") or [])
            futures_positions_rows = list(cached.get("futures_positions_rows") or [])
            futures_orders_rows = list(cached.get("futures_orders_rows") or [])
            reconciliation_issue_rows = list(cached.get("reconciliation_issue_rows") or [])
            model_rows = list(cached.get("model_rows") or [])

        snapshot: dict[str, Any] = {
            "balance_total": "n/a",
            "balance_available": "n/a",
            "balance_wallet": "n/a",
            "open_orders_count": 0,
            "open_orders_rows": [],
            "history_rows": history_rows_main,
            "history_rows_full": history_rows_full,
            "stats_orders_total": int(history_total),
            "stats_outcomes_total": int(outcomes_summary.get("total", 0)),
            "stats_positive_count": int(outcomes_summary.get("positive", 0)),
            "stats_negative_count": int(outcomes_summary.get("negative", 0)),
            "stats_neutral_count": int(outcomes_summary.get("neutral", 0)),
            "stats_net_pnl_quote": float(outcomes_summary.get("sum_net_pnl_quote", 0.0)),
            "stats_avg_pnl_quote": float(outcomes_summary.get("avg_net_pnl_quote", 0.0)),
            "stats_cum_pnl_chart": stats_cum_pnl_chart,
            "stats_balance_rows": balance_rows,
            "stats_balance_events": len(balance_rows),
            "stats_balance_delta_total": float(balance_delta_total),
            "stats_spot_holdings_rows": spot_holdings_rows,
            "stats_futures_positions_rows": futures_positions_rows,
            "stats_futures_orders_rows": futures_orders_rows,
            "stats_reconciliation_issue_rows": reconciliation_issue_rows,
            "model_rows": model_rows,
            "models_total": len(model_rows),
            "api_status": f"mode={mode}; modes={','.join(enabled_modes)}",
            "updated_at": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
            "runtime_capabilities_status": (
                f"capabilities: recon={runtime_caps.get('reconciliation')} | protection={runtime_caps.get('protection')}"
            ),
            "reconciliation_status_line": (
                f"reconciliation: {ops_status.get('reconciliation_last_status')} @ {ops_status.get('reconciliation_last_timestamp')} "
                f"({ops_status.get('reconciliation_last_trigger')})"
            ),
            "panel_freshness_line": (
                f"freshness: spot={ops_status.get('spot_holdings_freshness')} | fut_pos={ops_status.get('futures_positions_freshness')} "
                f"| fut_ord={ops_status.get('futures_orders_freshness')} | issues={ops_status.get('reconciliation_issues_freshness')} "
                f"| funding={ops_status.get('futures_funding_freshness')} | liq={ops_status.get('futures_liq_snapshots_freshness')}"
            ),
            "futures_protection_status_line": (
                f"protection: {ops_status.get('futures_protection_line')}; "
                f"{ops_status.get('futures_risk_telemetry_line')}"
            ),
            "reconciliation_last_status": str(ops_status.get("reconciliation_last_status") or "skipped"),
            "reconciliation_last_timestamp": str(ops_status.get("reconciliation_last_timestamp") or "-"),
            "reconciliation_last_trigger": str(ops_status.get("reconciliation_last_trigger") or "-"),
            "spot_holdings_freshness": str(ops_status.get("spot_holdings_freshness") or "-"),
            "futures_positions_freshness": str(ops_status.get("futures_positions_freshness") or "-"),
            "futures_orders_freshness": str(ops_status.get("futures_orders_freshness") or "-"),
            "reconciliation_issues_freshness": str(ops_status.get("reconciliation_issues_freshness") or "-"),
            "futures_funding_freshness": str(ops_status.get("futures_funding_freshness") or "-"),
            "futures_liq_snapshots_freshness": str(ops_status.get("futures_liq_snapshots_freshness") or "-"),
            "futures_protection_counts": dict(ops_status.get("futures_protection_counts") or {}),
            "ml_model_id": str(ml_metrics.get("model_id") or "bootstrap"),
            "ml_net_edge_mean": float(ml_metrics.get("net_edge_mean") or 0.0),
            "ml_win_rate": float(ml_metrics.get("win_rate") or 0.0),
            "ml_fill_rate": float(ml_metrics.get("fill_rate") or 0.0),
            "ml_fill_filled": int(ml_metrics.get("fill_filled_signals") or 0),
            "ml_fill_total": int(ml_metrics.get("fill_total_signals") or 0),
            "ml_executions_total": int(ml_metrics.get("executions_total") or 0),
            "ml_paired_closed_signals": paired_count,
            "ml_filled_orders": int(ml_metrics.get("filled_orders") or 0),
            "ml_chart": list(ml_metrics.get("chart") or []),
            "ml_training_paused": pause_flag_path.exists(),
            "ml_training_progress": progress_pct,
            "ml_closed_count": closed_count,
            "ml_batch_size": batch_size,
            "ml_runtime_mode": ml_mode,
        }

        if mode == "paper":
            snapshot["runtime_capabilities_status"] = "capabilities: recon=unsupported | protection=unsupported (paper mode)"
            snapshot["reconciliation_status_line"] = "reconciliation: unsupported (paper mode)"
            snapshot["futures_protection_status_line"] = "protection: unsupported (paper mode); funding=unsupported | liq=unsupported"
        if mode != "live":
            local_open = self._read_local_open_orders(
                db_path,
                market_label=market_label,
                strategy_default=strategy_label,
            )
            merged = self._annotate_open_rows([*local_open, *hold_rows], latest_price, dust_blocked_symbols)
            snapshot["open_orders_rows"] = merged
            snapshot["open_orders_count"] = len(merged)
            return snapshot

        api_key = env_data.get("BYBIT_API_KEY") or os.environ.get("BYBIT_API_KEY")
        api_secret = (
            env_data.get("BYBIT_API_SECRET_KEY")
            or env_data.get("BYBIT_API_SECRET")
            or os.environ.get("BYBIT_API_SECRET_KEY")
            or os.environ.get("BYBIT_API_SECRET")
        )
        rsa_key_path = env_data.get("BYBIT_RSA_PRIVATE_KEY_PATH") or os.environ.get("BYBIT_RSA_PRIVATE_KEY_PATH")
        host = str((raw_cfg.get("bybit") or {}).get("host") or "api-demo.bybit.com").strip()

        if not api_key:
            snapshot["api_status"] = "нет BYBIT_API_KEY"
            local_open = self._read_local_open_orders(
                db_path,
                market_label=market_label,
                strategy_default=strategy_label,
            )
            merged = self._annotate_open_rows([*local_open, *hold_rows], latest_price, dust_blocked_symbols)
            snapshot["open_orders_rows"] = merged
            snapshot["open_orders_count"] = len(merged)
            return snapshot
        if not api_secret and not rsa_key_path:
            snapshot["api_status"] = "нет секрета API (HMAC/RSA)"
            local_open = self._read_local_open_orders(
                db_path,
                market_label=market_label,
                strategy_default=strategy_label,
            )
            merged = self._annotate_open_rows([*local_open, *hold_rows], latest_price, dust_blocked_symbols)
            snapshot["open_orders_rows"] = merged
            snapshot["open_orders_count"] = len(merged)
            return snapshot

        category_plan: list[tuple[str, str]] = []
        seen_categories: set[str] = set()
        for strategy_mode in enabled_modes:
            runtime = self._mode_runtime(strategy_mode)
            cat = str(runtime.get("category") or "spot").strip().lower()
            if cat in seen_categories:
                continue
            seen_categories.add(cat)
            category_plan.append((cat, str(runtime.get("strategy_label") or "")))
        if not category_plan:
            category_plan = [(str(primary_runtime.get("category") or "spot"), str(primary_runtime.get("strategy_label") or ""))]

        first_cat, first_strategy = category_plan[0]
        live_data = asyncio.run(
            self._fetch_live_account_snapshot(
                host=host,
                category=first_cat,
                api_key=api_key,
                api_secret=api_secret,
                rsa_key_path=rsa_key_path,
                default_strategy=first_strategy,
            )
        )
        for cat, strategy_fallback in category_plan[1:]:
            extra = asyncio.run(
                self._fetch_live_account_snapshot(
                    host=host,
                    category=cat,
                    api_key=api_key,
                    api_secret=api_secret,
                    rsa_key_path=rsa_key_path,
                    default_strategy=strategy_fallback,
                )
            )
            live_data["open_orders_rows"] = list(live_data.get("open_orders_rows") or []) + list(extra.get("open_orders_rows") or [])
            if extra.get("api_status"):
                live_data["api_status"] = f"{live_data.get('api_status', '')} | {extra.get('api_status', '')}".strip(" |")
        live_rows = list(live_data.get("open_orders_rows") or [])
        live_data["open_orders_rows"] = self._annotate_open_rows(
            [*live_rows, *hold_rows],
            latest_price,
            dust_blocked_symbols,
        )
        live_data["open_orders_count"] = len(live_data["open_orders_rows"])
        snapshot.update(live_data)
        return snapshot

    async def _fetch_live_account_snapshot(
        self,
        host: str,
        category: str,
        api_key: str,
        api_secret: str | None,
        rsa_key_path: str | None,
        default_strategy: str,
    ) -> dict[str, Any]:
        from src.botik.execution.bybit_rest import BybitRestClient

        market = str(category or "spot").strip().lower()
        if market not in {"spot", "linear"}:
            market = "spot"
        client = BybitRestClient(
            base_url=f"https://{host}",
            api_key=api_key,
            api_secret=api_secret,
            rsa_private_key_path=rsa_key_path,
            category=market,
        )

        wallet_resp, open_resp = await asyncio.gather(
            client.get_wallet_balance(account_type="UNIFIED"),
            client.get_open_orders(),
        )

        out: dict[str, Any] = {
            "api_status": f"host={host}; category={market}",
            "open_orders_rows": [],
            "open_orders_count": 0,
        }

        if wallet_resp.get("retCode") != 0:
            out["api_status"] = f"wallet retCode={wallet_resp.get('retCode')}"
        else:
            wallet_item = ((wallet_resp.get("result") or {}).get("list") or [{}])[0]
            coins = wallet_item.get("coin") or []
            usdt = next((c for c in coins if str(c.get("coin", "")).upper() == "USDT"), None)
            total = wallet_item.get("totalEquity") or wallet_item.get("totalWalletBalance")
            available = wallet_item.get("totalAvailableBalance")
            wallet = usdt.get("walletBalance") if usdt else None
            out["balance_total"] = self._fmt_num(total, precision=4)
            out["balance_available"] = self._fmt_num(available, precision=4)
            out["balance_wallet"] = self._fmt_num(wallet if wallet is not None else total, precision=4)

        if open_resp.get("retCode") != 0:
            status = f"open_orders retCode={open_resp.get('retCode')}"
            if out.get("api_status"):
                out["api_status"] = f"{out['api_status']}; {status}"
            else:
                out["api_status"] = status
            return out

        open_list = (open_resp.get("result") or {}).get("list") or []
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
        for idx, item in enumerate(open_list[:80], start=1):
            price = str(item.get("price") or "")
            qty = str(item.get("qty") or "")
            order_link_id = str(item.get("orderLinkId") or "")
            strategy = self._infer_strategy_label(order_link_id, fallback=default_strategy)
            rows.append(
                (
                    str(idx),
                    str(item.get("symbol") or ""),
                    str(item.get("category") or market).upper(),
                    strategy,
                    str(item.get("side") or ""),
                    price,
                    "",
                    qty,
                    self._fmt_usd_notional(price, qty),
                    "",
                    "",
                    "",
                    "",
                    "",
                    str(item.get("orderStatus") or ""),
                )
            )
        out["open_orders_rows"] = rows
        out["open_orders_count"] = len(open_list)
        return out

    def _read_local_order_history(
        self,
        db_path: Path,
        raw_cfg: dict[str, Any],
        limit: int = 80,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            has_entry_exit = False
            if self._table_exists(conn, "orders"):
                cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
                has_entry_exit = "entry_price" in cols and "exit_price" in cols
            if self._table_exists(conn, "order_events"):
                rows = conn.execute(
                    """
                    WITH latest AS (
                        SELECT oe.*
                        FROM order_events oe
                        JOIN (
                            SELECT order_link_id, MAX(id) AS max_id
                            FROM order_events
                            WHERE COALESCE(order_link_id, '') <> ''
                            GROUP BY order_link_id
                        ) sel ON sel.max_id = oe.id
                    )
                    SELECT
                        COALESCE(latest.event_time_utc, ''),
                        COALESCE(latest.symbol, ''),
                        COALESCE(latest.side, ''),
                        COALESCE(latest.order_status, ''),
                        COALESCE(latest.avg_price, latest.price, 0.0),
                        CASE
                            WHEN COALESCE(latest.cum_exec_qty, 0.0) > 0 THEN latest.cum_exec_qty
                            ELSE latest.qty
                        END,
                        COALESCE(sig.entry_price, 0.0),
                        COALESCE(outc.exit_vwap, 0.0)
                    FROM latest
                    LEFT JOIN order_signal_map osm ON osm.order_link_id = latest.order_link_id
                    LEFT JOIN signals sig ON sig.signal_id = osm.signal_id
                    LEFT JOIN outcomes outc ON outc.signal_id = osm.signal_id
                    ORDER BY latest.id DESC
                    LIMIT ?
                    """,
                    (max(limit, 1),),
                ).fetchall()
            else:
                if has_entry_exit:
                    rows = conn.execute(
                        """
                        SELECT COALESCE(updated_at_utc, created_at_utc) AS ts, symbol, side, status, price, qty, entry_price, exit_price
                        FROM orders
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (max(limit, 1),),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT COALESCE(updated_at_utc, created_at_utc) AS ts, symbol, side, status, price, qty, 0.0 AS entry_price, 0.0 AS exit_price
                        FROM orders
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (max(limit, 1),),
                    ).fetchall()
            out_rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
            for idx, r in enumerate(rows, start=1):
                date_str, time_str = self._split_local_datetime(str(r[0] or ""))
                side = str(r[2] or "")
                status = str(r[3] or "")
                price = float(r[4] or 0.0)
                qty = float(r[5] or 0.0)
                entry_price = float(r[6] or 0.0) if len(r) > 6 else 0.0
                exit_price = float(r[7] or 0.0) if len(r) > 7 else 0.0
                if entry_price <= 0 and side.lower() == "buy" and price > 0:
                    entry_price = price
                if exit_price <= 0 and side.lower() == "buy" and entry_price > 0:
                    exit_price = self._expected_exit_from_entry(entry_price, raw_cfg)
                out_rows.append(
                    (
                        str(idx),
                        date_str,
                        time_str,
                        str(r[1] or ""),
                        side,
                        status,
                        self._fmt_price_or_blank(price, precision=8),
                        self._fmt_price_or_blank(qty, precision=8),
                        self._fmt_price_or_blank(entry_price, precision=8),
                        self._fmt_price_or_blank(exit_price, precision=8),
                    )
                )
            return out_rows
        except sqlite3.Error as exc:
            self._enqueue_log(f"[ui] db read error: {exc}")
            return []
        finally:
            conn.close()

    def _read_order_history_count(self, db_path: Path) -> int:
        if not db_path.exists():
            return 0
        conn = sqlite3.connect(str(db_path))
        try:
            if self._table_exists(conn, "order_events"):
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT order_link_id
                        FROM order_events
                        WHERE COALESCE(order_link_id, '') <> ''
                        GROUP BY order_link_id
                    ) x
                    """
                ).fetchone()
                return int(row[0] or 0) if row else 0
            if self._table_exists(conn, "orders"):
                row = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
                return int(row[0] or 0) if row else 0
            return 0
        except sqlite3.Error:
            return 0
        finally:
            conn.close()

    def _read_local_open_orders(
        self,
        db_path: Path,
        limit: int = 80,
        market_label: str = "SPOT",
        strategy_default: str = "",
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            rows: list[tuple[Any, ...]]
            if self._table_exists(conn, "order_events"):
                rows = conn.execute(
                    """
                    WITH latest AS (
                        SELECT oe.*
                        FROM order_events oe
                        JOIN (
                            SELECT order_link_id, MAX(id) AS max_id
                            FROM order_events
                            WHERE COALESCE(order_link_id, '') <> ''
                            GROUP BY order_link_id
                        ) sel ON sel.max_id = oe.id
                    )
                    SELECT
                        COALESCE(latest.order_link_id, ''),
                        COALESCE(latest.symbol, ''),
                        COALESCE(latest.side, ''),
                        COALESCE(latest.avg_price, latest.price, 0.0),
                        CASE
                            WHEN COALESCE(latest.cum_exec_qty, 0.0) > 0 THEN latest.cum_exec_qty
                            ELSE latest.qty
                        END,
                        COALESCE(latest.order_status, '')
                    FROM latest
                    WHERE upper(COALESCE(latest.order_status, '')) IN ('NEW', 'PARTIALLYFILLED')
                    ORDER BY latest.id DESC
                    LIMIT ?
                    """,
                    (max(limit, 1),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT COALESCE(order_link_id, ''), symbol, side, price, qty, status
                    FROM orders
                    WHERE status IN ('New', 'PartiallyFilled')
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (max(limit, 1),),
                ).fetchall()
            out_rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
            for idx, r in enumerate(rows, start=1):
                strategy_label = self._infer_strategy_label(r[0], fallback=strategy_default)
                price = self._fmt_price_or_blank(r[3], precision=8)
                qty = self._fmt_price_or_blank(r[4], precision=8)
                out_rows.append(
                    (
                        str(idx),
                        str(r[1] or ""),
                        str(market_label or "SPOT").upper(),
                        strategy_label,
                        str(r[2] or ""),
                        price,
                        "",
                        qty,
                        self._fmt_usd_notional(r[3], r[4]),
                        "",
                        "",
                        "",
                        "",
                        "",
                        str(r[5] or ""),
                    )
                )
            return out_rows
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_local_hold_rows(
        self,
        db_path: Path,
        raw_cfg: dict[str, Any],
        latest_price: dict[str, float] | None = None,
        dust_blocked_symbols: set[str] | None = None,
        limit: int = 80,
        market_label: str = "SPOT",
        strategy_label: str = "HOLD",
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "executions_raw"):
                return []
            exec_rows = conn.execute(
                """
                SELECT symbol, lower(COALESCE(side, '')), COALESCE(exec_price, 0.0), COALESCE(exec_qty, 0.0), COALESCE(exec_time_ms, 0)
                FROM executions_raw
                ORDER BY exec_time_ms ASC
                """
            ).fetchall()
            if not exec_rows:
                return []

            pos_qty: dict[str, float] = {}
            avg_entry: dict[str, float] = {}
            last_exec_price: dict[str, float] = {}
            for sym_raw, side_raw, price_raw, qty_raw, _ts in exec_rows:
                symbol = str(sym_raw or "").upper().strip()
                if not symbol:
                    continue
                side = str(side_raw or "").lower().strip()
                price = float(price_raw or 0.0)
                qty = float(qty_raw or 0.0)
                if side not in {"buy", "sell"} or qty <= 0 or price <= 0:
                    continue
                cur_qty = float(pos_qty.get(symbol, 0.0))
                cur_avg = float(avg_entry.get(symbol, 0.0))
                new_qty, new_avg = apply_fill(
                    current_qty=cur_qty,
                    current_avg_entry=cur_avg,
                    side=side,
                    fill_qty=qty,
                    fill_price=price,
                )
                pos_qty[symbol] = float(new_qty)
                avg_entry[symbol] = float(new_avg)
                last_exec_price[symbol] = price

            latest_price_map = {str(k).upper().strip(): float(v or 0.0) for k, v in (latest_price or {}).items()}
            dust_blocked = {str(s).upper().strip() for s in (dust_blocked_symbols or set()) if str(s).strip()}
            market = str(market_label or "SPOT").upper()
            strategy = str(strategy_label or "HOLD").upper()
            strategy_cfg = raw_cfg.get("strategy") or {}
            min_active_usdt = max(float(strategy_cfg.get("min_active_position_usdt") or 1.0), 0.0)

            rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
            for symbol, qty in pos_qty.items():
                if abs(float(qty)) <= 1e-9:
                    continue
                entry = float(avg_entry.get(symbol, 0.0))
                mark = float(latest_price_map.get(symbol, 0.0) or last_exec_price.get(symbol, 0.0) or entry)
                notional_usdt = abs(float(qty)) * float(mark if mark > 0 else entry)
                if min_active_usdt > 0 and notional_usdt < min_active_usdt:
                    continue
                target = self._expected_exit_from_entry(entry, raw_cfg) if qty > 0 else 0.0
                pnl_pct = ((mark - entry) / entry) * 100.0 if entry > 0 and mark > 0 else None
                status = "HOLD"
                if symbol in dust_blocked:
                    status = "HOLD:DUST_BLOCKED"
                elif target > 0 and mark > 0:
                    status = "HOLD:WAIT_TARGET" if mark < target else "HOLD:EXIT_READY"
                rows.append(
                    (
                        "0",
                        symbol,
                        market,
                        strategy,
                        "Sell" if qty > 0 else "Buy",
                        self._fmt_price_or_blank(target, precision=8),
                        self._fmt_price_or_blank(mark, precision=8),
                        self._fmt_price_or_blank(abs(qty), precision=8),
                        self._fmt_usd_notional(mark if mark > 0 else entry, abs(qty)),
                        self._fmt_price_or_blank(entry, precision=8),
                        self._fmt_price_or_blank(target, precision=8),
                        self._fmt_pct_or_blank(pnl_pct, precision=2) if pnl_pct is not None else "",
                        "",
                        "",
                        status,
                    )
                )
            rows.sort(key=lambda r: self._safe_float(r[8]), reverse=True)
            return self._reindex_rows(rows[: max(limit, 1)], width=15)
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_outcomes_summary(self, db_path: Path) -> dict[str, float | int]:
        summary: dict[str, float | int] = {
            "total": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "sum_net_pnl_quote": 0.0,
            "avg_net_pnl_quote": 0.0,
        }
        if not db_path.exists():
            return summary
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "outcomes"):
                return summary
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN COALESCE(net_pnl_quote, 0.0) > 0 THEN 1 ELSE 0 END) AS positive,
                    SUM(CASE WHEN COALESCE(net_pnl_quote, 0.0) < 0 THEN 1 ELSE 0 END) AS negative,
                    SUM(CASE WHEN COALESCE(net_pnl_quote, 0.0) = 0 THEN 1 ELSE 0 END) AS neutral,
                    COALESCE(SUM(net_pnl_quote), 0.0) AS sum_net_pnl_quote,
                    COALESCE(AVG(net_pnl_quote), 0.0) AS avg_net_pnl_quote
                FROM outcomes
                """
            ).fetchone()
            if row:
                summary["total"] = int(row[0] or 0)
                summary["positive"] = int(row[1] or 0)
                summary["negative"] = int(row[2] or 0)
                summary["neutral"] = int(row[3] or 0)
                summary["sum_net_pnl_quote"] = float(row[4] or 0.0)
                summary["avg_net_pnl_quote"] = float(row[5] or 0.0)
            return summary
        except sqlite3.Error:
            return summary
        finally:
            conn.close()

    @staticmethod
    def _compress_series(values: list[float], max_points: int) -> list[float]:
        if max_points <= 0 or len(values) <= max_points:
            return values
        if max_points == 1:
            return [values[-1]]
        last_idx = len(values) - 1
        out: list[float] = []
        for i in range(max_points):
            idx = int(round(i * last_idx / (max_points - 1)))
            out.append(values[idx])
        return out

    def _read_cumulative_pnl_chart(self, db_path: Path, max_points: int = 240) -> list[float]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "outcomes"):
                return []
            rows = conn.execute(
                """
                SELECT COALESCE(net_pnl_quote, 0.0)
                FROM outcomes
                ORDER BY closed_at_utc ASC
                """
            ).fetchall()
            if not rows:
                return []
            cumulative: list[float] = []
            acc = 0.0
            for (pnl_raw,) in rows:
                acc += float(pnl_raw or 0.0)
                cumulative.append(acc)
            return self._compress_series(cumulative, max_points=max(max_points, 10))
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    @staticmethod
    def _split_symbol_base_quote(symbol: str) -> tuple[str, str]:
        s = str(symbol or "").upper().strip()
        for quote in ("USDT", "USDC", "BTC", "ETH", "EUR", "USD"):
            if s.endswith(quote) and len(s) > len(quote):
                return s[: -len(quote)], quote
        return s, ""

    def _fee_to_quote_local(self, symbol: str, fee_value: float, fee_currency: str, price: float) -> float:
        fee = float(fee_value or 0.0)
        if fee <= 0:
            return 0.0
        fee_ccy = str(fee_currency or "").upper().strip()
        base_ccy, quote_ccy = self._split_symbol_base_quote(symbol)
        if fee_ccy and quote_ccy and fee_ccy == quote_ccy:
            return fee
        if fee_ccy and base_ccy and fee_ccy == base_ccy and price > 0:
            return fee * price
        return 0.0

    def _read_balance_flow_events(
        self,
        db_path: Path,
        max_rows: int = 500,
    ) -> tuple[list[tuple[str, str, str, str, str, str, str, str, str, str]], float]:
        if not db_path.exists():
            return [], 0.0
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "executions_raw"):
                return [], 0.0
            rows = conn.execute(
                """
                SELECT
                    COALESCE(exec_time_ms, 0),
                    COALESCE(symbol, ''),
                    lower(COALESCE(side, '')),
                    COALESCE(exec_price, 0.0),
                    COALESCE(exec_qty, 0.0),
                    COALESCE(exec_fee, 0.0),
                    COALESCE(fee_currency, '')
                FROM executions_raw
                WHERE COALESCE(exec_time_ms, 0) > 0
                ORDER BY exec_time_ms ASC
                """
            ).fetchall()
            if not rows:
                return [], 0.0

            cumulative = 0.0
            events: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
            for ts_ms, symbol_raw, side_raw, price_raw, qty_raw, fee_raw, fee_ccy_raw in rows:
                symbol = str(symbol_raw or "").upper().strip()
                side = str(side_raw or "").lower().strip()
                price = float(price_raw or 0.0)
                qty = float(qty_raw or 0.0)
                fee = float(fee_raw or 0.0)
                fee_ccy = str(fee_ccy_raw or "").upper().strip()
                if not symbol or side not in {"buy", "sell"} or price <= 0 or qty <= 0:
                    continue
                fee_quote = self._fee_to_quote_local(symbol, fee, fee_ccy, price)
                gross = price * qty
                delta_quote = (-gross if side == "buy" else gross) - fee_quote
                cumulative += delta_quote

                dt = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).astimezone()
                events.append(
                    (
                        "0",
                        dt.strftime("%Y-%m-%d"),
                        dt.strftime("%H:%M:%S"),
                        symbol,
                        "Buy" if side == "buy" else "Sell",
                        self._fmt_price_or_blank(qty, precision=8),
                        self._fmt_price_or_blank(price, precision=8),
                        self._fmt_num(fee_quote, precision=6),
                        self._fmt_num(delta_quote, precision=6),
                        self._fmt_num(cumulative, precision=6),
                    )
                )
            if not events:
                return [], 0.0
            tail = events[-max(max_rows, 1):]
            return self._reindex_rows(tail, width=10), cumulative
        except sqlite3.Error:
            return [], 0.0
        finally:
            conn.close()

    def _read_model_registry_rows(
        self,
        db_path: Path,
        limit: int = 300,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "model_registry"):
                return []
            has_model_stats = self._table_exists(conn, "model_stats")
            has_outcomes = self._table_exists(conn, "outcomes")
            has_signals = self._table_exists(conn, "signals")
            metrics_by_model: dict[str, dict[str, Any]] = {}
            try:
                metrics_rows = conn.execute(
                    "SELECT COALESCE(model_id, ''), COALESCE(metrics_json, '{}') FROM model_registry"
                ).fetchall()
                for model_id_raw, metrics_json_raw in metrics_rows:
                    model_key = str(model_id_raw or "").strip()
                    if not model_key:
                        continue
                    payload: dict[str, Any] = {}
                    try:
                        loaded = json.loads(str(metrics_json_raw or "{}"))
                        if isinstance(loaded, dict):
                            payload = loaded
                    except Exception:
                        payload = {}
                    metrics_by_model[model_key] = payload
            except sqlite3.Error:
                metrics_by_model = {}

            if not has_outcomes or not has_signals:
                rows = conn.execute(
                    """
                    SELECT
                        COALESCE(model_id, ''),
                        COALESCE(created_at_utc, ''),
                        COALESCE(is_active, 0),
                        0, 0, 0, 0.0, 0.0, 0.0, 0.0
                    FROM model_registry
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (max(int(limit), 1),),
                ).fetchall()
            elif has_model_stats:
                rows = conn.execute(
                    """
                    WITH latest_stats AS (
                        SELECT ms.model_id, ms.net_edge_mean, ms.fill_rate, ms.win_rate
                        FROM model_stats ms
                        JOIN (
                            SELECT model_id, MAX(ts_ms) AS max_ts
                            FROM model_stats
                            GROUP BY model_id
                        ) x ON x.model_id = ms.model_id AND x.max_ts = ms.ts_ms
                    ),
                    outcomes_by_model AS (
                        SELECT
                            COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap') AS model_id,
                            COUNT(*) AS outcomes_total,
                            SUM(CASE WHEN COALESCE(o.net_pnl_quote, 0.0) > 0 THEN 1 ELSE 0 END) AS plus_count,
                            SUM(CASE WHEN COALESCE(o.net_pnl_quote, 0.0) < 0 THEN 1 ELSE 0 END) AS minus_count,
                            COALESCE(SUM(o.net_pnl_quote), 0.0) AS net_pnl_quote
                        FROM outcomes o
                        LEFT JOIN signals s ON s.signal_id = o.signal_id
                        GROUP BY COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap')
                    )
                    SELECT
                        COALESCE(m.model_id, ''),
                        COALESCE(m.created_at_utc, ''),
                        COALESCE(m.is_active, 0),
                        COALESCE(obm.outcomes_total, 0),
                        COALESCE(obm.plus_count, 0),
                        COALESCE(obm.minus_count, 0),
                        COALESCE(obm.net_pnl_quote, 0.0),
                        COALESCE(ls.net_edge_mean, 0.0),
                        COALESCE(ls.fill_rate, 0.0),
                        COALESCE(ls.win_rate, 0.0)
                    FROM model_registry m
                    LEFT JOIN outcomes_by_model obm ON obm.model_id = m.model_id
                    LEFT JOIN latest_stats ls ON ls.model_id = m.model_id
                    ORDER BY m.id DESC
                    LIMIT ?
                    """,
                    (max(int(limit), 1),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    WITH outcomes_by_model AS (
                        SELECT
                            COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap') AS model_id,
                            COUNT(*) AS outcomes_total,
                            SUM(CASE WHEN COALESCE(o.net_pnl_quote, 0.0) > 0 THEN 1 ELSE 0 END) AS plus_count,
                            SUM(CASE WHEN COALESCE(o.net_pnl_quote, 0.0) < 0 THEN 1 ELSE 0 END) AS minus_count,
                            COALESCE(SUM(o.net_pnl_quote), 0.0) AS net_pnl_quote
                        FROM outcomes o
                        LEFT JOIN signals s ON s.signal_id = o.signal_id
                        GROUP BY COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap')
                    )
                    SELECT
                        COALESCE(m.model_id, ''),
                        COALESCE(m.created_at_utc, ''),
                        COALESCE(m.is_active, 0),
                        COALESCE(obm.outcomes_total, 0),
                        COALESCE(obm.plus_count, 0),
                        COALESCE(obm.minus_count, 0),
                        COALESCE(obm.net_pnl_quote, 0.0),
                        0.0,
                        0.0,
                        0.0
                    FROM model_registry m
                    LEFT JOIN outcomes_by_model obm ON obm.model_id = m.model_id
                    ORDER BY m.id DESC
                    LIMIT ?
                    """,
                    (max(int(limit), 1),),
                ).fetchall()
            out: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
            for model_id, created_at, is_active, outcomes_total, plus_count, minus_count, net_pnl, edge, fill_rate, win_rate in rows:
                model_key = str(model_id or "").strip()
                extra = metrics_by_model.get(model_key, {})
                train_open_acc_raw = extra.get("open_accuracy", extra.get("quality_score"))
                train_positive_ratio_raw = extra.get("positive_ratio")
                train_open_acc = None
                train_positive_ratio = None
                try:
                    if train_open_acc_raw is not None:
                        train_open_acc = float(train_open_acc_raw)
                except (TypeError, ValueError):
                    train_open_acc = None
                try:
                    if train_positive_ratio_raw is not None:
                        train_positive_ratio = float(train_positive_ratio_raw)
                except (TypeError, ValueError):
                    train_positive_ratio = None

                outcomes_total_int = int(outcomes_total or 0)
                edge_value = max(min(float(edge or 0.0), 5000.0), -5000.0)
                if outcomes_total_int > 0:
                    try:
                        wr = float(plus_count or 0) / max(outcomes_total_int, 1)
                    except Exception:
                        wr = float(win_rate or 0.0)
                else:
                    wr = (
                        float(train_open_acc)
                        if train_open_acc is not None
                        else float(win_rate or 0.0)
                    )
                fill_ratio = float(fill_rate or 0.0)
                if outcomes_total_int <= 0 and fill_ratio <= 0.0 and train_positive_ratio is not None:
                    fill_ratio = float(train_positive_ratio)
                out.append(
                    (
                        str(model_id or ""),
                        str(created_at or ""),
                        "yes" if int(is_active or 0) == 1 else "no",
                        str(outcomes_total_int),
                        str(int(plus_count or 0)),
                        str(int(minus_count or 0)),
                        f"{wr * 100.0:.1f}%",
                        self._fmt_num(net_pnl, precision=6),
                        self._fmt_num(edge_value, precision=3),
                        f"{fill_ratio * 100.0:.1f}%",
                    )
                )
            return out
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_spot_holdings_rows(
        self,
        db_path: Path,
        limit: int = 400,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "spot_holdings"):
                return []
            rows = conn.execute(
                """
                SELECT
                    COALESCE(symbol, ''),
                    COALESCE(base_asset, ''),
                    COALESCE(free_qty, 0.0),
                    COALESCE(locked_qty, 0.0),
                    avg_entry_price,
                    COALESCE(hold_reason, ''),
                    COALESCE(source_of_truth, ''),
                    COALESCE(recovered_from_exchange, 0),
                    COALESCE(auto_sell_allowed, 0)
                FROM spot_holdings
                ORDER BY updated_at_utc DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            out: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
            for symbol, base, free_qty, locked_qty, entry, reason, source, recovered, auto_sell in rows:
                out.append(
                    (
                        "0",
                        str(symbol or ""),
                        str(base or ""),
                        self._fmt_num(free_qty, precision=8),
                        self._fmt_num(locked_qty, precision=8),
                        self._fmt_price_or_blank(entry, precision=8),
                        str(reason or ""),
                        str(source or ""),
                        "yes" if int(recovered or 0) == 1 else "no",
                        "yes" if int(auto_sell or 0) == 1 else "no",
                    )
                )
            return self._reindex_rows(out, width=10)
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_futures_positions_rows(
        self,
        db_path: Path,
        limit: int = 400,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "futures_positions"):
                return []
            rows = conn.execute(
                """
                SELECT
                    COALESCE(symbol, ''),
                    COALESCE(side, ''),
                    COALESCE(qty, 0.0),
                    entry_price,
                    mark_price,
                    liq_price,
                    unrealized_pnl,
                    take_profit,
                    stop_loss,
                    COALESCE(protection_status, '')
                FROM futures_positions
                WHERE ABS(COALESCE(qty, 0.0)) > 0
                ORDER BY updated_at_utc DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            out: list[tuple[str, str, str, str, str, str, str, str, str, str, str]] = []
            for symbol, side, qty, entry, mark, liq, upnl, tp, sl, protection in rows:
                out.append(
                    (
                        "0",
                        str(symbol or ""),
                        str(side or ""),
                        self._fmt_num(qty, precision=8),
                        self._fmt_price_or_blank(entry, precision=8),
                        self._fmt_price_or_blank(mark, precision=8),
                        self._fmt_price_or_blank(liq, precision=8),
                        self._fmt_num(upnl, precision=6),
                        self._fmt_price_or_blank(tp, precision=8),
                        self._fmt_price_or_blank(sl, precision=8),
                        str(protection or ""),
                    )
                )
            return self._reindex_rows(out, width=10)
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_futures_open_orders_rows(
        self,
        db_path: Path,
        limit: int = 400,
    ) -> list[tuple[str, str, str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "futures_open_orders"):
                return []
            rows = conn.execute(
                """
                SELECT
                    COALESCE(symbol, ''),
                    COALESCE(side, ''),
                    COALESCE(order_id, ''),
                    COALESCE(order_link_id, ''),
                    COALESCE(order_type, ''),
                    price,
                    qty,
                    COALESCE(status, '')
                FROM futures_open_orders
                ORDER BY updated_at_utc DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            out: list[tuple[str, str, str, str, str, str, str, str, str]] = []
            for symbol, side, order_id, link_id, order_type, price, qty, status in rows:
                out.append(
                    (
                        "0",
                        str(symbol or ""),
                        str(side or ""),
                        str(order_id or ""),
                        str(link_id or ""),
                        str(order_type or ""),
                        self._fmt_price_or_blank(price, precision=8),
                        self._fmt_num(qty, precision=8),
                        str(status or ""),
                    )
                )
            return self._reindex_rows(out, width=10)
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _read_reconciliation_issue_rows(
        self,
        db_path: Path,
        limit: int = 400,
    ) -> list[tuple[str, str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            if not self._table_exists(conn, "reconciliation_issues"):
                return []
            rows = conn.execute(
                """
                SELECT
                    COALESCE(created_at_utc, ''),
                    COALESCE(domain, ''),
                    COALESCE(issue_type, ''),
                    COALESCE(symbol, ''),
                    COALESCE(severity, ''),
                    COALESCE(status, '')
                FROM reconciliation_issues
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            out: list[tuple[str, str, str, str, str, str, str]] = []
            for ts, domain, issue_type, symbol, severity, status in rows:
                out.append(
                    (
                        "0",
                        str(ts or ""),
                        str(domain or ""),
                        str(issue_type or ""),
                        str(symbol or ""),
                        str(severity or ""),
                        str(status or ""),
                    )
                )
            return self._reindex_rows(out, width=10)
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _set_tree_rows(self, tree: ttk.Treeview, rows: list[tuple[Any, ...]]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            tags: tuple[str, ...] = ()
            if tree is self.open_orders_tree:
                tag = self._open_order_row_tag(row)
                if tag:
                    tags = (tag,)
            elif tree is self.models_tree:
                row_list = list(row)
                if len(row_list) >= 3 and str(row_list[2]).lower() == "yes":
                    tags = ("model_active",)
            tree.insert("", tk.END, values=row, tags=tags)

    def _active_tab_key(self) -> str:
        if self.notebook is None:
            return "control"
        try:
            selected = self.notebook.select()
            widget = self.notebook.nametowidget(selected)
        except Exception:
            return "control"
        if widget is self.control_tab:
            return "control"
        if widget is self.logs_tab:
            return "logs"
        if widget is self.settings_tab:
            if self.settings_notebook is not None:
                try:
                    inner = self.settings_notebook.nametowidget(self.settings_notebook.select())
                    if inner is self.spike_tab:
                        return "strategies"
                except Exception:
                    pass
            return "settings"
        if widget is self.statistics_tab:
            if self.statistics_notebook is not None:
                try:
                    inner = self.statistics_notebook.nametowidget(self.statistics_notebook.select())
                    if inner is self.models_tab:
                        return "models"
                except Exception:
                    pass
            return "stats"
        return "control"

    @staticmethod
    def _parse_pct_cell(value: Any) -> float | None:
        text = str(value or "").strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_float_cell(value: Any) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _open_order_row_tag(self, row: tuple[Any, ...]) -> str:
        values = list(row)
        if len(values) < 15:
            return "pnl_neutral"
        status = str(values[14] or "").upper()
        pnl_pct = self._parse_pct_cell(values[11])
        progress = self._parse_pct_cell(values[13])

        if status.startswith("HOLD:EXIT_READY"):
            return "exit_ready"
        if status.startswith("HOLD:WAIT_TARGET"):
            if pnl_pct is not None and pnl_pct < 0:
                return "exit_risk"
            return "exit_wait"
        if progress is not None and progress >= 100.0:
            return "exit_ready"
        if pnl_pct is None:
            return "pnl_neutral"
        if pnl_pct > 0:
            return "pnl_pos"
        if pnl_pct < 0:
            return "pnl_neg"
        return "pnl_neutral"

    def _apply_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        active_tab = self._active_tab_key()
        self.balance_total_var.set(str(snapshot.get("balance_total", "n/a")))
        self.balance_available_var.set(str(snapshot.get("balance_available", "n/a")))
        self.balance_wallet_var.set(str(snapshot.get("balance_wallet", "n/a")))
        self.open_orders_var.set(str(snapshot.get("open_orders_count", 0)))
        self.api_status_var.set(str(snapshot.get("api_status", "n/a")))
        self.snapshot_time_var.set(str(snapshot.get("updated_at", "-")))
        self.runtime_capabilities_var.set(str(snapshot.get("runtime_capabilities_status", "capabilities: n/a")))
        self.reconciliation_status_var.set(str(snapshot.get("reconciliation_status_line", "reconciliation: n/a")))
        self.panel_freshness_var.set(str(snapshot.get("panel_freshness_line", "freshness: n/a")))
        self.futures_protection_status_var.set(
            str(snapshot.get("futures_protection_status_line", "protection: n/a"))
        )
        self._set_tree_rows(self.open_orders_tree, list(snapshot.get("open_orders_rows") or []))
        self._set_tree_rows(self.order_history_tree, list(snapshot.get("history_rows") or []))
        if self.stats_history_tree is not None and active_tab == "stats":
            self._set_tree_rows(self.stats_history_tree, list(snapshot.get("history_rows_full") or []))
        if self.stats_balance_tree is not None and active_tab == "stats":
            self._set_tree_rows(self.stats_balance_tree, list(snapshot.get("stats_balance_rows") or []))
        if self.stats_spot_holdings_tree is not None and active_tab == "stats":
            self._set_tree_rows(self.stats_spot_holdings_tree, list(snapshot.get("stats_spot_holdings_rows") or []))
        if self.stats_futures_positions_tree is not None and active_tab == "stats":
            self._set_tree_rows(self.stats_futures_positions_tree, list(snapshot.get("stats_futures_positions_rows") or []))
        if self.stats_futures_orders_tree is not None and active_tab == "stats":
            self._set_tree_rows(self.stats_futures_orders_tree, list(snapshot.get("stats_futures_orders_rows") or []))
        if self.stats_reconciliation_issues_tree is not None and active_tab == "stats":
            self._set_tree_rows(
                self.stats_reconciliation_issues_tree,
                list(snapshot.get("stats_reconciliation_issue_rows") or []),
            )
        if self.models_tree is not None and active_tab == "models":
            self._set_tree_rows(self.models_tree, list(snapshot.get("model_rows") or []))
        self.stats_orders_total_var.set(str(int(snapshot.get("stats_orders_total", 0))))
        self.stats_outcomes_total_var.set(str(int(snapshot.get("stats_outcomes_total", 0))))
        self.stats_positive_var.set(str(int(snapshot.get("stats_positive_count", 0))))
        self.stats_negative_var.set(str(int(snapshot.get("stats_negative_count", 0))))
        self.stats_neutral_var.set(str(int(snapshot.get("stats_neutral_count", 0))))
        self.stats_net_pnl_var.set(f"{float(snapshot.get('stats_net_pnl_quote', 0.0)):.6f}")
        self.stats_avg_pnl_var.set(f"{float(snapshot.get('stats_avg_pnl_quote', 0.0)):.6f}")
        self.stats_balance_events_var.set(str(int(snapshot.get("stats_balance_events", 0))))
        self.stats_balance_delta_var.set(f"{float(snapshot.get('stats_balance_delta_total', 0.0)):.6f}")
        self.models_summary_var.set(
            f"models={int(snapshot.get('models_total', 0))} | orders={int(snapshot.get('stats_orders_total', 0))} | outcomes={int(snapshot.get('stats_outcomes_total', 0))}"
        )
        self._stats_cum_pnl_points.clear()
        self._stats_cum_pnl_points.extend(float(v) for v in list(snapshot.get("stats_cum_pnl_chart") or []))
        self._draw_stats_pnl_chart()
        self.ml_training_paused = bool(snapshot.get("ml_training_paused", False))
        self.ml_runtime_mode = str(snapshot.get("ml_runtime_mode") or "bootstrap")
        self.ml_model_id_var.set(str(snapshot.get("ml_model_id") or "bootstrap"))
        self.ml_net_edge_var.set(f"{float(snapshot.get('ml_net_edge_mean', 0.0)):.4f} bps")
        self.ml_win_rate_var.set(f"{float(snapshot.get('ml_win_rate', 0.0)) * 100.0:.1f}%")
        self.ml_fill_rate_var.set(f"{float(snapshot.get('ml_fill_rate', 0.0)) * 100.0:.1f}%")
        fill_filled = int(snapshot.get("ml_fill_filled", 0))
        fill_total = int(snapshot.get("ml_fill_total", 0))
        self.ml_fill_details_var.set(f"{fill_filled}/{fill_total} signals")
        progress = float(snapshot.get("ml_training_progress", 0.0))
        closed = int(snapshot.get("ml_closed_count", 0))
        paired = int(snapshot.get("ml_paired_closed_signals", 0))
        exec_total = int(snapshot.get("ml_executions_total", 0))
        filled_orders = int(snapshot.get("ml_filled_orders", 0))
        batch = int(snapshot.get("ml_batch_size", 50))
        self.ml_progress_text_var.set(
            f"{progress:.0f}% out={closed} pair={paired}\nfill={filled_orders} exec={exec_total} b={batch}"
        )
        self.ml_metrics_compact_var.set(
            f"edge={self.ml_net_edge_var.get()} | win={self.ml_win_rate_var.get()} | fill={self.ml_fill_rate_var.get()}\n"
            f"signals={self.ml_fill_details_var.get()} | outcomes={closed} | paired={paired} | filled_orders={filled_orders}"
        )
        self._ml_chart_points.clear()
        self._ml_chart_points.extend(float(v) for v in list(snapshot.get("ml_chart") or []))
        self._draw_ml_chart()

    def _draw_stats_pnl_chart(self) -> None:
        canvas = self.stats_pnl_canvas
        if canvas is None:
            return
        canvas.delete("all")
        points = list(self._stats_cum_pnl_points)

        width = max(int(canvas.winfo_width()), 40)
        height = max(int(canvas.winfo_height()), 28)
        if len(points) < 2:
            mid = height / 2.0
            canvas.create_line(4, mid, width - 4, mid, fill=self._ui_colors.get("line", "#2A4063"))
            return

        min_v = min(points)
        max_v = max(points)
        if abs(max_v - min_v) < 1e-9:
            min_v -= 1.0
            max_v += 1.0

        coords: list[float] = []
        total = len(points) - 1
        for idx, value in enumerate(points):
            x = (idx / total) * (width - 8) + 4
            norm = (value - min_v) / (max_v - min_v)
            y = (height - 6) - norm * (height - 12)
            coords.extend([x, y])

        zero_norm = (0.0 - min_v) / (max_v - min_v)
        zero_y = (height - 6) - zero_norm * (height - 12)
        zero_y = min(max(zero_y, 2.0), height - 2.0)
        canvas.create_line(4, zero_y, width - 4, zero_y, fill=self._ui_colors.get("line", "#2A4063"))
        color = self._ui_colors.get("success", "#27AE60") if points[-1] >= 0 else self._ui_colors.get("danger", "#D64545")
        canvas.create_line(*coords, fill=color, width=2, smooth=True)

    def _draw_ml_chart(self) -> None:
        canvas = self.ml_chart_canvas
        canvas.delete("all")
        points = list(self._ml_chart_points)
        if len(points) < 2:
            return

        width = max(int(canvas.winfo_width()), 40)
        height = max(int(canvas.winfo_height()), 20)
        min_v = min(points)
        max_v = max(points)
        if abs(max_v - min_v) < 1e-9:
            max_v = min_v + 1.0

        coords: list[float] = []
        total = len(points) - 1
        for idx, value in enumerate(points):
            x = (idx / total) * (width - 8) + 4
            norm = (value - min_v) / (max_v - min_v)
            y = (height - 6) - norm * (height - 12)
            coords.extend([x, y])

        canvas.create_line(4, height - 5, width - 4, height - 5, fill=self._ui_colors.get("line", "#2A4063"))
        canvas.create_line(*coords, fill=self._ui_colors.get("accent", "#3B82F6"), width=2, smooth=True)

    def copy_ml_chart(self) -> None:
        if not self._ml_chart_points:
            return
        payload = (
            f"model={self.ml_model_id_var.get()}\n"
            f"net_edge_mean={self.ml_net_edge_var.get()}\n"
            f"win_rate={self.ml_win_rate_var.get()}\n"
            f"fill_rate={self.ml_fill_rate_var.get()} ({self.ml_fill_details_var.get()})\n"
            f"series={','.join(f'{v:.4f}' for v in self._ml_chart_points)}"
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self._enqueue_log("[ui] copied ML chart data")

    @staticmethod
    def _detect_strategy_preset(raw: dict[str, Any]) -> str:
        bybit_cfg = raw.get("bybit") or {}
        strategy = raw.get("strategy") or {}
        preset = str(strategy.get("ui_strategy_preset") or "").strip().lower()
        if preset in {"spot_spread", "spot_spike", "futures_spike_reversal"}:
            return preset
        market = str(bybit_cfg.get("market_category") or "spot").strip().lower()
        runtime = str(strategy.get("runtime_strategy") or "spread_maker").strip().lower()
        if market == "linear" and runtime == "spike_reversal":
            return "futures_spike_reversal"
        return "spot_spread"

    def _selected_strategy_mode(self) -> str:
        label = self.strategy_mode_var.get()
        return STRATEGY_PRESET_LABELS.get(label, "spot_spread")

    @staticmethod
    def _normalized_profile_dict(
        profile_id: str,
        *,
        entry_tick_offset: int,
        order_qty_base: float,
        target_profit: float,
        safety_buffer: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        hold_timeout_sec: int,
        maker_only: bool,
    ) -> dict[str, Any]:
        return {
            "profile_id": str(profile_id),
            "entry_tick_offset": int(max(entry_tick_offset, 0)),
            "order_qty_base": float(max(order_qty_base, 1e-10)),
            "target_profit": float(max(target_profit, 0.0)),
            "safety_buffer": float(max(safety_buffer, 0.0)),
            "min_top_book_qty": 0.0,
            "stop_loss_pct": float(max(stop_loss_pct, 0.0)),
            "take_profit_pct": float(max(take_profit_pct, 0.0)),
            "hold_timeout_sec": int(max(hold_timeout_sec, 1)),
            "maker_only": bool(maker_only),
        }

    def _ensure_adaptive_action_profiles(self, strategy: dict[str, Any], mode: str) -> None:
        """
        Ensure the strategy has a profile set for ML/Bandit parameter selection.
        Existing user-defined profile sets (2+) are preserved.
        """
        profiles_raw = strategy.get("action_profiles")
        existing: list[dict[str, Any]] = [dict(p) for p in profiles_raw if isinstance(p, dict)] if isinstance(profiles_raw, list) else []
        if len(existing) >= 2:
            strategy["action_profiles"] = existing
            strategy["bandit_enabled"] = bool(strategy.get("bandit_enabled", True))
            return

        base_qty = max(float(strategy.get("order_qty_base") or 0.001), 1e-10)
        base_target = max(float(strategy.get("target_profit") or 0.0001), 0.0)
        base_safety = max(float(strategy.get("safety_buffer") or 0.00005), 0.0)
        base_sl = max(float(strategy.get("stop_loss_pct") or 0.003), 0.0)
        base_tp = max(float(strategy.get("take_profit_pct") or 0.005), 0.0)
        base_hold = max(int(strategy.get("position_hold_timeout_sec") or 180), 1)
        entry_tick_offset = max(int(strategy.get("entry_tick_offset") or 1), 0)

        maker_default = not (str(mode).strip().lower() == "futures_spike_reversal")
        if mode == "futures_spike_reversal":
            maker_default = not bool(strategy.get("spike_reversal_taker", True))

        adaptive_profiles = [
            self._normalized_profile_dict(
                "adaptive_conservative",
                entry_tick_offset=entry_tick_offset,
                order_qty_base=base_qty * 0.75,
                target_profit=max(base_target * 1.4, base_target + 0.00003),
                safety_buffer=max(base_safety * 1.4, base_safety + 0.00002),
                stop_loss_pct=max(base_sl * 0.8, 0.002),
                take_profit_pct=max(base_tp * 1.15, base_tp + 0.001),
                hold_timeout_sec=max(int(base_hold * 0.7), 25),
                maker_only=maker_default,
            ),
            self._normalized_profile_dict(
                "adaptive_balanced",
                entry_tick_offset=entry_tick_offset,
                order_qty_base=base_qty,
                target_profit=base_target,
                safety_buffer=base_safety,
                stop_loss_pct=base_sl,
                take_profit_pct=base_tp,
                hold_timeout_sec=base_hold,
                maker_only=maker_default,
            ),
            self._normalized_profile_dict(
                "adaptive_aggressive",
                entry_tick_offset=entry_tick_offset,
                order_qty_base=base_qty * 1.2,
                target_profit=max(base_target * 0.75, base_target * 0.5),
                safety_buffer=max(base_safety * 0.75, base_safety * 0.5),
                stop_loss_pct=max(base_sl * 1.35, base_sl + 0.001),
                take_profit_pct=max(base_tp * 1.6, base_tp + 0.002),
                hold_timeout_sec=max(int(base_hold * 1.25), base_hold + 15),
                maker_only=maker_default,
            ),
        ]

        strategy["action_profiles"] = adaptive_profiles
        strategy["bandit_enabled"] = True

    def load_settings(self) -> None:
        self._suspend_autosave = True
        try:
            env_data = _read_env_map(ENV_PATH)
            for key, var in self.env_vars.items():
                var.set(env_data.get(key, ""))

            raw = self._load_yaml()
            self.cfg_execution_mode.set(str(((raw.get("execution") or {}).get("mode") or "paper")).lower())
            self.cfg_start_paused.set(bool(raw.get("start_paused", True)))
            self.cfg_bybit_host.set(str((raw.get("bybit") or {}).get("host") or "api-demo.bybit.com"))
            self.cfg_ws_host.set(str((raw.get("bybit") or {}).get("ws_public_host") or "stream.bybit.com"))
            self.cfg_market_category.set(str((raw.get("bybit") or {}).get("market_category") or "spot").lower())
            symbols = raw.get("symbols") or ["BTCUSDT", "ETHUSDT"]
            self.cfg_symbols.set(",".join(str(s) for s in symbols))

            strategy = raw.get("strategy") or {}
            self.cfg_runtime_strategy.set(str(strategy.get("runtime_strategy") or "spread_maker").lower())
            self.cfg_target_profit.set(str(strategy.get("target_profit", 0.0002)))
            self.cfg_safety_buffer.set(str(strategy.get("safety_buffer", 0.0001)))
            self.cfg_stop_loss.set(str(strategy.get("stop_loss_pct", 0.003)))
            self.cfg_take_profit.set(str(strategy.get("take_profit_pct", 0.005)))
            self.cfg_hold_timeout.set(str(strategy.get("position_hold_timeout_sec", 180)))
            self.cfg_min_active_usdt.set(str(strategy.get("min_active_position_usdt", 1.0)))
            self.cfg_maker_only.set(True)
            self.spike_threshold_bps_var.set(str(strategy.get("spike_threshold_bps", 12)))
            self.spike_min_trades_var.set(str(strategy.get("spike_min_trades_per_min", 8)))
            self.spike_slices_var.set(str(strategy.get("spike_burst_slices", 4)))
            self.spike_qty_scale_var.set(str(strategy.get("spike_burst_qty_scale", 0.25)))
            self.spike_scanner_top_k_var.set(str(strategy.get("scanner_top_k", 80)))
            self.spike_universe_size_var.set(str(strategy.get("auto_universe_size", 200)))
            ml_raw = raw.get("ml") or {}
            self.spike_ml_interval_var.set(str(ml_raw.get("run_interval_sec", 120)))
            preset_mode = self._detect_strategy_preset(raw)
            self.strategy_mode_var.set(STRATEGY_PRESET_MODES.get(preset_mode, STRATEGY_PRESET_MODES["spot_spread"]))
            enabled_modes = self._extract_enabled_strategy_modes_from_raw(raw)
            self._set_enabled_strategy_modes_ui(enabled_modes)
        finally:
            self._suspend_autosave = False
        self._enqueue_log("[settings] loaded from files")

    def save_env(self, show_popup: bool = True) -> bool:
        updates = {k: v.get().strip() for k, v in self.env_vars.items()}
        try:
            _upsert_env(ENV_PATH, updates)
        except Exception as exc:
            if show_popup:
                messagebox.showerror("Save failed", f".env save error:\n{exc}")
            return False
        self._start_telegram_control_if_configured()
        self._enqueue_log(f"[settings] .env auto-saved: {ENV_PATH}")
        if show_popup:
            messagebox.showinfo("Saved", f".env updated:\n{ENV_PATH}")
        return True

    def save_config(self, show_popup: bool = True) -> bool:
        cfg_path = Path(self.config_var.get())
        raw = self._load_yaml()
        raw.setdefault("execution", {})
        raw.setdefault("bybit", {})
        raw.setdefault("strategy", {})

        try:
            raw["execution"]["mode"] = self.cfg_execution_mode.get().strip().lower()
            raw["start_paused"] = bool(self.cfg_start_paused.get())

            raw["bybit"]["host"] = self.cfg_bybit_host.get().strip()
            raw["bybit"]["ws_public_host"] = self.cfg_ws_host.get().strip()
            market_category = self.cfg_market_category.get().strip().lower()
            raw["bybit"]["market_category"] = market_category if market_category in {"spot", "linear"} else "spot"
            raw["symbols"] = [s.strip().upper() for s in self.cfg_symbols.get().split(",") if s.strip()]

            runtime_strategy = self.cfg_runtime_strategy.get().strip().lower()
            raw["strategy"]["runtime_strategy"] = (
                runtime_strategy if runtime_strategy in {"spread_maker", "spike_reversal"} else "spread_maker"
            )
            raw["strategy"]["target_profit"] = float(self.cfg_target_profit.get().strip())
            raw["strategy"]["safety_buffer"] = float(self.cfg_safety_buffer.get().strip())
            raw["strategy"]["stop_loss_pct"] = float(self.cfg_stop_loss.get().strip())
            raw["strategy"]["take_profit_pct"] = float(self.cfg_take_profit.get().strip())
            raw["strategy"]["position_hold_timeout_sec"] = int(self.cfg_hold_timeout.get().strip())
            raw["strategy"]["min_active_position_usdt"] = max(float(self.cfg_min_active_usdt.get().strip()), 0.0)
            raw["strategy"]["maker_only"] = True
            enabled_modes = self._enabled_strategy_modes_from_ui()
            raw["strategy"]["ui_enabled_strategy_modes"] = enabled_modes
            self._ensure_adaptive_action_profiles(raw["strategy"], self._detect_strategy_preset(raw))
            cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        except Exception as exc:
            if show_popup:
                messagebox.showerror("Save failed", f"config save error:\n{exc}")
            return False

        self._enqueue_log(f"[settings] config auto-saved: {cfg_path}")
        if show_popup:
            messagebox.showinfo("Saved", f"config.yaml updated:\n{cfg_path}")
        return True

    def save_all(self) -> None:
        try:
            self.save_env(show_popup=False)
            self.save_config(show_popup=False)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._enqueue_log("[settings] save all completed")

    def _apply_spike_preset_impl(self, show_popup: bool) -> tuple[bool, str]:
        cfg_path = Path(self.config_var.get())
        raw = self._load_yaml()
        raw.setdefault("strategy", {})
        raw.setdefault("ml", {})
        raw.setdefault("execution", {})
        strategy = raw["strategy"]
        ml = raw["ml"]

        try:
            spike_threshold = max(float(self.spike_threshold_bps_var.get().strip()), 0.0)
            spike_min_trades = max(float(self.spike_min_trades_var.get().strip()), 0.0)
            spike_slices = min(max(int(self.spike_slices_var.get().strip()), 1), 8)
            spike_qty_scale = max(float(self.spike_qty_scale_var.get().strip()), 0.01)
            scanner_top_k = max(int(self.spike_scanner_top_k_var.get().strip()), 1)
            universe_size = max(int(self.spike_universe_size_var.get().strip()), scanner_top_k)
            ml_interval = max(int(self.spike_ml_interval_var.get().strip()), 30)
        except ValueError as exc:
            msg = f"Spike preset parse error: {exc}"
            if show_popup:
                messagebox.showerror("Spike preset error", msg)
            return False, msg

        strategy["spike_burst_enabled"] = True
        strategy["spike_threshold_bps"] = spike_threshold
        strategy["spike_min_trades_per_min"] = spike_min_trades
        strategy["spike_burst_slices"] = spike_slices
        strategy["spike_burst_qty_scale"] = spike_qty_scale
        strategy["spike_burst_tick_step"] = 1
        strategy["strict_pair_filter"] = True
        strategy["scanner_enabled"] = True
        strategy["scanner_top_k"] = scanner_top_k
        strategy["auto_universe_enabled"] = True
        strategy["auto_universe_size"] = universe_size
        strategy["auto_universe_min_symbols"] = max(int(strategy.get("auto_universe_min_symbols") or 60), scanner_top_k)
        strategy.setdefault("auto_universe_refresh_sec", 180)
        strategy.setdefault("spike_profile_id", "spike")

        ml["mode"] = "online"
        ml["run_interval_sec"] = ml_interval
        ml["train_batch_size"] = 20
        ml["min_closed_trades_to_train"] = 20

        profile_id = str(strategy.get("spike_profile_id") or "spike").strip() or "spike"
        base_qty = max(float(strategy.get("order_qty_base") or 0.001), 1e-8)
        spike_qty = max(base_qty * spike_qty_scale, 1e-8)
        profiles_raw = strategy.get("action_profiles")
        profiles: list[dict[str, Any]] = []
        if isinstance(profiles_raw, list):
            for item in profiles_raw:
                if isinstance(item, dict):
                    profiles.append(dict(item))

        updated = False
        for profile in profiles:
            if str(profile.get("profile_id") or "").strip() != profile_id:
                continue
            profile["entry_tick_offset"] = int(profile.get("entry_tick_offset") or strategy.get("entry_tick_offset") or 1)
            profile["order_qty_base"] = spike_qty
            profile["target_profit"] = float(profile.get("target_profit") or strategy.get("target_profit") or 0.0001)
            profile["safety_buffer"] = float(profile.get("safety_buffer") or strategy.get("safety_buffer") or 0.00005)
            profile["min_top_book_qty"] = float(profile.get("min_top_book_qty") or strategy.get("min_top_book_qty") or 0.0)
            profile["stop_loss_pct"] = float(profile.get("stop_loss_pct") or strategy.get("stop_loss_pct") or 0.003)
            profile["take_profit_pct"] = float(profile.get("take_profit_pct") or strategy.get("take_profit_pct") or 0.005)
            profile["hold_timeout_sec"] = int(profile.get("hold_timeout_sec") or strategy.get("position_hold_timeout_sec") or 180)
            profile["maker_only"] = True
            updated = True
            break

        if not updated:
            profiles.append(
                {
                    "profile_id": profile_id,
                    "entry_tick_offset": int(strategy.get("entry_tick_offset") or 1),
                    "order_qty_base": spike_qty,
                    "target_profit": float(strategy.get("target_profit") or 0.0001),
                    "safety_buffer": float(strategy.get("safety_buffer") or 0.00005),
                    "min_top_book_qty": float(strategy.get("min_top_book_qty") or 0.0),
                    "stop_loss_pct": float(strategy.get("stop_loss_pct") or 0.003),
                    "take_profit_pct": float(strategy.get("take_profit_pct") or 0.005),
                    "hold_timeout_sec": int(strategy.get("position_hold_timeout_sec") or 180),
                    "maker_only": True,
                }
            )
        strategy["action_profiles"] = profiles
        self._ensure_adaptive_action_profiles(strategy, "spot_spike")

        try:
            cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        except OSError as exc:
            msg = f"Spike preset save error: {exc}"
            if show_popup:
                messagebox.showerror("Spike preset error", msg)
            return False, msg

        self._enqueue_log(
            "[spike] params applied: ml=online, spike_burst=on, "
            f"threshold={spike_threshold:.2f}, slices={spike_slices}, qty_scale={spike_qty_scale:.3f}"
        )
        self.load_settings()
        msg = "Spike params applied."
        if show_popup:
            messagebox.showinfo("Spike preset", msg)
        return True, msg

    def apply_spike_preset(self) -> None:
        self._flush_autosave()
        ok, msg = self._apply_spike_preset_impl(show_popup=True)
        if not ok:
            self._enqueue_log(f"[spike] {msg}")

    def _apply_strategy_preset_impl(self, mode: str, show_popup: bool) -> tuple[bool, str]:
        cfg_path = Path(self.config_var.get())
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode not in {"spot_spread", "spot_spike", "futures_spike_reversal"}:
            return False, f"unknown strategy mode: {mode}"

        if normalized_mode in {"spot_spike", "futures_spike_reversal"}:
            ok, msg = self._apply_spike_preset_impl(show_popup=False)
            if not ok:
                if show_popup:
                    messagebox.showerror("Strategy preset error", msg)
                return False, msg

        raw = self._load_yaml()
        raw.setdefault("bybit", {})
        raw.setdefault("strategy", {})
        raw.setdefault("ml", {})
        strategy = raw["strategy"]
        bybit = raw["bybit"]
        ml = raw["ml"]

        if normalized_mode == "spot_spread":
            bybit["market_category"] = "spot"
            strategy["runtime_strategy"] = "spread_maker"
            strategy["spike_burst_enabled"] = False
            strategy.setdefault("strict_pair_filter", True)
            msg = "Strategy preset applied: Spot Spread (maker)."
        elif normalized_mode == "spot_spike":
            bybit["market_category"] = "spot"
            strategy["runtime_strategy"] = "spread_maker"
            strategy["spike_burst_enabled"] = True
            strategy.setdefault("strict_pair_filter", True)
            msg = "Strategy preset applied: Spot Spike Burst."
        else:
            bybit["market_category"] = "linear"
            strategy["runtime_strategy"] = "spike_reversal"
            strategy["spike_burst_enabled"] = False
            strategy["strict_pair_filter"] = False
            strategy["spike_reversal_reverse"] = True
            strategy["spike_reversal_taker"] = True
            strategy["spike_reversal_min_strength_bps"] = max(float(strategy.get("spike_threshold_bps") or 12.0), 0.0)
            strategy["spike_reversal_entry_offset_ticks"] = max(int(strategy.get("spike_burst_tick_step") or 1), 0)
            strategy["spike_reversal_qty_scale"] = max(float(strategy.get("spike_burst_qty_scale") or 0.25), 0.01)
            strategy["spike_reversal_max_symbols"] = max(int(strategy.get("scanner_top_k") or 80), 1)
            strategy["spike_reversal_cooldown_sec"] = 2.0
            spike_profile_id = str(strategy.get("spike_profile_id") or "spike").strip() or "spike"
            profiles_raw = strategy.get("action_profiles")
            profiles: list[dict[str, Any]] = [dict(p) for p in profiles_raw if isinstance(p, dict)] if isinstance(profiles_raw, list) else []
            for profile in profiles:
                if str(profile.get("profile_id") or "").strip() == spike_profile_id:
                    profile["maker_only"] = False
            strategy["action_profiles"] = profiles
            ml["mode"] = "online"
            msg = "Strategy preset applied: Futures Spike Reversal (linear)."

        strategy["ui_strategy_preset"] = normalized_mode
        strategy["ui_enabled_strategy_modes"] = [normalized_mode]
        self._ensure_adaptive_action_profiles(strategy, normalized_mode)

        try:
            cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        except OSError as exc:
            save_msg = f"Strategy preset save error: {exc}"
            if show_popup:
                messagebox.showerror("Strategy preset error", save_msg)
            return False, save_msg

        self.load_settings()
        self._enqueue_log(f"[strategy] {msg}")
        if show_popup:
            messagebox.showinfo("Strategy preset", msg)
        return True, msg

    def apply_selected_strategy(self) -> None:
        self._flush_autosave()
        mode = self._selected_strategy_mode()
        ok, msg = self._apply_strategy_preset_impl(mode, show_popup=True)
        if not ok:
            self._enqueue_log(f"[strategy] {msg}")

    def start_selected_strategy(self) -> None:
        self._flush_autosave()
        mode = self._selected_strategy_mode()
        ok, msg = self._apply_strategy_preset_impl(mode, show_popup=False)
        self._enqueue_log(f"[strategy] {msg}")
        if not ok:
            return
        self._enqueue_log("[strategy] preset applied. Use Start (Trade+ML) on Control tab.")

    def start_spike_trading(self) -> None:
        self.strategy_mode_var.set(STRATEGY_PRESET_MODES["spot_spike"])
        self.start_selected_strategy()

    def _training_pause_flag_path(self) -> Path:
        raw = self._load_yaml()
        path = self._resolve_training_pause_flag(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _runtime_config_path_for_mode(self, mode: str) -> Path:
        safe = str(mode).strip().lower().replace("-", "_")
        path = ROOT_DIR / "data" / "runtime_configs" / f"config.runtime.{safe}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _build_runtime_config_for_mode(self, base_raw: dict[str, Any], mode: str) -> dict[str, Any]:
        raw = dict(base_raw)
        raw.setdefault("bybit", {})
        raw.setdefault("strategy", {})
        raw.setdefault("ml", {})
        bybit = raw["bybit"]
        strategy = raw["strategy"]
        runtime = self._mode_runtime(mode)

        bybit["market_category"] = runtime["category"]
        strategy["runtime_strategy"] = runtime["runtime_strategy"]
        strategy["ui_strategy_preset"] = mode
        strategy["ui_enabled_strategy_modes"] = [mode]

        if mode == "spot_spread":
            strategy["spike_burst_enabled"] = False
            strategy.setdefault("strict_pair_filter", True)
        elif mode == "spot_spike":
            strategy["spike_burst_enabled"] = True
            strategy.setdefault("strict_pair_filter", True)
            raw["ml"]["mode"] = "online"
        elif mode == "futures_spike_reversal":
            strategy["spike_burst_enabled"] = False
            strategy["strict_pair_filter"] = False
            strategy["spike_reversal_reverse"] = True
            strategy["spike_reversal_taker"] = True
            strategy["spike_reversal_min_strength_bps"] = max(float(strategy.get("spike_threshold_bps") or 12.0), 0.0)
            strategy["spike_reversal_entry_offset_ticks"] = max(int(strategy.get("spike_burst_tick_step") or 1), 0)
            strategy["spike_reversal_qty_scale"] = max(float(strategy.get("spike_burst_qty_scale") or 0.25), 0.01)
            strategy["spike_reversal_max_symbols"] = max(int(strategy.get("scanner_top_k") or 80), 1)
            strategy["spike_reversal_cooldown_sec"] = max(float(strategy.get("spike_reversal_cooldown_sec") or 2.0), 0.1)
            raw["ml"]["mode"] = "online"
            spike_profile_id = str(strategy.get("spike_profile_id") or "spike").strip() or "spike"
            profiles_raw = strategy.get("action_profiles")
            profiles: list[dict[str, Any]] = [dict(p) for p in profiles_raw if isinstance(p, dict)] if isinstance(profiles_raw, list) else []
            for profile in profiles:
                if str(profile.get("profile_id") or "").strip() == spike_profile_id:
                    profile["maker_only"] = False
            strategy["action_profiles"] = profiles
        self._ensure_adaptive_action_profiles(strategy, mode)
        return raw

    def _write_runtime_config_for_mode(self, mode: str) -> Path:
        base = self._load_yaml()
        merged = self._build_runtime_config_for_mode(base, mode)
        out_path = self._runtime_config_path_for_mode(mode)
        out_path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return out_path

    def _start_trading_impl(self, interactive: bool, start_ml: bool = True) -> str:
        self._flush_autosave()
        mode = self._load_execution_mode()
        if interactive and mode == "live":
            if not messagebox.askyesno(
                "Live Mode Warning",
                "execution.mode=live. This can place real orders.\nContinue?",
            ):
                return "Start canceled by user."
        selected_modes = self._enabled_strategy_modes_from_ui()
        child_env = os.environ.copy()
        child_env["BOTIK_DISABLE_INTERNAL_TELEGRAM"] = "1"
        started_modes: list[str] = []
        already_running_modes: list[str] = []
        for strategy_mode in selected_modes:
            proc = self.trading_processes.get(strategy_mode)
            if proc is None:
                continue
            if proc.running:
                already_running_modes.append(strategy_mode)
                continue
            cfg_path = self._write_runtime_config_for_mode(strategy_mode)
            cmd = self._cmd("-m", "src.botik.main", "--config", str(cfg_path))
            if proc.start(cmd, ROOT_DIR, env=child_env):
                started_modes.append(strategy_mode)

        ml_msg = ""
        if start_ml:
            pause_flag = self._training_pause_flag_path()
            if pause_flag.exists():
                try:
                    pause_flag.unlink()
                except OSError:
                    pass
            ml_msg = self._start_ml_impl()
        started_txt = ",".join(started_modes) if started_modes else "none"
        already_txt = ",".join(already_running_modes) if already_running_modes else "none"
        if start_ml:
            return f"Trade start: started=[{started_txt}] already_running=[{already_txt}]. {ml_msg}"
        return f"Trading start: started=[{started_txt}] already_running=[{already_txt}]."

    def start_trading(self) -> None:
        self._enqueue_log(f"[ui] {self._start_trading_impl(interactive=True, start_ml=True)}")

    def _stop_trading_impl(self, stop_ml: bool = True) -> str:
        stopped_modes: list[str] = []
        for mode, proc in self.trading_processes.items():
            if proc.stop():
                stopped_modes.append(mode)
        ml_msg = ""
        if stop_ml:
            ml_msg = self._stop_ml_impl()
        stopped_txt = ",".join(stopped_modes) if stopped_modes else "none"
        if stop_ml:
            return f"Trade stop: stopped=[{stopped_txt}]. {ml_msg}"
        return f"Trading stop: stopped=[{stopped_txt}]."

    def stop_trading(self) -> None:
        self._enqueue_log(f"[ui] {self._stop_trading_impl(stop_ml=True)}")

    def _start_ml_impl(self) -> str:
        self._flush_autosave()
        raw_cfg = self._load_yaml()
        ml_mode = str(((raw_cfg.get("ml") or {}).get("mode") or "bootstrap")).strip().lower()
        if ml_mode not in {"bootstrap", "train", "predict", "online"}:
            ml_mode = "bootstrap"
        cmd = self._cmd("-m", "ml_service.run_loop", "--config", self.config_var.get(), "--mode", ml_mode)
        started = self.ml.start(cmd, ROOT_DIR)
        return "ML process started." if started else "ML already running."

    def _stop_ml_impl(self) -> str:
        stopped = self.ml.stop()
        return "ML process stopped." if stopped else "ML already stopped."

    def start_ml(self) -> None:
        self._enqueue_log(f"[ui] {self._start_ml_impl()}")

    def stop_ml(self) -> None:
        self._enqueue_log(f"[ui] {self._stop_ml_impl()}")

    def start_training(self) -> None:
        self.start_ml()

    def stop_training(self) -> None:
        self.stop_ml()

    def pause_training(self) -> None:
        flag = self._training_pause_flag_path()
        if flag.exists():
            try:
                flag.unlink()
            except OSError as exc:
                self._enqueue_log(f"[ui] failed to resume training: {exc}")
                return
            self._enqueue_log("[ui] training resumed")
        else:
            try:
                flag.write_text("paused\n", encoding="utf-8")
            except OSError as exc:
                self._enqueue_log(f"[ui] failed to pause training: {exc}")
                return
            self._enqueue_log("[ui] training paused")
        self.refresh_runtime_snapshot()

    def run_preflight(self) -> None:
        self._flush_autosave()
        cmd = self._cmd("tools/preflight.py", "--config", self.config_var.get(), "--timeout-sec", "15")
        threading.Thread(target=self._run_one_shot, args=(cmd,), daemon=True).start()

    def show_help(self) -> None:
        text = (
            "Быстрая помощь\n\n"
            "1) Открытые ордера\n"
            "- Status=New/PartiallyFilled: лимитный ордер еще в книге.\n"
            "- Status=HOLD:*: монета на балансе (ожидание/попытка выхода).\n"
            "- USD: оценка позиции в USDT.\n"
            "- Order: цена выставленного лимитного ордера (если есть).\n"
            "- Now: текущая цена из последних signals/executions.\n"
            "- Entry: средняя цена входа.\n"
            "- Target: расчетная цель продажи по профиту+буферу+комиссии.\n\n"
            "- PnL%: изменение относительно Entry.\n"
            "- PnL USDT: текущий нереализованный результат в котируемой валюте.\n"
            "- Exit: прогресс до Target в %.\n"
            "- HOLD:WAIT_TARGET: текущая цена еще ниже Target.\n"
            "- HOLD:EXIT_READY: цель достигнута, бот пытается держать котировку на выход.\n"
            "- HOLD:DUST_BLOCKED: остаток слишком мал (биржа отклоняет qty после нормализации).\n\n"
            "- min_active_position_usdt: позиции ниже порога скрываются из активных.\n\n"
            "- Кнопка 'Закрыть выбранную позицию' отправляет IOC manual-close по выбранной строке.\n\n"
            "2) История ордеров\n"
            "- Показывается последний статус по order_link_id из order_events.\n\n"
            "3) ML Panel\n"
            "- State показывает режим: bootstrap/train/predict/online.\n"
            "- outcomes: закрытые outcomes в БД.\n"
            "- paired: сигналы, где есть и buy, и sell execution.\n"
            "- filled: число Filled-событий ордеров.\n"
            "4) Models tab\n"
            "- Показывает статистику по model_registry: outcomes, plus/minus, net PnL.\n"
            "- Можно вручную активировать выбранную модель.\n\n"
            "5) Strategies tab\n"
            "- Здесь настраиваются пресеты; запуск/стоп делаются на вкладке Control.\n"
            "- На Control можно включить сразу несколько стратегий чекбоксами.\n"
        )
        messagebox.showinfo("Help", text)

    def _run_one_shot(self, cmd: list[str]) -> None:
        self._enqueue_log(f"[preflight] started: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout is not None:
            for line in proc.stdout:
                self._enqueue_log(f"[preflight] {line.rstrip()}")
        code = proc.wait()
        self._enqueue_log(f"[preflight] exited with code {code}")

    def _on_ctrl_c(self, event: tk.Event) -> str:
        widget = event.widget
        if widget is self.log_text:
            self._copy_selected_log_from_widget(self.log_text)
            return "break"
        if self.log_text_full is not None and widget is self.log_text_full:
            self._copy_selected_log_from_widget(self.log_text_full)
            return "break"
        self.copy_selected_log()
        return "break"

    def _show_log_context_menu(self, event: tk.Event) -> None:
        if event.widget is self.log_text:
            self._log_menu_target = self.log_text
        elif self.log_text_full is not None and event.widget is self.log_text_full:
            self._log_menu_target = self.log_text_full
        else:
            self._log_menu_target = None
        try:
            self.log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.log_menu.grab_release()

    def _active_log_widget(self) -> tk.Text:
        focused = self.root.focus_get()
        if focused is self.log_text:
            return self.log_text
        if self.log_text_full is not None and focused is self.log_text_full:
            return self.log_text_full
        if self._log_menu_target is self.log_text:
            return self.log_text
        if self.log_text_full is not None and self._log_menu_target is self.log_text_full:
            return self.log_text_full
        return self.log_text

    def _copy_selected_log_from_widget(self, widget: tk.Text) -> bool:
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        self._enqueue_log("[ui] copied selected log text")
        return True

    def copy_selected_log(self) -> None:
        self._copy_selected_log_from_widget(self._active_log_widget())
        self._log_menu_target = None

    def copy_all_log(self) -> None:
        full = self._active_log_widget().get("1.0", tk.END).rstrip()
        if not full:
            self._log_menu_target = None
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(full)
        self._enqueue_log("[ui] copied full log")
        self._log_menu_target = None

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)
        if self.log_text_full is not None:
            self.log_text_full.delete("1.0", tk.END)
        self._log_messages.clear()
        self._known_log_pairs.clear()
        self._sync_log_pair_filter_values()
        self._log_autoscroll_main = True
        self._log_autoscroll_full = True
        self._log_menu_target = None
        self._update_log_jump_buttons()

    def _on_close(self) -> None:
        self._flush_autosave()
        if self._telegram_stop_event is not None:
            self._telegram_stop_event.set()
        if self._telegram_thread is not None and self._telegram_thread.is_alive():
            self._telegram_thread.join(timeout=2.0)
        self._stop_trading_impl(stop_ml=True)
        self.sleep_blocker.disable()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = BotikGui()
    app.run()


if __name__ == "__main__":
    main()

