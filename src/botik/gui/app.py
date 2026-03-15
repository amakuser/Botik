"""
Desktop Dashboard Shell for local operation (Windows/Linux desktop).

Features:
- Start/stop runtime and training processes.
- Live logs inside the application.
- Preflight run button.
- Technical Settings Workspace for secrets, manifests, paths and launcher diagnostics.
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
from src.botik.version import get_app_version_label, load_app_version, load_build_sha
from src.botik.gui.theme import apply_dark_theme
from src.botik.gui.ui_components import card, labeled_combobox, labeled_entry
from src.botik.storage.futures_store import list_futures_positions
from src.botik.storage.spot_store import (
    insert_spot_exit_decision,
    list_spot_exit_decisions,
    list_spot_fills,
    list_spot_holdings,
    list_spot_orders,
    summarize_spot_holdings,
)
from src.botik.utils.runtime import runtime_root


ROOT_DIR = runtime_root(__file__, levels_up=3)
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
GUI_LOG_PATH = ROOT_DIR / "logs" / "gui.log"
DASHBOARD_RELEASE_MANIFEST_PATH = ROOT_DIR / "dashboard_release_manifest.yaml"
DASHBOARD_WORKSPACE_MANIFEST_PATH = ROOT_DIR / "dashboard_workspace_manifest.yaml"
ACTIVE_MODELS_MANIFEST_PATH = ROOT_DIR / "active_models.yaml"

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

RECONCILIATION_ENTRY_LOCK_ISSUES: tuple[str, ...] = (
    "orphaned_exchange_position",
    "orphaned_exchange_order",
    "local_position_missing_on_exchange",
    "local_order_missing_on_exchange",
)

DASHBOARD_WORKSPACE_TABS: tuple[tuple[str, str], ...] = (
    ("home", "Dashboard Home"),
    ("spot", "Spot Workspace"),
    ("futures", "Futures Workspace"),
    ("model_registry", "Model Registry Workspace"),
    ("telegram", "Telegram Workspace"),
    ("logs", "Logs Workspace"),
    ("ops", "Ops Workspace"),
    ("settings", "Settings Workspace"),
)

TELEGRAM_WORKSPACE_AVAILABLE_COMMANDS: tuple[str, ...] = (
    "/status",
    "/balance",
    "/orders",
    "/starttrading",
    "/stoptrading",
    "/pull",
    "/restartsoft",
    "/restarthard",
    "/help",
)

TELEGRAM_WORKSPACE_ACTIONS: tuple[str, ...] = (
    "Refresh",
    "Test Send",
    "Reload Telegram Status",
    "Open Telegram Logs",
    "Open Telegram Settings/Profile",
    "Copy Chat Summary",
)

DASHBOARD_LOG_CHANNELS: tuple[str, ...] = (
    "ALL",
    "spot",
    "futures_training",
    "futures_paper",
    "telegram",
    "models",
    "ops",
    "ui",
    "system",
)

DASHBOARD_LOG_INSTRUMENTS: tuple[str, ...] = (
    "ALL",
    "spot",
    "futures",
    "telegram",
    "models",
    "ops",
)


def dashboard_workspace_labels() -> list[str]:
    return [label for _, label in DASHBOARD_WORKSPACE_TABS]


def detect_dashboard_log_level(text: str) -> str:
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


def detect_dashboard_log_pair(text: str) -> str:
    upper = str(text or "").upper()
    found = re.search(r"\b([A-Z0-9]{2,}(?:USDT|USDC|USD|BTC|ETH))\b", upper)
    return str(found.group(1) if found else "")


def detect_dashboard_log_channel(text: str) -> str:
    msg = str(text or "").strip()
    lower = msg.lower()
    prefix_match = re.match(r"^\s*\[([^\]]+)\]", lower)
    prefix = str(prefix_match.group(1) if prefix_match else "").strip()

    if prefix.startswith("spot"):
        return "spot"
    if prefix.startswith("futures-paper"):
        return "futures_paper"
    if prefix.startswith("futures-training") or prefix.startswith("ml"):
        return "futures_training"
    if prefix.startswith("telegram"):
        return "telegram"
    if prefix.startswith("models"):
        return "models"
    if prefix.startswith("ops") or prefix.startswith("reconciliation") or prefix.startswith("protection") or prefix.startswith("risk"):
        return "ops"
    if prefix.startswith("ui"):
        return "ui"
    if prefix:
        return "system"

    if "telegram" in lower:
        return "telegram"
    if "futures-paper" in lower or "paper session" in lower or "paper results" in lower:
        return "futures_paper"
    if "futures" in lower or "training" in lower or "checkpoint" in lower or "evaluation" in lower:
        return "futures_training"
    if "model registry" in lower or "champion" in lower or "challenger" in lower:
        return "models"
    if "spot" in lower:
        return "spot"
    if "reconcile" in lower or "protection" in lower or "issue" in lower or "audit" in lower:
        return "ops"
    return "system"


def detect_dashboard_log_instrument(text: str) -> str:
    lower = str(text or "").lower()
    channel = detect_dashboard_log_channel(text)
    if channel == "spot":
        return "spot"
    if channel in {"futures_training", "futures_paper"}:
        return "futures"
    if channel == "telegram":
        return "telegram"
    if channel == "models":
        return "models"
    if channel in {"ops", "ui"}:
        return "ops"
    if "spot" in lower:
        return "spot"
    if "futures" in lower or "checkpoint" in lower or "training" in lower:
        return "futures"
    if "telegram" in lower:
        return "telegram"
    if "model" in lower:
        return "models"
    return "ops"


def dashboard_log_matches_filters(
    text: str,
    *,
    level_filter: str,
    pair_filter: str,
    channel_filter: str,
    instrument_filter: str,
    query_filter: str,
) -> bool:
    msg = str(text or "")
    level_value = str(level_filter or "ALL").strip().upper()
    pair_value = str(pair_filter or "ALL").strip().upper()
    channel_value = str(channel_filter or "ALL").strip().lower()
    instrument_value = str(instrument_filter or "ALL").strip().lower()
    query_value = str(query_filter or "").strip().lower()

    if level_value not in {"", "ALL"} and detect_dashboard_log_level(msg) != level_value:
        return False
    if pair_value not in {"", "ALL"} and pair_value not in msg.upper():
        return False
    if channel_value not in {"", "all"} and detect_dashboard_log_channel(msg) != channel_value:
        return False
    if instrument_value not in {"", "all"} and detect_dashboard_log_instrument(msg) != instrument_value:
        return False
    if query_value and query_value not in msg.lower():
        return False
    return True


def filter_dashboard_strategy_modes(
    modes: list[str] | tuple[str, ...] | None,
    instrument: str,
) -> list[str]:
    instrument_key = str(instrument or "").strip().lower()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in modes or []:
        mode = str(raw or "").strip().lower()
        if mode not in STRATEGY_MODE_RUNTIME or mode in seen:
            continue
        seen.add(mode)
        normalized.append(mode)

    if instrument_key == "spot":
        filtered = [mode for mode in normalized if STRATEGY_MODE_RUNTIME.get(mode, {}).get("category") == "spot"]
        return filtered or ["spot_spread"]
    if instrument_key == "futures":
        filtered = [mode for mode in normalized if STRATEGY_MODE_RUNTIME.get(mode, {}).get("category") != "spot"]
        return filtered or ["futures_spike_reversal"]
    return normalized


def dashboard_strategy_preset_labels(instrument: str) -> list[str]:
    instrument_key = str(instrument or "").strip().lower()
    labels: list[str] = []
    for label, mode in STRATEGY_PRESET_LABELS.items():
        category = STRATEGY_MODE_RUNTIME.get(mode, {}).get("category")
        if instrument_key == "spot" and category == "spot":
            labels.append(label)
        if instrument_key == "futures" and category != "spot":
            labels.append(label)
    if labels:
        return labels
    return ["Spot Spread (Maker)"] if instrument_key == "spot" else ["Futures Spike Reversal"]


def _normalize_dashboard_workspace_key(raw_key: Any) -> str:
    key = str(raw_key or "").strip().lower()
    alias_map = {
        "futures_training": "futures",
        "models": "model_registry",
    }
    return alias_map.get(key, key)


def _default_workspace_manifest_tabs() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "enabled": True,
            "visible": True,
            "order": idx,
        }
        for idx, (key, label) in enumerate(DASHBOARD_WORKSPACE_TABS, start=1)
    ]


def resolve_dashboard_workspace_tabs(manifest_data: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    defaults_map = {key: label for key, label in DASHBOARD_WORKSPACE_TABS}
    legacy_default_labels = {
        "futures_training": "Futures Training Workspace",
        "models": "Models",
    }
    entries: list[dict[str, Any]] = []
    raw_entries = manifest_data.get("workspaces") if isinstance(manifest_data, dict) else None
    if isinstance(raw_entries, list):
        for idx, item in enumerate(raw_entries, start=1):
            if not isinstance(item, dict):
                continue
            raw_key = str(item.get("key") or "").strip().lower()
            key = _normalize_dashboard_workspace_key(raw_key)
            if key not in defaults_map:
                continue
            raw_label = str(item.get("label") or "").strip()
            if raw_key != key and (not raw_label or raw_label == legacy_default_labels.get(raw_key, "")):
                label = defaults_map[key]
            else:
                label = raw_label or defaults_map[key]
            enabled = bool(item.get("enabled", True))
            visible = bool(item.get("visible", True))
            order_raw = item.get("order", idx)
            try:
                order = int(order_raw)
            except (TypeError, ValueError):
                order = idx
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "enabled": enabled,
                    "visible": visible,
                    "order": order,
                    "idx": idx,
                }
            )

    if not entries:
        entries = [
            {
                "key": key,
                "label": label,
                "enabled": True,
                "visible": True,
                "order": idx,
                "idx": idx,
            }
            for idx, (key, label) in enumerate(DASHBOARD_WORKSPACE_TABS, start=1)
        ]

    enabled_entries = [item for item in entries if bool(item.get("enabled")) and bool(item.get("visible"))]
    if not enabled_entries:
        enabled_entries = [
            {
                "key": key,
                "label": label,
                "enabled": True,
                "visible": True,
                "order": idx,
                "idx": idx,
            }
            for idx, (key, label) in enumerate(DASHBOARD_WORKSPACE_TABS, start=1)
        ]
    enabled_entries.sort(key=lambda x: (int(x.get("order") or 0), int(x.get("idx") or 0)))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for item in enabled_entries:
        key = str(item.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((key, str(item.get("label") or defaults_map.get(key, key))))
    if "home" not in seen:
        out.insert(0, ("home", defaults_map["home"]))
    return out


def load_dashboard_workspace_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DASHBOARD_WORKSPACE_MANIFEST_PATH
    out: dict[str, Any] = {
        "manifest_status": "missing",
        "manifest_path": str(manifest_path),
        "loaded_at": "-",
        "workspaces": _default_workspace_manifest_tabs(),
    }
    if not manifest_path.exists():
        out["manifest_status"] = "defaulted"
        return out
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            out["manifest_status"] = "failed"
            return out
        resolved = resolve_dashboard_workspace_tabs(raw)
        out["workspaces"] = [
            {"key": key, "label": label, "enabled": True, "visible": True, "order": idx}
            for idx, (key, label) in enumerate(resolved, start=1)
        ]
        loaded_dt = datetime.fromtimestamp(float(manifest_path.stat().st_mtime), tz=timezone.utc).astimezone()
        out["loaded_at"] = loaded_dt.strftime("%Y-%m-%d %H:%M:%S")
        out["manifest_status"] = "loaded"
        return out
    except Exception:
        out["manifest_status"] = "failed"
        return out


def load_active_models_pointer(path: Path | None = None) -> dict[str, str]:
    pointer_path = path or ACTIVE_MODELS_MANIFEST_PATH
    out: dict[str, str] = {
        "manifest_status": "missing",
        "manifest_path": str(pointer_path),
        "loaded_at": "-",
        "active_spot_model": "unknown",
        "active_futures_model": "unknown",
        "spot_checkpoint_path": "",
        "futures_checkpoint_path": "",
    }
    if not pointer_path.exists():
        return out
    try:
        raw = yaml.safe_load(pointer_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            out["manifest_status"] = "failed"
            return out
        out["active_spot_model"] = _component_text(raw.get("active_spot_model"), fallback="unknown")
        out["active_futures_model"] = _component_text(raw.get("active_futures_model"), fallback="unknown")
        out["spot_checkpoint_path"] = str(raw.get("spot_checkpoint_path") or "")
        out["futures_checkpoint_path"] = str(raw.get("futures_checkpoint_path") or "")
        loaded_dt = datetime.fromtimestamp(float(pointer_path.stat().st_mtime), tz=timezone.utc).astimezone()
        out["loaded_at"] = loaded_dt.strftime("%Y-%m-%d %H:%M:%S")
        out["manifest_status"] = "loaded"
        return out
    except Exception:
        out["manifest_status"] = "failed"
        return out


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


def detect_launcher_mode() -> str:
    # PyInstaller runtime sets sys.frozen=True.
    return "packaged" if bool(getattr(sys, "frozen", False)) else "source"


def build_worker_launch_command(
    *,
    process_kind: str,
    launcher_mode: str,
    python_path: str,
    config_path: str | None,
    packaged_executable: str | None = None,
    ml_mode: str | None = None,
) -> tuple[list[str], bool, str]:
    kind = str(process_kind or "").strip().lower()
    if kind not in {"trading", "ml"}:
        return [], False, f"unsupported_process_kind:{kind or 'empty'}"

    mode = str(launcher_mode or "").strip().lower() or "source"
    cfg = str(config_path or "").strip()

    if mode == "packaged":
        exe = str(packaged_executable or "").strip()
        if not exe:
            exe = str(Path(sys.executable))
        if not exe:
            return [], False, "packaged_launcher_missing_executable"
        cmd = [exe, "--nogui", "--role", kind]
        if cfg:
            cmd.extend(["--config", cfg])
        if kind == "ml":
            ml_mode_value = str(ml_mode or "").strip().lower()
            if ml_mode_value:
                cmd.extend(["--ml-mode", ml_mode_value])
        return cmd, True, "packaged"

    py = str(python_path or "").strip() or sys.executable
    if not py:
        return [], False, "source_launcher_missing_python"
    if kind == "trading":
        cmd = [py, "-m", "src.botik.main"]
        if cfg:
            cmd.extend(["--config", cfg])
        return cmd, True, "source"

    cmd = [py, "-m", "ml_service.run_loop"]
    if cfg:
        cmd.extend(["--config", cfg])
    ml_mode_value = str(ml_mode or "").strip().lower()
    if ml_mode_value:
        cmd.extend(["--mode", ml_mode_value])
    return cmd, True, "source"


def _component_text(value: Any, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text or fallback


def _parse_json_dict(raw_value: Any) -> dict[str, Any]:
    try:
        loaded = json.loads(str(raw_value or "{}"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _infer_model_registry_instrument(
    model_id: str,
    metrics: dict[str, Any] | None = None,
    release_manifest: dict[str, Any] | None = None,
) -> str:
    payload = metrics or {}
    explicit = str(
        payload.get("instrument")
        or payload.get("domain")
        or payload.get("market_category")
        or payload.get("category")
        or ""
    ).strip().lower()
    if explicit == "spot":
        return "spot"
    if explicit in {"linear", "futures", "future", "perp"}:
        return "futures"
    release = release_manifest or {}
    if model_id and model_id == str(release.get("active_spot_model_version") or "").strip():
        return "spot"
    if model_id and model_id == str(release.get("active_futures_model_version") or "").strip():
        return "futures"
    lowered = model_id.lower()
    if "spot" in lowered:
        return "spot"
    if "fut" in lowered or "future" in lowered or "perp" in lowered:
        return "futures"
    return "unknown"


def _infer_model_registry_policy(metrics: dict[str, Any] | None = None) -> str:
    payload = metrics or {}
    explicit = str(
        payload.get("policy")
        or payload.get("decision_policy")
        or payload.get("policy_mode")
        or payload.get("execution_policy")
        or ""
    ).strip()
    if explicit:
        return explicit
    if payload.get("hard_rules") is True:
        return "hard"
    return "unknown"


def _infer_model_registry_source(metrics: dict[str, Any] | None = None) -> str:
    payload = metrics or {}
    return _component_text(
        payload.get("source_mode")
        or payload.get("training_source_mode")
        or payload.get("data_source")
        or payload.get("source"),
        fallback="unknown",
    )


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_win_rate_fraction(raw_value: Any) -> float:
    text = str(raw_value or "").strip().replace("%", "")
    try:
        value = float(text or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(min(value / 100.0, 1.0), 0.0)


def build_model_registry_comparison(left: dict[str, Any], right: dict[str, Any]) -> dict[str, str]:
    left_id = _component_text(left.get("model_id"), fallback="left")
    right_id = _component_text(right.get("model_id"), fallback="right")
    left_outcomes = max(int(_float_or_zero(left.get("outcomes"))), 0)
    right_outcomes = max(int(_float_or_zero(right.get("outcomes"))), 0)
    left_win = _float_or_zero(left.get("win_rate"))
    right_win = _float_or_zero(right.get("win_rate"))
    left_pnl = _float_or_zero(left.get("net_pnl"))
    right_pnl = _float_or_zero(right.get("net_pnl"))
    left_edge = _float_or_zero(left.get("edge"))
    right_edge = _float_or_zero(right.get("edge"))

    left_score = 0
    right_score = 0
    reasons: list[str] = []
    if left_pnl > right_pnl + 1e-9:
        left_score += 2
        reasons.append(f"net_pnl favors {left_id}")
    elif right_pnl > left_pnl + 1e-9:
        right_score += 2
        reasons.append(f"net_pnl favors {right_id}")
    if left_win > right_win + 0.005:
        left_score += 1
        reasons.append(f"win_rate favors {left_id}")
    elif right_win > left_win + 0.005:
        right_score += 1
        reasons.append(f"win_rate favors {right_id}")
    if left_edge > right_edge + 0.01:
        left_score += 1
        reasons.append(f"edge favors {left_id}")
    elif right_edge > left_edge + 0.01:
        right_score += 1
        reasons.append(f"edge favors {right_id}")
    if left_outcomes >= max(5, right_outcomes) and left_outcomes > right_outcomes:
        left_score += 1
        reasons.append(f"sample_size favors {left_id}")
    elif right_outcomes >= max(5, left_outcomes) and right_outcomes > left_outcomes:
        right_score += 1
        reasons.append(f"sample_size favors {right_id}")

    left_status = str(left.get("status") or "").strip().lower()
    right_status = str(right.get("status") or "").strip().lower()
    if left_status in {"regressed", "rejected"}:
        right_score += 1
        reasons.append(f"status penalizes {left_id}")
    if right_status in {"regressed", "rejected"}:
        left_score += 1
        reasons.append(f"status penalizes {right_id}")

    left_ready = left_outcomes >= 5
    right_ready = right_outcomes >= 5
    if left_score >= right_score + 2 and left_ready:
        verdict = f"prefer:{left_id}"
        summary = f"prefer {left_id}"
    elif right_score >= left_score + 2 and right_ready:
        verdict = f"prefer:{right_id}"
        summary = f"prefer {right_id}"
    elif left_score > right_score:
        verdict = f"review:{left_id}"
        summary = f"manual review leaning {left_id}"
    elif right_score > left_score:
        verdict = f"review:{right_id}"
        summary = f"manual review leaning {right_id}"
    else:
        verdict = "hold"
        summary = "hold / no clear winner"

    if not reasons:
        reasons = ["metrics too close or insufficient data"]
    return {
        "verdict": verdict,
        "summary": summary,
        "reason_line": " | ".join(reasons),
        "left_score": str(left_score),
        "right_score": str(right_score),
    }


def build_model_registry_selector_summary(
    entries: list[dict[str, Any]],
    *,
    instrument: str,
    champion_model_id: str,
) -> str:
    instrument_key = str(instrument or "").strip().lower()
    scoped = [entry for entry in entries if str(entry.get("instrument") or "").strip().lower() == instrument_key]
    if not scoped:
        return f"{instrument_key}=no-models"
    champion = next((entry for entry in scoped if str(entry.get("model_id") or "") == champion_model_id), None)
    challengers = [entry for entry in scoped if entry is not champion]
    if champion is None:
        leader = max(
            scoped,
            key=lambda entry: (
                _float_or_zero(entry.get("net_pnl")),
                _float_or_zero(entry.get("win_rate")),
                _float_or_zero(entry.get("edge")),
                _float_or_zero(entry.get("outcomes")),
            ),
        )
        return f"{instrument_key}=review:{leader.get('model_id', 'unknown')} | no champion pointer"
    if not challengers:
        return f"{instrument_key}=hold:{champion_model_id} | champion-only"
    best = max(
        challengers,
        key=lambda entry: (
            _float_or_zero(entry.get("net_pnl")),
            _float_or_zero(entry.get("win_rate")),
            _float_or_zero(entry.get("edge")),
            _float_or_zero(entry.get("outcomes")),
        ),
    )
    comparison = build_model_registry_comparison(best, champion)
    verdict = str(comparison.get("verdict") or "hold")
    if verdict.startswith(f"prefer:{best.get('model_id', '')}") or verdict.startswith(f"review:{best.get('model_id', '')}"):
        return f"{instrument_key}={verdict} | champion={champion_model_id}"
    return f"{instrument_key}=hold:{champion_model_id}"


def write_active_model_pointer(
    model_id: str,
    instrument: str,
    *,
    path: Path | None = None,
) -> tuple[bool, str]:
    instrument_key = str(instrument or "").strip().lower()
    if instrument_key not in {"spot", "futures"}:
        return False, f"unsupported instrument={instrument_key or 'unknown'}"
    pointer_path = path or ACTIVE_MODELS_MANIFEST_PATH
    raw: dict[str, Any] = {}
    try:
        if pointer_path.exists():
            loaded = yaml.safe_load(pointer_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = dict(loaded)
    except Exception as exc:
        return False, f"active_models load failed: {exc}"
    raw["manifest_version"] = int(raw.get("manifest_version") or 1)
    raw["product"] = str(raw.get("product") or "botik_dashboard")
    raw["source"] = str(raw.get("source") or "external_active_models_pointer")
    raw.setdefault("active_spot_model", "unknown")
    raw.setdefault("active_futures_model", "unknown")
    raw.setdefault("spot_checkpoint_path", "")
    raw.setdefault("futures_checkpoint_path", "")
    raw[f"active_{instrument_key}_model"] = str(model_id or "unknown")
    try:
        pointer_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception as exc:
        return False, f"active_models write failed: {exc}"
    return True, f"active_{instrument_key}_model={model_id}"


def promote_model_registry_model(
    db_path: Path,
    model_id: str,
    instrument: str,
) -> tuple[bool, str]:
    instrument_key = str(instrument or "").strip().lower()
    if instrument_key not in {"spot", "futures"}:
        return False, f"unsupported instrument={instrument_key or 'unknown'}"
    if not db_path.exists():
        return False, f"db missing: {db_path}"
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists_local(conn, "model_registry"):
            return False, "table model_registry not found"
        rows = conn.execute(
            "SELECT id, COALESCE(model_id, ''), COALESCE(metrics_json, '{}') FROM model_registry"
        ).fetchall()
        target_row_id: int | None = None
        same_instrument_ids: list[int] = []
        for row_id, row_model_id, metrics_json_raw in rows:
            row_model = str(row_model_id or "").strip()
            metrics = _parse_json_dict(metrics_json_raw)
            row_instrument = _infer_model_registry_instrument(row_model, metrics)
            if row_instrument == instrument_key:
                same_instrument_ids.append(int(row_id))
            if row_model == model_id:
                target_row_id = int(row_id)
        if target_row_id is None:
            return False, f"model_id not found: {model_id}"
        if not same_instrument_ids:
            same_instrument_ids = [target_row_id]
        for row_id in same_instrument_ids:
            conn.execute(
                "UPDATE model_registry SET is_active=? WHERE id=?",
                (1 if row_id == target_row_id else 0, row_id),
            )
        conn.commit()
        return True, f"legacy is_active updated for {instrument_key}"
    except sqlite3.Error as exc:
        return False, str(exc)
    finally:
        conn.close()


def load_shell_build_sha() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=2.0,
            **dashboard_subprocess_run_kwargs(),
        )
        if proc.returncode == 0:
            value = str(proc.stdout or "").strip()
            if value:
                return value
    except Exception:
        pass
    return _component_text(load_build_sha(), fallback="unknown")


def load_dashboard_release_manifest(
    path: Path | None = None,
    *,
    workspace_manifest_path: Path | None = None,
    active_models_path: Path | None = None,
) -> dict[str, str]:
    version_data = load_app_version()
    workspace_manifest = load_dashboard_workspace_manifest(workspace_manifest_path)
    active_models_manifest = load_active_models_pointer(active_models_path)
    out: dict[str, str] = {
        "shell_name": "Dashboard Shell",
        "shell_version": _component_text(version_data.version, fallback="0.0.0"),
        "shell_build_sha": load_shell_build_sha(),
        "shell_version_source": "VERSION",
        "shell_build_source": "version.txt",
        "workspace_pack_version": "unknown",
        "spot_runtime_version": "unknown",
        "futures_training_engine_version": "unknown",
        "telegram_bot_module_version": "unknown",
        "active_spot_model_version": "unknown",
        "active_futures_model_version": "unknown",
        "db_schema_version": "unknown",
        "active_config_profile": "unknown",
        "release_source": "external_manifest",
        "loaded_at": "-",
        "manifest_status": "missing",
        "manifest_path": str(path or DASHBOARD_RELEASE_MANIFEST_PATH),
        "workspace_manifest_status": str(workspace_manifest.get("manifest_status") or "missing"),
        "workspace_manifest_path": str(workspace_manifest.get("manifest_path") or DASHBOARD_WORKSPACE_MANIFEST_PATH),
        "workspace_manifest_loaded_at": str(workspace_manifest.get("loaded_at") or "-"),
        "workspace_order_line": " / ".join(
            str(item.get("label") or item.get("key") or "")
            for item in list(workspace_manifest.get("workspaces") or [])
            if isinstance(item, dict)
        )
        or "unknown",
        "active_models_manifest_status": str(active_models_manifest.get("manifest_status") or "missing"),
        "active_models_manifest_path": str(active_models_manifest.get("manifest_path") or ACTIVE_MODELS_MANIFEST_PATH),
        "active_models_manifest_loaded_at": str(active_models_manifest.get("loaded_at") or "-"),
    }
    manifest_path = path or DASHBOARD_RELEASE_MANIFEST_PATH
    if not manifest_path.exists():
        if str(active_models_manifest.get("active_spot_model") or "").strip():
            out["active_spot_model_version"] = _component_text(active_models_manifest.get("active_spot_model"))
        if str(active_models_manifest.get("active_futures_model") or "").strip():
            out["active_futures_model_version"] = _component_text(active_models_manifest.get("active_futures_model"))
        return out
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            out["manifest_status"] = "failed"
            return out
        shell = raw.get("shell") if isinstance(raw.get("shell"), dict) else {}
        components = raw.get("components") if isinstance(raw.get("components"), dict) else {}
        release = raw.get("release") if isinstance(raw.get("release"), dict) else {}
        external_manifests = raw.get("external_manifests") if isinstance(raw.get("external_manifests"), dict) else {}
        out["shell_name"] = _component_text(shell.get("name") if isinstance(shell, dict) else "", fallback="Dashboard Shell")
        out["shell_version_source"] = _component_text(
            shell.get("version_source") if isinstance(shell, dict) else "",
            fallback="VERSION",
        )
        out["shell_build_source"] = _component_text(
            shell.get("build_source") if isinstance(shell, dict) else "",
            fallback="version.txt",
        )
        if isinstance(external_manifests, dict):
            out["workspace_manifest_declared_path"] = _component_text(
                external_manifests.get("workspace_manifest"),
                fallback=str(Path(out["workspace_manifest_path"]).name),
            )
            out["active_models_declared_path"] = _component_text(
                external_manifests.get("active_models_pointer"),
                fallback=str(Path(out["active_models_manifest_path"]).name),
            )
        out["workspace_pack_version"] = _component_text(
            components.get("workspace_pack") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["spot_runtime_version"] = _component_text(
            components.get("spot_runtime") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["futures_training_engine_version"] = _component_text(
            components.get("futures_training_engine") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["telegram_bot_module_version"] = _component_text(
            components.get("telegram_bot_module") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["active_spot_model_version"] = _component_text(
            components.get("active_spot_model") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["active_futures_model_version"] = _component_text(
            components.get("active_futures_model") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["db_schema_version"] = _component_text(
            components.get("db_schema") if isinstance(components, dict) else "",
            fallback="unknown",
        )
        out["active_config_profile"] = _component_text(
            release.get("active_config_profile") if isinstance(release, dict) else "",
            fallback="unknown",
        )
        out["release_source"] = _component_text(
            release.get("source") if isinstance(release, dict) else "",
            fallback="external_manifest",
        )
        loaded_dt = datetime.fromtimestamp(float(manifest_path.stat().st_mtime), tz=timezone.utc).astimezone()
        out["loaded_at"] = loaded_dt.strftime("%Y-%m-%d %H:%M:%S")
        out["manifest_status"] = "loaded"
        ext_spot = _component_text(active_models_manifest.get("active_spot_model"), fallback="unknown")
        ext_fut = _component_text(active_models_manifest.get("active_futures_model"), fallback="unknown")
        if ext_spot != "unknown":
            out["active_spot_model_version"] = ext_spot
        if ext_fut != "unknown":
            out["active_futures_model_version"] = ext_fut
        return out
    except Exception:
        out["manifest_status"] = "failed"
        ext_spot = _component_text(active_models_manifest.get("active_spot_model"), fallback="unknown")
        ext_fut = _component_text(active_models_manifest.get("active_futures_model"), fallback="unknown")
        if ext_spot != "unknown":
            out["active_spot_model_version"] = ext_spot
        if ext_fut != "unknown":
            out["active_futures_model_version"] = ext_fut
        return out


def build_dashboard_release_home_sections(manifest: dict[str, str]) -> dict[str, str]:
    release_status = _component_text(manifest.get("manifest_status"), fallback="missing")
    workspace_status = _component_text(manifest.get("workspace_manifest_status"), fallback="missing")
    models_status = _component_text(manifest.get("active_models_manifest_status"), fallback="missing")
    shell_line = (
        f"{manifest.get('shell_name', 'Dashboard Shell')} "
        f"{manifest.get('shell_version', 'unknown')} "
        f"| build={manifest.get('shell_build_sha', 'unknown')} "
        f"| version_source={manifest.get('shell_version_source', 'VERSION')} "
        f"| build_source={manifest.get('shell_build_source', 'version.txt')}"
    )
    status_line = (
        f"release={release_status} @ {manifest.get('loaded_at', '-')} "
        f"| workspace_manifest={workspace_status} "
        f"| active_models_manifest={models_status} "
        f"| source={manifest.get('release_source', 'external_manifest')}"
    )
    components_line = (
        f"workspace_pack={manifest.get('workspace_pack_version', 'unknown')} | "
        f"spot_runtime={manifest.get('spot_runtime_version', 'unknown')} | "
        f"futures_training={manifest.get('futures_training_engine_version', 'unknown')} | "
        f"telegram={manifest.get('telegram_bot_module_version', 'unknown')} | "
        f"db_schema={manifest.get('db_schema_version', 'unknown')}"
    )
    models_line = (
        f"spot_model={manifest.get('active_spot_model_version', 'unknown')} | "
        f"futures_model={manifest.get('active_futures_model_version', 'unknown')} | "
        f"profile={manifest.get('active_config_profile', 'unknown')}"
    )
    manifests_line = (
        f"release={Path(str(manifest.get('manifest_path') or DASHBOARD_RELEASE_MANIFEST_PATH)).name} | "
        f"workspace={Path(str(manifest.get('workspace_manifest_path') or DASHBOARD_WORKSPACE_MANIFEST_PATH)).name} | "
        f"active_models={Path(str(manifest.get('active_models_manifest_path') or ACTIVE_MODELS_MANIFEST_PATH)).name}"
    )
    workspace_line = f"workspace_order={manifest.get('workspace_order_line', 'unknown')}"
    return {
        "status_line": status_line,
        "shell_line": shell_line,
        "components_line": components_line,
        "models_line": models_line,
        "manifests_line": manifests_line,
        "workspace_line": workspace_line,
    }


def format_dashboard_release_panel(manifest: dict[str, str]) -> str:
    sections = build_dashboard_release_home_sections(manifest)
    return "\n".join(
        [
            f"Release Manifest Status: {manifest.get('manifest_status', 'missing')}",
            f"Release Manifest Loaded At: {manifest.get('loaded_at', '-')}",
            sections["status_line"],
            sections["shell_line"],
            sections["components_line"],
            sections["models_line"],
            sections["manifests_line"],
            sections["workspace_line"],
        ]
    )


def load_model_registry_workspace_read_model(
    db_path: Path,
    *,
    release_manifest: dict[str, Any] | None = None,
    limit: int = 300,
) -> dict[str, Any]:
    release = release_manifest or {}
    active_spot_model = str(release.get("active_spot_model_version") or "unknown")
    active_futures_model = str(release.get("active_futures_model_version") or "unknown")
    out: dict[str, Any] = {
        "summary_line": (
            f"total=0 | spot=0 | futures=0 | champion_spot={active_spot_model} | champion_futures={active_futures_model}"
        ),
        "status_line": (
            "selector=active_models.yaml | legacy_db_slot=compatibility_only | compare source=unavailable"
        ),
        "rows": [],
        "actions": [
            "Refresh",
            "Promote Selected to Active",
            "Compare Selected Models",
            "Open Model Stats",
            "Copy Artifact Path",
        ],
        "total_models": 0,
        "spot_models": 0,
        "futures_models": 0,
        "unknown_models": 0,
        "champion_spot": active_spot_model,
        "champion_futures": active_futures_model,
    }
    if not db_path.exists():
        return out

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists_local(conn, "model_registry"):
            return out

        has_model_stats = _table_exists_local(conn, "model_stats")
        has_outcomes = _table_exists_local(conn, "outcomes")
        has_signals = _table_exists_local(conn, "signals")

        latest_stats: dict[str, dict[str, float]] = {}
        if has_model_stats:
            for model_id_raw, edge, fill_rate, win_rate in conn.execute(
                """
                SELECT ms.model_id, ms.net_edge_mean, ms.fill_rate, ms.win_rate
                FROM model_stats ms
                JOIN (
                    SELECT model_id, MAX(ts_ms) AS max_ts
                    FROM model_stats
                    GROUP BY model_id
                ) x ON x.model_id = ms.model_id AND x.max_ts = ms.ts_ms
                """
            ).fetchall():
                latest_stats[str(model_id_raw or "")] = {
                    "edge": float(edge or 0.0),
                    "fill_rate": float(fill_rate or 0.0),
                    "win_rate": float(win_rate or 0.0),
                }

        outcomes_by_model: dict[str, dict[str, float]] = {}
        if has_outcomes and has_signals:
            for model_id_raw, outcomes_total, plus_count, net_pnl_quote in conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap') AS model_id,
                    COUNT(*) AS outcomes_total,
                    SUM(CASE WHEN COALESCE(o.net_pnl_quote, 0.0) > 0 THEN 1 ELSE 0 END) AS plus_count,
                    COALESCE(SUM(o.net_pnl_quote), 0.0) AS net_pnl_quote
                FROM outcomes o
                LEFT JOIN signals s ON s.signal_id = o.signal_id
                GROUP BY COALESCE(NULLIF(s.active_model_id, ''), NULLIF(s.model_id, ''), 'bootstrap')
                """
            ).fetchall():
                outcomes_by_model[str(model_id_raw or "")] = {
                    "outcomes": float(outcomes_total or 0.0),
                    "plus_count": float(plus_count or 0.0),
                    "net_pnl": float(net_pnl_quote or 0.0),
                }

        rows = conn.execute(
            """
            SELECT
                COALESCE(model_id, ''),
                COALESCE(path_or_payload, ''),
                COALESCE(metrics_json, '{}'),
                COALESCE(created_at_utc, ''),
                COALESCE(is_active, 0)
            FROM model_registry
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(int(limit), 1),),
        ).fetchall()

        total_models = 0
        spot_models = 0
        futures_models = 0
        unknown_models = 0
        out_rows: list[tuple[str, ...]] = []
        entry_payloads: list[dict[str, Any]] = []
        for model_id_raw, path_or_payload, metrics_json_raw, created_at, is_active in rows:
            model_id = str(model_id_raw or "").strip()
            metrics = _parse_json_dict(metrics_json_raw)
            instrument = _infer_model_registry_instrument(model_id, metrics, release_manifest=release)
            policy = _infer_model_registry_policy(metrics)
            source_mode = _infer_model_registry_source(metrics)
            status = _component_text(metrics.get("status"), fallback="candidate")
            role = status
            if model_id and model_id == active_spot_model:
                role = "champion:spot"
            elif model_id and model_id == active_futures_model:
                role = "champion:futures"
            elif int(is_active or 0) == 1:
                role = "legacy-active"

            total_models += 1
            if instrument == "spot":
                spot_models += 1
            elif instrument == "futures":
                futures_models += 1
            else:
                unknown_models += 1

            outcome_payload = outcomes_by_model.get(model_id, {})
            outcomes_total = int(outcome_payload.get("outcomes") or 0)
            plus_count = int(outcome_payload.get("plus_count") or 0)
            if outcomes_total > 0:
                win_rate = float(plus_count) / float(max(outcomes_total, 1))
            else:
                win_rate = float(latest_stats.get(model_id, {}).get("win_rate") or 0.0)
                if win_rate <= 0.0:
                    try:
                        win_rate = float(metrics.get("open_accuracy") or 0.0)
                    except (TypeError, ValueError):
                        win_rate = 0.0
            edge_value = float(latest_stats.get(model_id, {}).get("edge") or 0.0)
            if abs(edge_value) <= 1e-9:
                try:
                    edge_value = float(metrics.get("quality_score") or 0.0)
                except (TypeError, ValueError):
                    edge_value = 0.0
            net_pnl_value = float(outcome_payload.get("net_pnl") or 0.0)
            win_rate_fraction = float(win_rate or 0.0)
            entry_payloads.append(
                {
                    "model_id": model_id,
                    "instrument": instrument,
                    "policy": policy,
                    "source_mode": source_mode,
                    "role": role,
                    "status": status,
                    "created": str(created_at or ""),
                    "outcomes": outcomes_total,
                    "win_rate": win_rate_fraction,
                    "net_pnl": net_pnl_value,
                    "edge": edge_value,
                    "artifact": str(path_or_payload or "-"),
                }
            )
            out_rows.append(
                (
                    model_id,
                    instrument,
                    policy,
                    source_mode,
                    role,
                    status,
                    str(created_at or ""),
                    str(outcomes_total),
                    f"{win_rate_fraction * 100.0:.1f}%",
                    f"{net_pnl_value:.6f}",
                    f"{edge_value:.3f}",
                    str(path_or_payload or "-"),
                )
            )

        compare_source = "outcomes/model_stats" if has_outcomes and has_signals else "model_registry metrics only"
        spot_selector = build_model_registry_selector_summary(
            entry_payloads,
            instrument="spot",
            champion_model_id=active_spot_model,
        )
        futures_selector = build_model_registry_selector_summary(
            entry_payloads,
            instrument="futures",
            champion_model_id=active_futures_model,
        )
        out["rows"] = out_rows
        out["total_models"] = total_models
        out["spot_models"] = spot_models
        out["futures_models"] = futures_models
        out["unknown_models"] = unknown_models
        out["spot_selector_line"] = spot_selector
        out["futures_selector_line"] = futures_selector
        out["summary_line"] = (
            f"total={total_models} | spot={spot_models} | futures={futures_models} | unknown={unknown_models} | "
            f"champion_spot={active_spot_model} | champion_futures={active_futures_model}"
        )
        out["status_line"] = (
            f"selector=active_models.yaml | legacy_db_slot=compatibility_only | compare source={compare_source} | "
            f"{spot_selector} | {futures_selector}"
        )
        return out
    except sqlite3.Error:
        return out
    finally:
        conn.close()


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
        "reconciliation_open_issues": 0,
        "reconciliation_resolved_issues": 0,
        "reconciliation_lock_symbols": [],
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

        if _table_exists_local(conn, "reconciliation_issues"):
            counts_row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN LOWER(COALESCE(status, '')) IN ('open', 'active') THEN 1 ELSE 0 END) AS open_cnt,
                    SUM(CASE WHEN LOWER(COALESCE(status, '')) IN ('resolved', 'closed') THEN 1 ELSE 0 END) AS resolved_cnt
                FROM reconciliation_issues
                """
            ).fetchone()
            if counts_row:
                out["reconciliation_open_issues"] = int(counts_row[0] or 0)
                out["reconciliation_resolved_issues"] = int(counts_row[1] or 0)
            placeholders = ",".join("?" for _ in RECONCILIATION_ENTRY_LOCK_ISSUES)
            lock_rows = conn.execute(
                f"""
                SELECT DISTINCT UPPER(COALESCE(symbol, ''))
                FROM reconciliation_issues
                WHERE LOWER(COALESCE(status, '')) IN ('open', 'active')
                  AND issue_type IN ({placeholders})
                  AND COALESCE(symbol, '') <> ''
                ORDER BY UPPER(COALESCE(symbol, '')) ASC
                LIMIT 20
                """,
                tuple(RECONCILIATION_ENTRY_LOCK_ISSUES),
            ).fetchall()
            out["reconciliation_lock_symbols"] = [str(r[0] or "") for r in lock_rows if str(r[0] or "").strip()]

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


def build_dashboard_ops_workspace_sections(
    *,
    ops_status: dict[str, Any] | None,
    runtime_caps: dict[str, str] | None,
    trading_state: str,
    running_modes: list[str] | tuple[str, ...],
    ml_state: str,
    telegram_state: str,
    db_path: Path,
) -> dict[str, str]:
    snapshot = ops_status or {}
    capabilities = runtime_caps or {}
    lock_symbols = ",".join(list(snapshot.get("reconciliation_lock_symbols") or [])[:5]) or "-"
    open_issues = int(snapshot.get("reconciliation_open_issues") or 0)
    resolved_issues = int(snapshot.get("reconciliation_resolved_issues") or 0)
    db_status = "ok" if db_path.exists() else "missing"
    db_name = db_path.name if str(db_path or "") else "unknown"

    service_health_line = (
        "trading={trading} ({modes}) | ml={ml} | telegram={telegram}"
    ).format(
        trading=str(trading_state or "stopped"),
        modes=",".join(list(running_modes or [])) or "-",
        ml=str(ml_state or "unknown"),
        telegram=str(telegram_state or "unknown"),
    )
    reconciliation_line = (
        "status={status} @ {ts} ({trigger}) | issues open={open_cnt} resolved={resolved_cnt} | locks={locks}"
    ).format(
        status=str(snapshot.get("reconciliation_last_status") or "skipped"),
        ts=str(snapshot.get("reconciliation_last_timestamp") or "-"),
        trigger=str(snapshot.get("reconciliation_last_trigger") or "-"),
        open_cnt=open_issues,
        resolved_cnt=resolved_issues,
        locks=lock_symbols,
    )
    protection_line = (
        "{protection} | {risk}"
    ).format(
        protection=str(snapshot.get("futures_protection_line") or "none"),
        risk=str(snapshot.get("futures_risk_telemetry_line") or "funding=none | liq=none"),
    )
    db_health_line = (
        "db={db_status} ({db_name}) | spot={spot} | fut_pos={fut_pos} | fut_ord={fut_ord} | issues={issues}"
    ).format(
        db_status=db_status,
        db_name=db_name,
        spot=str(snapshot.get("spot_holdings_freshness") or "-"),
        fut_pos=str(snapshot.get("futures_positions_freshness") or "-"),
        fut_ord=str(snapshot.get("futures_orders_freshness") or "-"),
        issues=str(snapshot.get("reconciliation_issues_freshness") or "-"),
    )
    capabilities_line = (
        "reconciliation={reconcile} | protection={protection} | funding_freshness={funding} | liq_freshness={liq}"
    ).format(
        reconcile=str(capabilities.get("reconciliation") or "unknown"),
        protection=str(capabilities.get("protection") or "unknown"),
        funding=str(snapshot.get("futures_funding_freshness") or "-"),
        liq=str(snapshot.get("futures_liq_snapshots_freshness") or "-"),
    )
    return {
        "service_health_line": service_health_line,
        "reconciliation_line": reconciliation_line,
        "protection_line": protection_line,
        "db_health_line": db_health_line,
        "capabilities_line": capabilities_line,
        "issues_summary_line": f"open={open_issues} | resolved={resolved_issues} | locks={lock_symbols}",
    }


SPOT_OPEN_ORDER_STATUSES: tuple[str, ...] = (
    "new",
    "partiallyfilled",
    "partially_filled",
    "untriggered",
    "active",
)


def _fmt_workspace_float(value: Any, *, precision: int = 8, fallback: str = "0") -> str:
    try:
        if value is None:
            return fallback
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        return fallback


def _fmt_workspace_ts_from_ms(value: Any) -> str:
    try:
        ms = int(value)
        if ms <= 0:
            return "-"
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return "-"


def _split_telegram_chat_ids(raw_value: Any) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    return [part for part in re.split(r"[,\s;]+", text) if part]


def _mask_telegram_chat_id(chat_id: Any) -> str:
    raw = str(chat_id or "").strip()
    if not raw:
        return ""
    if len(raw) <= 4:
        return f"{raw[:1]}***"
    return f"{raw[:2]}***{raw[-2:]}"


def _normalize_telegram_recent_rows(
    items: list[dict[str, Any]] | None,
    *,
    default_source: str,
    default_status: str = "ok",
    value_key: str = "command",
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for idx, item in enumerate(list(items or []), start=1):
        ts = str(item.get("ts") or "-")
        value = str(item.get(value_key) or item.get("message") or "unknown")
        source = str(item.get("source") or default_source)
        status = str(item.get("status") or default_status)
        rows.append((str(idx), ts, value, source, status))
    return rows


def load_telegram_workspace_read_model(
    *,
    raw_cfg: dict[str, Any] | None = None,
    env_data: dict[str, str] | None = None,
    release_manifest: dict[str, Any] | None = None,
    thread_running: bool = False,
    missing_token_reported: bool = False,
    runtime_capabilities: dict[str, str] | None = None,
    recent_commands: list[dict[str, Any]] | None = None,
    recent_alerts: list[dict[str, Any]] | None = None,
    recent_errors: list[dict[str, Any]] | None = None,
    log_lines: list[str] | None = None,
) -> dict[str, Any]:
    cfg = raw_cfg or {}
    env = env_data or {}
    manifest = release_manifest or {}
    capabilities = runtime_capabilities or {}
    tg_cfg = cfg.get("telegram") if isinstance(cfg.get("telegram"), dict) else {}

    token_env_name = str((tg_cfg.get("token_env") if isinstance(tg_cfg, dict) else "") or "TELEGRAM_BOT_TOKEN")
    chat_env_name = str((tg_cfg.get("chat_id_env") if isinstance(tg_cfg, dict) else "") or "TELEGRAM_CHAT_ID")
    bot_profile = str((tg_cfg.get("profile") if isinstance(tg_cfg, dict) else "") or "default")
    token = str(env.get(token_env_name) or "").strip()
    chat_ids_raw = str(env.get(chat_env_name) or "").strip()
    chat_ids = _split_telegram_chat_ids(chat_ids_raw)
    masked_chats = [_mask_telegram_chat_id(chat_id) for chat_id in chat_ids]

    token_configured = bool(token)
    disable_internal = str(env.get("BOTIK_DISABLE_INTERNAL_TELEGRAM") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if disable_internal:
        bot_connected = "disabled_by_env"
    elif token_configured and thread_running:
        bot_connected = "connected"
    elif token_configured:
        bot_connected = "disconnected"
    elif missing_token_reported:
        bot_connected = "disabled"
    else:
        bot_connected = "unknown"
    telegram_enabled = "yes" if token_configured and not disable_internal else "no"

    module_version = str(manifest.get("telegram_bot_module_version") or "unknown")
    if not module_version.strip():
        module_version = "unknown"
    supported_commands = list(TELEGRAM_WORKSPACE_AVAILABLE_COMMANDS)
    commands_line = ", ".join(supported_commands)

    command_rows = _normalize_telegram_recent_rows(
        recent_commands,
        default_source="telegram_bot",
        value_key="command",
    )
    alert_rows = _normalize_telegram_recent_rows(
        recent_alerts,
        default_source="telegram_module",
        value_key="message",
    )
    error_rows = _normalize_telegram_recent_rows(
        recent_errors,
        default_source="telegram_module",
        default_status="error",
        value_key="error",
    )
    if not error_rows:
        # Fallback to recent log lines when explicit Telegram error events are absent.
        for raw in reversed(list(log_lines or [])[-120:]):
            line = str(raw or "").strip()
            if "telegram" not in line.lower():
                continue
            if "error" not in line.lower() and "warning" not in line.lower():
                continue
            error_rows.append(
                (
                    str(len(error_rows) + 1),
                    "-",
                    line[-180:],
                    "log",
                    "error" if "error" in line.lower() else "warning",
                )
            )
            if len(error_rows) >= 12:
                break

    last_successful_send = "-"
    if alert_rows:
        last_successful_send = str(alert_rows[0][1] or "-")
    last_error = "not available"
    if error_rows:
        last_error = str(error_rows[0][2] or "not available")
    elif not token_configured:
        last_error = "configuration_missing_token"

    cap_reconcile = str(capabilities.get("reconciliation") or "unknown")
    cap_protection = str(capabilities.get("protection") or "unknown")
    capability_line = f"runtime_caps: reconciliation={cap_reconcile} | protection={cap_protection}"

    out: dict[str, Any] = {
        "telegram_enabled": telegram_enabled,
        "bot_connected": bot_connected,
        "bot_profile": bot_profile,
        "token_profile_name": token_env_name,
        "token_configured": "yes" if token_configured else "no",
        "allowed_chat_env": chat_env_name,
        "allowed_chat_count": len(chat_ids),
        "allowed_chats_masked": ", ".join(masked_chats) if masked_chats else "not configured",
        "commands_count": len(supported_commands),
        "available_commands": supported_commands,
        "module_version": module_version,
        "recent_commands_count": len(command_rows),
        "recent_alerts_count": len(alert_rows),
        "recent_errors_count": len(error_rows),
        "last_successful_send": last_successful_send,
        "last_error": last_error,
        "startup_status": "started" if thread_running else ("disabled" if not token_configured else "stopped"),
        "capability_line": capability_line,
        "actions": list(TELEGRAM_WORKSPACE_ACTIONS),
        "summary_line": (
            "enabled={enabled} | connected={connected} | profile={profile} | "
            "allowed_chats={chats} | recent_commands={commands} | recent_alerts={alerts} | module={module_version}"
        ).format(
            enabled=telegram_enabled,
            connected=bot_connected,
            profile=bot_profile,
            chats=len(chat_ids),
            commands=len(command_rows),
            alerts=len(alert_rows),
            module_version=module_version,
        ),
        "profile_connection_line": (
            "token_profile={token_profile} | token_configured={token_configured} | "
            "connection_status={connection_status} | startup={startup} | last_successful_send={last_send}"
        ).format(
            token_profile=token_env_name,
            token_configured="yes" if token_configured else "no",
            connection_status=bot_connected,
            startup="started" if thread_running else "not running",
            last_send=last_successful_send,
        ),
        "access_line": (
            "allowed_chat_env={chat_env} | allowed_chats={allowed_chats} | "
            "commands_restricted={restricted}"
        ).format(
            chat_env=chat_env_name,
            allowed_chats=", ".join(masked_chats) if masked_chats else "not configured",
            restricted="yes" if len(chat_ids) > 0 else "no",
        ),
        "commands_line": commands_line,
        "health_line": f"last_error={last_error} | {capability_line}",
        "recent_commands_rows": command_rows[:30],
        "recent_alerts_rows": alert_rows[:30],
        "recent_errors_rows": error_rows[:30],
    }
    return out


def classify_spot_holding_record(row: dict[str, Any]) -> dict[str, Any]:
    hold_reason = str(row.get("hold_reason") or "").strip().lower()
    strategy_owner = str(row.get("strategy_owner") or "").strip()
    recovered = bool(row.get("recovered_from_exchange"))
    auto_sell_allowed = bool(row.get("auto_sell_allowed"))
    free_qty = float(row.get("free_qty") or 0.0)
    locked_qty = float(row.get("locked_qty") or 0.0)
    total_qty = max(free_qty, 0.0) + max(locked_qty, 0.0)

    stale = hold_reason == "stale_hold"
    if hold_reason == "dust" or total_qty <= 1e-9:
        hold_class = "dust"
    elif stale:
        hold_class = "stale_hold"
    elif recovered and hold_reason == "unknown_recovered_from_exchange":
        hold_class = "recovered_unknown"
    elif hold_reason == "manual_import":
        hold_class = "manual_imported"
    elif hold_reason == "strategy_entry" or bool(strategy_owner):
        hold_class = "strategy_owned"
    else:
        hold_class = "unknown"

    position_state = "flat"
    if total_qty > 0 and locked_qty > 0 and free_qty > 0:
        position_state = "partial_locked"
    elif total_qty > 0 and locked_qty > 0:
        position_state = "locked"
    elif total_qty > 0:
        position_state = "free"

    sell_allowed = bool(auto_sell_allowed or hold_class == "strategy_owned")
    if hold_class in {"recovered_unknown", "manual_imported", "dust"} and not auto_sell_allowed:
        sell_allowed = False

    if hold_class in {"recovered_unknown", "manual_imported"} and not sell_allowed:
        exit_policy = "protected_by_policy"
    elif hold_class == "dust":
        exit_policy = "dust_protected"
    elif stale and not sell_allowed:
        exit_policy = "review_required"
    elif sell_allowed:
        exit_policy = "sell_allowed"
    else:
        exit_policy = "unknown"

    return {
        "hold_class": hold_class,
        "position_state": position_state,
        "stale": stale,
        "sell_allowed": sell_allowed,
        "exit_policy": exit_policy,
    }


def load_spot_workspace_read_model(
    db_path: Path,
    *,
    account_type: str = "UNIFIED",
    limit: int = 400,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "runtime_status": "unknown",
        "holdings_count": 0,
        "open_orders_count": 0,
        "recovered_holdings_count": 0,
        "stale_holdings_count": 0,
        "manual_holdings_count": 0,
        "strategy_owned_count": 0,
        "last_reconcile": "-",
        "last_error": "-",
        "holdings_rows": [],
        "open_orders_rows": [],
        "fills_rows": [],
        "exit_decisions_rows": [],
    }
    if not db_path.exists():
        return out

    conn = sqlite3.connect(str(db_path))
    try:
        holdings: list[dict[str, Any]] = []
        if _table_exists_local(conn, "spot_holdings"):
            holdings = list_spot_holdings(conn, account_type=account_type)
            summary = summarize_spot_holdings(conn, account_type=account_type)
            out["holdings_count"] = int(summary.get("total") or 0)
            out["recovered_holdings_count"] = int(summary.get("recovered") or 0)
            out["stale_holdings_count"] = int(summary.get("stale") or 0)
            out["manual_holdings_count"] = int(summary.get("manual_imported") or 0)
            out["strategy_owned_count"] = int(summary.get("strategy_owned") or 0)

            rows: list[tuple[str, ...]] = []
            for item in holdings[: max(int(limit), 1)]:
                cls = classify_spot_holding_record(item)
                hold_reason = str(item.get("hold_reason") or "").strip() or "unknown"
                strategy_owner = str(item.get("strategy_owner") or "").strip() or "unknown"
                rows.append(
                    (
                        "0",
                        str(item.get("symbol") or ""),
                        str(item.get("base_asset") or ""),
                        _fmt_workspace_float(item.get("free_qty"), precision=8, fallback="0"),
                        _fmt_workspace_float(item.get("locked_qty"), precision=8, fallback="0"),
                        _fmt_workspace_float(item.get("avg_entry_price"), precision=8, fallback="unknown")
                        if item.get("avg_entry_price") is not None
                        else "unknown",
                        hold_reason,
                        "yes" if bool(item.get("recovered_from_exchange")) else "no",
                        strategy_owner,
                        str(cls["hold_class"]),
                        str(cls["position_state"]),
                        str(cls["exit_policy"]),
                        str(item.get("updated_at_utc") or "unknown"),
                        "yes" if bool(cls["stale"]) else "no",
                    )
                )
            out["holdings_rows"] = rows

        if _table_exists_local(conn, "spot_orders"):
            orders = list_spot_orders(
                conn,
                account_type=account_type,
                statuses=SPOT_OPEN_ORDER_STATUSES,
                limit=limit,
            )
            out["open_orders_count"] = len(orders)
            out["open_orders_rows"] = [
                (
                    "0",
                    str(item.get("symbol") or ""),
                    str(item.get("side") or ""),
                    str(item.get("status") or ""),
                    _fmt_workspace_float(item.get("price"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("qty"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("filled_qty"), precision=8, fallback=""),
                    str(item.get("order_type") or "unknown"),
                    str(item.get("strategy_owner") or "unknown"),
                    str(item.get("updated_at_utc") or "-"),
                )
                for item in orders
            ]

        if _table_exists_local(conn, "spot_fills"):
            fills = list_spot_fills(conn, account_type=account_type, limit=limit)
            out["fills_rows"] = [
                (
                    "0",
                    str(item.get("created_at_utc") or "-"),
                    str(item.get("symbol") or ""),
                    str(item.get("side") or ""),
                    _fmt_workspace_float(item.get("price"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("qty"), precision=8, fallback=""),
                    (
                        _fmt_workspace_float(item.get("fee"), precision=8, fallback="")
                        if item.get("fee") is not None
                        else ""
                    ),
                    str(item.get("fee_currency") or ""),
                    (
                        "maker"
                        if item.get("is_maker") is True
                        else "taker"
                        if item.get("is_maker") is False
                        else "unknown"
                    ),
                    str(item.get("exec_id") or ""),
                )
                for item in fills
            ]

        if _table_exists_local(conn, "spot_exit_decisions"):
            decisions = list_spot_exit_decisions(conn, account_type=account_type, limit=limit)
            out["exit_decisions_rows"] = [
                (
                    "0",
                    str(item.get("created_at_utc") or "-"),
                    str(item.get("symbol") or ""),
                    str(item.get("decision_type") or ""),
                    str(item.get("reason") or ""),
                    str(item.get("policy_name") or "unknown"),
                    (
                        _fmt_workspace_float(item.get("pnl_pct"), precision=4, fallback="")
                        if item.get("pnl_pct") is not None
                        else ""
                    ),
                    (
                        _fmt_workspace_float(item.get("pnl_quote"), precision=6, fallback="")
                        if item.get("pnl_quote") is not None
                        else ""
                    ),
                    "yes" if bool(item.get("applied")) else "no",
                )
                for item in decisions
            ]

        if _table_exists_local(conn, "reconciliation_runs"):
            row = conn.execute(
                """
                SELECT
                    COALESCE(status, ''),
                    COALESCE(finished_at_utc, started_at_utc, '')
                FROM reconciliation_runs
                ORDER BY COALESCE(finished_at_utc, started_at_utc) DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                out["last_reconcile"] = str(row[1] or "-")
                status = str(row[0] or "").strip().lower()
                if status == "failed":
                    out["last_error"] = "last_reconcile_failed"
                out["runtime_status"] = "running" if status in {"success", "running"} else (status or "unknown")
    except sqlite3.Error:
        return out
    finally:
        conn.close()

    out["holdings_rows"] = [
        (
            str(idx),
            *tuple(row[1:]),
        )
        for idx, row in enumerate(out.get("holdings_rows") or [], start=1)
    ]
    out["open_orders_rows"] = [
        (
            str(idx),
            *tuple(row[1:]),
        )
        for idx, row in enumerate(out.get("open_orders_rows") or [], start=1)
    ]
    out["fills_rows"] = [
        (
            str(idx),
            *tuple(row[1:]),
        )
        for idx, row in enumerate(out.get("fills_rows") or [], start=1)
    ]
    out["exit_decisions_rows"] = [
        (
            str(idx),
            *tuple(row[1:]),
        )
        for idx, row in enumerate(out.get("exit_decisions_rows") or [], start=1)
    ]
    return out


def _safe_metrics_json(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        raw = json.loads(text)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _metric_or_unknown(metrics: dict[str, Any], key: str, *, precision: int = 6) -> str:
    if key not in metrics:
        return "not available"
    try:
        return f"{float(metrics.get(key)):.{precision}f}"
    except (TypeError, ValueError):
        return "not available"


def load_futures_training_workspace_read_model(
    db_path: Path,
    *,
    raw_cfg: dict[str, Any] | None = None,
    release_manifest: dict[str, Any] | None = None,
    ml_running: bool = False,
    ml_paused: bool = False,
    ml_process_state: str = "stopped",
    training_mode: str = "bootstrap",
) -> dict[str, Any]:
    cfg = raw_cfg or {}
    manifest = release_manifest or {}
    symbols = cfg.get("symbols") if isinstance(cfg.get("symbols"), list) else []
    first_symbol = str(symbols[0]).upper() if symbols else "unknown"
    candles_source = str(((cfg.get("bybit") or {}).get("ws_public_host") or "unknown")).strip() or "unknown"
    active_profile = str(manifest.get("active_config_profile") or "unknown")
    active_futures_model = str(manifest.get("active_futures_model_version") or "unknown")
    training_engine_version = str(manifest.get("futures_training_engine_version") or "unknown")
    timeframe_hint = str(((cfg.get("strategy") or {}).get("scanner_interval_sec") or "")).strip()
    timeframe = f"{timeframe_hint}s" if timeframe_hint else "not available"

    runtime_status = "idle"
    state = str(ml_process_state or "").strip().lower()
    if ml_running and ml_paused:
        runtime_status = "paused"
    elif ml_running:
        runtime_status = "running"
    elif state == "error":
        runtime_status = "failed"
    elif state == "stopped":
        runtime_status = "idle"
    elif state:
        runtime_status = state

    out: dict[str, Any] = {
        "training_runtime_status": runtime_status,
        "active_symbol": first_symbol,
        "active_timeframe": timeframe,
        "active_dataset_range": "not available",
        "candles_source": candles_source,
        "dataset_prepared": "no",
        "dataset_rows": 0,
        "dataset_windows_count": 0,
        "candidate_events_count": 0,
        "outcomes_count": 0,
        "features_prepared": "no",
        "labels_prepared": "no",
        "active_recipe": f"runtime={str(((cfg.get('strategy') or {}).get('runtime_strategy') or 'unknown'))}; ml={training_mode}",
        "pipeline_last_prepared_at": "-",
        "pipeline_last_failure": "not available",
        "run_epoch": "not available",
        "run_step": "not available",
        "run_status": runtime_status,
        "run_started_at": "-",
        "run_updated_at": "-",
        "run_duration": "not available",
        "train_loss": "not available",
        "val_loss": "not available",
        "best_checkpoint": "not available",
        "latest_checkpoint": "not available",
        "active_futures_model_version": active_futures_model,
        "training_engine_version": training_engine_version,
        "evaluation_summary": "not available",
        "best_metric": "not available",
        "last_evaluation_ts": "-",
        "last_completed_run": "-",
        "last_error": "not available",
        "checkpoints_rows": [],
        "actions": [
            "Refresh",
            "Prepare Dataset",
            "Build Features / Labels",
            "Start Training",
            "Pause Training",
            "Run Evaluation",
            "Open Checkpoints",
            "Open Logs",
        ],
    }
    if not db_path.exists():
        return out

    conn = sqlite3.connect(str(db_path))
    try:
        latest_signal_symbol = ""
        ts_min = 0
        ts_max = 0
        if _table_exists_local(conn, "signals"):
            sig_row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    MIN(COALESCE(ts_signal_ms, 0)),
                    MAX(COALESCE(ts_signal_ms, 0))
                FROM signals
                """
            ).fetchone()
            if sig_row:
                signals_count = int(sig_row[0] or 0)
                ts_min = int(sig_row[1] or 0)
                ts_max = int(sig_row[2] or 0)
                out["dataset_rows"] = signals_count
                out["dataset_windows_count"] = signals_count
                out["candidate_events_count"] = signals_count
                if signals_count > 0:
                    out["dataset_prepared"] = "yes"
                    out["features_prepared"] = "yes"
            latest_signal = conn.execute(
                """
                SELECT COALESCE(symbol, ''), COALESCE(created_at_utc, '')
                FROM signals
                ORDER BY COALESCE(ts_signal_ms, 0) DESC
                LIMIT 1
                """
            ).fetchone()
            if latest_signal:
                latest_signal_symbol = str(latest_signal[0] or "").strip().upper()
                if latest_signal_symbol:
                    out["active_symbol"] = latest_signal_symbol
                out["pipeline_last_prepared_at"] = str(latest_signal[1] or "-")

        if ts_min > 0 and ts_max > 0:
            out["active_dataset_range"] = f"{_fmt_workspace_ts_from_ms(ts_min)} -> {_fmt_workspace_ts_from_ms(ts_max)}"

        if _table_exists_local(conn, "outcomes"):
            outcomes_row = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(closed_at_utc), '') FROM outcomes"
            ).fetchone()
            outcomes_count = int(outcomes_row[0] or 0) if outcomes_row else 0
            out["outcomes_count"] = outcomes_count
            if outcomes_count > 0:
                out["labels_prepared"] = "yes"
                out["last_completed_run"] = str((outcomes_row[1] if outcomes_row else "") or "-")

        checkpoints: list[dict[str, Any]] = []
        best_checkpoint_id = "not available"
        best_metric_name = "quality_score"
        best_metric_value = float("-inf")
        latest_checkpoint_id = "not available"
        latest_checkpoint_ts = "-"
        if _table_exists_local(conn, "model_registry"):
            rows = conn.execute(
                """
                SELECT
                    COALESCE(model_id, ''),
                    COALESCE(created_at_utc, ''),
                    COALESCE(is_active, 0),
                    COALESCE(metrics_json, ''),
                    COALESCE(path_or_payload, '')
                FROM model_registry
                ORDER BY created_at_utc DESC, id DESC
                LIMIT 200
                """
            ).fetchall()
            if rows:
                latest_checkpoint_id = str(rows[0][0] or "not available")
                latest_checkpoint_ts = str(rows[0][1] or "-")
            for model_id, created_at, is_active, metrics_json, path in rows:
                metrics = _safe_metrics_json(metrics_json)
                quality = float(metrics.get("quality_score", metrics.get("open_accuracy", -9999.0)) or -9999.0)
                train_loss_text = _metric_or_unknown(metrics, "training_loss", precision=6)
                val_loss_text = _metric_or_unknown(metrics, "val_loss", precision=6)
                open_acc_text = _metric_or_unknown(metrics, "open_accuracy", precision=6)
                checkpoints.append(
                    {
                        "model_id": str(model_id or ""),
                        "created_at": str(created_at or "-"),
                        "is_active": bool(int(is_active or 0)),
                        "quality_score": quality,
                        "open_accuracy": open_acc_text,
                        "train_loss": train_loss_text,
                        "val_loss": val_loss_text,
                        "path": str(path or ""),
                        "metrics": metrics,
                    }
                )
                if quality > best_metric_value:
                    best_metric_value = quality
                    best_checkpoint_id = str(model_id or "not available")

        out["latest_checkpoint"] = latest_checkpoint_id
        out["best_checkpoint"] = best_checkpoint_id
        out["checkpoints_rows"] = [
            (
                str(idx),
                str(item.get("model_id") or ""),
                str(item.get("created_at") or "-"),
                "yes" if bool(item.get("is_active")) else "no",
                (
                    "not available"
                    if float(item.get("quality_score", -9999.0)) <= -9999.0
                    else f"{float(item.get('quality_score')):.4f}"
                ),
                str(item.get("open_accuracy") or "not available"),
                str(item.get("train_loss") or "not available"),
                str(item.get("val_loss") or "not available"),
                str(item.get("path") or ""),
            )
            for idx, item in enumerate(checkpoints, start=1)
        ]

        active_checkpoint = next((cp for cp in checkpoints if bool(cp.get("is_active"))), None)
        active_metrics = dict(active_checkpoint.get("metrics") or {}) if active_checkpoint else {}
        if active_metrics:
            out["train_loss"] = _metric_or_unknown(active_metrics, "training_loss", precision=6)
            out["val_loss"] = _metric_or_unknown(active_metrics, "val_loss", precision=6)
            open_acc = _metric_or_unknown(active_metrics, "open_accuracy", precision=4)
            edge_mae = _metric_or_unknown(active_metrics, "edge_mae", precision=4)
            out["evaluation_summary"] = f"open_accuracy={open_acc} | edge_mae={edge_mae}"
            out["best_metric"] = (
                _metric_or_unknown(active_metrics, "quality_score", precision=6)
                if "quality_score" in active_metrics
                else _metric_or_unknown(active_metrics, "open_accuracy", precision=6)
            )

        if _table_exists_local(conn, "model_stats"):
            m_row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(MAX(ts_ms), 0)
                FROM model_stats
                """
            ).fetchone()
            if m_row:
                stats_count = int(m_row[0] or 0)
                max_ts = int(m_row[1] or 0)
                if stats_count > 0:
                    out["run_step"] = str(stats_count)
                    out["run_updated_at"] = _fmt_workspace_ts_from_ms(max_ts)
                    out["last_evaluation_ts"] = _fmt_workspace_ts_from_ms(max_ts)
            r_row = conn.execute(
                """
                SELECT COALESCE(MIN(ts_ms), 0), COALESCE(MAX(ts_ms), 0)
                FROM model_stats
                """
            ).fetchone()
            if r_row:
                min_ts = int(r_row[0] or 0)
                max_ts = int(r_row[1] or 0)
                if min_ts > 0:
                    out["run_started_at"] = _fmt_workspace_ts_from_ms(min_ts)
                if min_ts > 0 and max_ts >= min_ts:
                    duration_sec = max((max_ts - min_ts) // 1000, 0)
                    out["run_duration"] = f"{duration_sec}s"

        out["last_error"] = "not available" if runtime_status not in {"failed"} else "training_runtime_failed"
        if runtime_status == "running":
            out["run_status"] = "running"
        elif runtime_status == "paused":
            out["run_status"] = "paused"
        elif runtime_status == "failed":
            out["run_status"] = "failed"
        elif out["last_completed_run"] != "-":
            out["run_status"] = "completed"
        else:
            out["run_status"] = "idle"
    except sqlite3.Error:
        return out
    finally:
        conn.close()
    return out


def load_futures_paper_workspace_read_model(
    db_path: Path,
    *,
    release_manifest: dict[str, Any] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    manifest = release_manifest or {}
    active_futures_model = str(manifest.get("active_futures_model_version") or "unknown")
    out: dict[str, Any] = {
        "session_status": "read_only",
        "capability_status": "close_controls_unsupported",
        "positions_count": 0,
        "open_orders_count": 0,
        "closed_results_count": 0,
        "good_results_count": 0,
        "bad_results_count": 0,
        "flat_results_count": 0,
        "net_pnl_total": 0.0,
        "last_closed_at": "-",
        "active_futures_model_version": active_futures_model,
        "summary_line": (
            "paper_session=read_only | positions=0 | pending_orders=0 | "
            "closed_results=0 | net_pnl=0.000000 | active_model={model}"
        ).format(model=active_futures_model),
        "status_line": (
            "good=0 | bad=0 | flat=0 | close_controls=unsupported | reset_session=unsupported"
        ),
        "positions_rows": [],
        "open_orders_rows": [],
        "closed_results_rows": [],
        "actions": [
            "Refresh",
            "Close Selected Paper Position",
            "Close All Paper Positions",
            "Reset Paper Session",
            "Open Futures Logs",
            "Open Model Registry",
        ],
    }
    if not db_path.exists():
        return out

    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists_local(conn, "futures_positions"):
            positions = list_futures_positions(conn, account_type="UNIFIED")
            out["positions_count"] = len(positions)
            out["positions_rows"] = [
                (
                    str(idx),
                    str(item.get("symbol") or ""),
                    str(item.get("side") or ""),
                    _fmt_workspace_float(item.get("qty"), precision=8, fallback="0"),
                    _fmt_workspace_float(item.get("entry_price"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("mark_price"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("liq_price"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("unrealized_pnl"), precision=6, fallback=""),
                    _fmt_workspace_float(item.get("take_profit"), precision=8, fallback=""),
                    _fmt_workspace_float(item.get("stop_loss"), precision=8, fallback=""),
                    str(item.get("protection_status") or "unknown"),
                )
                for idx, item in enumerate(positions[: max(int(limit), 1)], start=1)
            ]

        if _table_exists_local(conn, "futures_open_orders"):
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
                ORDER BY COALESCE(updated_at_utc, created_at_utc) DESC, id DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            out["open_orders_count"] = len(rows)
            out["open_orders_rows"] = [
                (
                    str(idx),
                    str(symbol or ""),
                    str(side or ""),
                    str(order_id or ""),
                    str(order_link_id or ""),
                    str(order_type or ""),
                    _fmt_workspace_float(price, precision=8, fallback=""),
                    _fmt_workspace_float(qty, precision=8, fallback=""),
                    str(status or ""),
                )
                for idx, (symbol, side, order_id, order_link_id, order_type, price, qty, status) in enumerate(
                    rows, start=1
                )
            ]

        if _table_exists_local(conn, "outcomes"):
            closed_rows = conn.execute(
                """
                SELECT
                    COALESCE(o.symbol, ''),
                    COALESCE(s.side, ''),
                    o.entry_vwap,
                    o.exit_vwap,
                    o.net_pnl_quote,
                    COALESCE(s.active_model_id, s.model_id, ''),
                    COALESCE(s.policy_used, ''),
                    COALESCE(s.created_at_utc, ''),
                    COALESCE(o.closed_at_utc, '')
                FROM outcomes o
                LEFT JOIN signals s ON s.signal_id = o.signal_id
                ORDER BY COALESCE(o.closed_at_utc, '') DESC, COALESCE(o.signal_id, '') DESC
                LIMIT ?
                """,
                (max(int(limit), 1),),
            ).fetchall()
            if closed_rows:
                out["last_closed_at"] = str(closed_rows[0][8] or "-")
            closed_result_rows: list[tuple[str, ...]] = []
            good = 0
            bad = 0
            flat = 0
            net_total = 0.0
            for idx, (symbol, side, entry_vwap, exit_vwap, net_pnl_quote, model_source, policy_used, opened_at, closed_at) in enumerate(
                closed_rows,
                start=1,
            ):
                net_pnl_value = float(net_pnl_quote or 0.0)
                net_total += net_pnl_value
                if net_pnl_value > 0:
                    result_class = "good"
                    good += 1
                elif net_pnl_value < 0:
                    result_class = "bad"
                    bad += 1
                else:
                    result_class = "flat"
                    flat += 1
                closed_result_rows.append(
                    (
                        str(idx),
                        str(symbol or ""),
                        str(side or "unknown"),
                        _fmt_workspace_float(entry_vwap, precision=8, fallback=""),
                        _fmt_workspace_float(exit_vwap, precision=8, fallback=""),
                        f"{net_pnl_value:.6f}",
                        result_class,
                        _component_text(model_source, fallback="unknown"),
                        str(policy_used or "unknown"),
                        str(opened_at or "-"),
                        str(closed_at or "-"),
                    )
                )
            out["closed_results_rows"] = closed_result_rows
            out["closed_results_count"] = len(closed_result_rows)
            out["good_results_count"] = good
            out["bad_results_count"] = bad
            out["flat_results_count"] = flat
            out["net_pnl_total"] = net_total
    except sqlite3.Error:
        return out
    finally:
        conn.close()

    out["summary_line"] = (
        "paper_session={status} | positions={positions} | pending_orders={orders} | "
        "closed_results={closed} | net_pnl={net_pnl:.6f} | active_model={model}"
    ).format(
        status=str(out.get("session_status") or "read_only"),
        positions=int(out.get("positions_count") or 0),
        orders=int(out.get("open_orders_count") or 0),
        closed=int(out.get("closed_results_count") or 0),
        net_pnl=float(out.get("net_pnl_total") or 0.0),
        model=str(out.get("active_futures_model_version") or "unknown"),
    )
    out["status_line"] = (
        "good={good} | bad={bad} | flat={flat} | last_closed={last_closed} | "
        "close_controls=unsupported | reset_session=unsupported"
    ).format(
        good=int(out.get("good_results_count") or 0),
        bad=int(out.get("bad_results_count") or 0),
        flat=int(out.get("flat_results_count") or 0),
        last_closed=str(out.get("last_closed_at") or "-"),
    )
    return out


def _dashboard_policy_mode_label(strategy_cfg: dict[str, Any] | None, ml_mode: str) -> str:
    payload = strategy_cfg or {}
    bandit_enabled = bool(payload.get("bandit_enabled", True))
    mode = str(ml_mode or "bootstrap").strip().lower()
    model_enabled = mode in {"predict", "online"}
    if model_enabled and bandit_enabled:
        return "Hybrid"
    if model_enabled:
        return "Model-driven"
    if not bandit_enabled:
        return "Hard Rules"
    return "Hybrid"


def _dashboard_training_source_label(exec_mode: str, ml_mode: str) -> str:
    exec_mode_norm = str(exec_mode or "paper").strip().lower()
    ml_mode_norm = str(ml_mode or "bootstrap").strip().lower()
    if ml_mode_norm == "bootstrap":
        return "Training disabled"
    if exec_mode_norm in {"paper", "paper_only"}:
        return "Paper only"
    if exec_mode_norm in {"live", "demo", "real"}:
        return "Paper + Executed"
    return f"ml:{ml_mode_norm}"


def build_dashboard_home_instrument_sections(
    *,
    raw_cfg: dict[str, Any] | None,
    release_manifest: dict[str, Any] | None,
    spot_workspace: dict[str, Any] | None,
    futures_training_workspace: dict[str, Any] | None,
    futures_paper_workspace: dict[str, Any] | None,
    exec_mode: str,
) -> dict[str, str]:
    cfg = raw_cfg or {}
    release = release_manifest or {}
    spot = spot_workspace or {}
    futures_training = futures_training_workspace or {}
    futures_paper = futures_paper_workspace or {}
    strategy_cfg = cfg.get("strategy") or {}
    ml_cfg = cfg.get("ml") or {}
    ml_mode = str(ml_cfg.get("mode") or "bootstrap").strip().lower() or "bootstrap"
    policy_mode = _dashboard_policy_mode_label(strategy_cfg, ml_mode)
    training_source = _dashboard_training_source_label(exec_mode, ml_mode)
    max_position_size = _component_text(
        strategy_cfg.get("max_order_notional_usdt") or strategy_cfg.get("order_notional_quote"),
        fallback="unknown",
    )
    tp = _component_text(strategy_cfg.get("take_profit_pct"), fallback="unknown")
    sl = _component_text(strategy_cfg.get("stop_loss_pct"), fallback="unknown")
    dust_threshold = _component_text(strategy_cfg.get("min_active_position_usdt"), fallback="unknown")

    spot_primary_line = (
        "active_holdings={holdings} | open_orders={orders} | recovered={recovered} | "
        "stale={stale} | current_mode={mode} | active_model={model}"
    ).format(
        holdings=int(spot.get("holdings_count") or 0),
        orders=int(spot.get("open_orders_count") or 0),
        recovered=int(spot.get("recovered_holdings_count") or 0),
        stale=int(spot.get("stale_holdings_count") or 0),
        mode=str(exec_mode or "paper"),
        model=str(release.get("active_spot_model_version") or "unknown"),
    )
    spot_meta_line = (
        "runtime={runtime} | policy={policy} | holdings_total={total} | "
        "protected_manual={manual} | dust_threshold={dust}"
    ).format(
        runtime=str(release.get("spot_runtime_version") or "unknown"),
        policy=policy_mode,
        total=int(spot.get("holdings_count") or 0),
        manual=int(spot.get("manual_holdings_count") or 0),
        dust=dust_threshold,
    )
    spot_settings_line = (
        "TP={tp} | SL={sl} | max_position_size={max_pos} | hard_rules={hard_rules} | "
        "training_source={training_source} | dust_threshold={dust}"
    ).format(
        tp=tp,
        sl=sl,
        max_pos=max_position_size,
        hard_rules=("on" if policy_mode == "Hard Rules" else "off"),
        training_source=training_source,
        dust=dust_threshold,
    )

    futures_primary_line = (
        "training_status={status} | paper_results={closed} | good={good} bad={bad} | "
        "active_model={model} | mode=research-only"
    ).format(
        status=str(futures_training.get("training_runtime_status") or "unknown"),
        closed=int(futures_paper.get("closed_results_count") or 0),
        good=int(futures_paper.get("good_results_count") or 0),
        bad=int(futures_paper.get("bad_results_count") or 0),
        model=str(release.get("active_futures_model_version") or "unknown"),
    )
    futures_meta_line = (
        "paper_positions={positions} | pending_orders={orders} | net_pnl={net_pnl:.6f} | "
        "engine={engine} | best_checkpoint={checkpoint}"
    ).format(
        positions=int(futures_paper.get("positions_count") or 0),
        orders=int(futures_paper.get("open_orders_count") or 0),
        net_pnl=float(futures_paper.get("net_pnl_total") or 0.0),
        engine=str(release.get("futures_training_engine_version") or "unknown"),
        checkpoint=str(futures_training.get("best_checkpoint") or "not available"),
    )
    futures_settings_line = (
        "TP={tp} | SL={sl} | max_position_size={max_pos} | hard_rules={hard_rules} | training_source={training_source}"
    ).format(
        tp=tp,
        sl=sl,
        max_pos=max_position_size,
        hard_rules=("on" if policy_mode == "Hard Rules" else "off"),
        training_source=training_source,
    )

    return {
        "spot_primary_line": spot_primary_line,
        "spot_meta_line": spot_meta_line,
        "spot_settings_line": spot_settings_line,
        "futures_primary_line": futures_primary_line,
        "futures_meta_line": futures_meta_line,
        "futures_settings_line": futures_settings_line,
    }


def build_dashboard_settings_workspace_sections(
    *,
    launcher_mode: str,
    packaged_executable: str | None,
    python_path: str | None,
    config_path: str | None,
    raw_cfg: dict[str, Any] | None,
    env_data: dict[str, str] | None,
    release_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = raw_cfg or {}
    env_map = env_data or {}
    release = release_manifest or {}
    execution_cfg = cfg.get("execution") or {}
    bybit_cfg = cfg.get("bybit") or {}
    launcher = str(launcher_mode or "").strip().lower() or "source"
    runtime_name = (
        Path(str(packaged_executable or sys.executable)).name
        if launcher == "packaged"
        else Path(str(python_path or sys.executable)).name
    ) or ("botik.exe" if launcher == "packaged" else "python")
    config_name = Path(str(config_path or DEFAULT_CONFIG_PATH)).name or "config.yaml"
    execution_mode = _component_text(execution_cfg.get("mode"), fallback="paper")
    start_paused = "yes" if bool(cfg.get("start_paused", True)) else "no"
    bybit_host = _component_text(bybit_cfg.get("host"), fallback="unknown")
    ws_host = _component_text(bybit_cfg.get("ws_public_host"), fallback="unknown")
    shell_version = _component_text(release.get("shell_version"), fallback="unknown")
    shell_build = _component_text(release.get("shell_build_sha"), fallback="unknown")
    profile_name = _component_text(
        release.get("active_config_profile") or Path(str(config_path or DEFAULT_CONFIG_PATH)).name,
        fallback="unknown",
    )

    def _secret_status(key: str) -> str:
        return "configured" if str(env_map.get(key) or "").strip() else "missing"

    return {
        "diagnostics_line": (
            f"launcher={launcher} | runtime={runtime_name} | config={config_name} | "
            f"shell={shell_version} | build={shell_build}"
        ),
        "profile_line": (
            f"execution.mode={execution_mode} | start_paused={start_paused} | "
            f"bybit.host={bybit_host} | ws_public_host={ws_host} | profile={profile_name}"
        ),
        "paths_line": (
            f".env={ENV_PATH.name} | config={config_name} | release_manifest={DASHBOARD_RELEASE_MANIFEST_PATH.name} | "
            f"workspace_manifest={DASHBOARD_WORKSPACE_MANIFEST_PATH.name} | active_models={ACTIVE_MODELS_MANIFEST_PATH.name} | "
            f"gui_log={GUI_LOG_PATH.name}"
        ),
        "secrets_line": (
            f"telegram_token={_secret_status('TELEGRAM_BOT_TOKEN')} | "
            f"bybit_api_key={_secret_status('BYBIT_API_KEY')} | "
            f"bybit_api_secret={_secret_status('BYBIT_API_SECRET_KEY')} | "
            f"rsa_key_path={_secret_status('BYBIT_RSA_PRIVATE_KEY_PATH')}"
        ),
        "notice_line": (
            "Instrument policy and trading knobs live in Dashboard Home, Spot Workspace and Futures Workspace, "
            "not in Settings Workspace."
        ),
        "editable_fields": [
            "execution.mode",
            "start_paused",
            "bybit.host",
            "ws_public_host",
        ],
    }


def dashboard_subprocess_popen_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        startupinfo = startupinfo_cls() if callable(startupinfo_cls) else None
        if startupinfo is not None:
            startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0))
            startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
            kwargs["startupinfo"] = startupinfo
        if creationflags:
            kwargs["creationflags"] = creationflags
    return kwargs


def dashboard_subprocess_run_kwargs() -> dict[str, Any]:
    kwargs = dashboard_subprocess_popen_kwargs()
    kwargs.pop("stdin", None)
    return kwargs


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
        self.state = "starting"
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **dashboard_subprocess_popen_kwargs(),
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
        self.state = "stopping"
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
    Keeps Windows system awake while Dashboard Shell is running.
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
        self.root.title(f"Botik Dashboard {self.app_version}")
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
        self.launcher_mode = detect_launcher_mode()
        self.packaged_executable = str(Path(sys.executable)) if self.launcher_mode == "packaged" else ""

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
        self.dashboard_spot_status_var = tk.StringVar(value="Spot: n/a")
        self.dashboard_futures_status_var = tk.StringVar(value="Futures: n/a")
        self.dashboard_telegram_status_var = tk.StringVar(value="Telegram: n/a")
        self.dashboard_ops_status_var = tk.StringVar(value="Ops: n/a")
        self.dashboard_release_panel_var = tk.StringVar(value="Loaded Components / Releases: not loaded")
        self.dashboard_release_status_var = tk.StringVar(value="release=missing")
        self.dashboard_release_shell_var = tk.StringVar(value="Dashboard Shell: unknown")
        self.dashboard_release_components_var = tk.StringVar(value="workspace_pack=unknown")
        self.dashboard_release_models_var = tk.StringVar(value="spot_model=unknown | futures_model=unknown")
        self.dashboard_release_manifests_var = tk.StringVar(value="release=dashboard_release_manifest.yaml")
        self.dashboard_balance_summary_var = tk.StringVar(value="Balance: n/a")
        self.dashboard_pnl_summary_var = tk.StringVar(value="Day PnL: n/a")
        self.dashboard_profile_summary_var = tk.StringVar(value="Profile: unknown")
        self.dashboard_spot_primary_var = tk.StringVar(value="Spot primary: n/a")
        self.dashboard_spot_meta_var = tk.StringVar(value="Spot meta: n/a")
        self.dashboard_spot_settings_var = tk.StringVar(value="Spot settings: n/a")
        self.dashboard_futures_primary_var = tk.StringVar(value="Futures primary: n/a")
        self.dashboard_futures_meta_var = tk.StringVar(value="Futures meta: n/a")
        self.dashboard_futures_settings_var = tk.StringVar(value="Futures settings: n/a")
        self.models_status_var = tk.StringVar(value="selector=active_models.yaml")
        self.spot_workspace_summary_var = tk.StringVar(value="Spot Summary: n/a")
        self.spot_workspace_policy_var = tk.StringVar(value="Policy: n/a")
        self.futures_training_summary_var = tk.StringVar(value="Training Summary: n/a")
        self.futures_dataset_summary_var = tk.StringVar(value="Dataset/Candles: n/a")
        self.futures_pipeline_summary_var = tk.StringVar(value="Features/Labels Pipeline: n/a")
        self.futures_run_progress_var = tk.StringVar(value="Training Run Progress: n/a")
        self.futures_eval_summary_var = tk.StringVar(value="Evaluation Summary: n/a")
        self.futures_checkpoints_summary_var = tk.StringVar(value="Checkpoints: n/a")
        self.futures_paper_summary_var = tk.StringVar(value="Paper Results: n/a")
        self.futures_paper_status_var = tk.StringVar(value="Paper Status: n/a")
        self.telegram_workspace_summary_var = tk.StringVar(value="Telegram Status Summary: n/a")
        self.telegram_workspace_profile_var = tk.StringVar(value="Bot Profile / Connection: n/a")
        self.telegram_workspace_access_var = tk.StringVar(value="Allowed Chats / Access: n/a")
        self.telegram_workspace_commands_var = tk.StringVar(value="Available Commands: n/a")
        self.telegram_workspace_health_var = tk.StringVar(value="Telegram Errors / Health: n/a")
        self.telegram_workspace_capabilities_var = tk.StringVar(value="Capabilities: n/a")
        self.ml_model_id_var = tk.StringVar(value="bootstrap")
        self.ml_training_state_var = tk.StringVar(value="idle")
        self.ml_progress_text_var = tk.StringVar(value="0%")
        self.ml_net_edge_var = tk.StringVar(value="n/a")
        self.ml_win_rate_var = tk.StringVar(value="n/a")
        self.ml_fill_rate_var = tk.StringVar(value="n/a")
        self.ml_fill_details_var = tk.StringVar(value="0/0 signals")
        self.ml_metrics_compact_var = tk.StringVar(value="edge=n/a | win=n/a | fill=n/a")
        self.ml_progress: ttk.Progressbar | None = None
        self.ml_progress_label: ttk.Label | None = None
        self.ml_chart_canvas: tk.Canvas | None = None
        self.stats_orders_total_var = tk.StringVar(value="0")
        self.stats_outcomes_total_var = tk.StringVar(value="0")
        self.stats_positive_var = tk.StringVar(value="0")
        self.stats_negative_var = tk.StringVar(value="0")
        self.stats_neutral_var = tk.StringVar(value="0")
        self.stats_net_pnl_var = tk.StringVar(value="0.000000")
        self.stats_avg_pnl_var = tk.StringVar(value="0.000000")
        self.stats_balance_events_var = tk.StringVar(value="0")
        self.stats_balance_delta_var = tk.StringVar(value="0.000000")
        self.ops_service_health_var = tk.StringVar(value="services: n/a")
        self.ops_reconciliation_var = tk.StringVar(value="reconciliation: n/a")
        self.ops_protection_var = tk.StringVar(value="protection: n/a")
        self.ops_db_health_var = tk.StringVar(value="db: n/a")
        self.ops_capabilities_var = tk.StringVar(value="capabilities: n/a")
        self.models_summary_var = tk.StringVar(value="models=0")
        self.settings_diagnostics_var = tk.StringVar(value="launcher=unknown | runtime=unknown | config=unknown")
        self.settings_profile_var = tk.StringVar(value="execution.mode=unknown | start_paused=yes")
        self.settings_paths_var = tk.StringVar(
            value=".env=.env | config=config.yaml | release_manifest=dashboard_release_manifest.yaml"
        )
        self.settings_secrets_var = tk.StringVar(value="telegram_token=missing | bybit_api_key=missing")
        self.settings_notice_var = tk.StringVar(
            value="Instrument policy and trading knobs live in Dashboard Home, Spot Workspace and Futures Workspace."
        )
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
        self.ops_domain_notebook: ttk.Notebook | None = None
        self.ops_issues_frame: ttk.Frame | None = None
        self.ops_futures_positions_frame: ttk.Frame | None = None
        self.models_tree: ttk.Treeview | None = None
        self.order_history_tree: ttk.Treeview | None = None
        self.spot_workspace_holdings_tree: ttk.Treeview | None = None
        self.spot_workspace_orders_tree: ttk.Treeview | None = None
        self.spot_workspace_fills_tree: ttk.Treeview | None = None
        self.spot_workspace_exit_tree: ttk.Treeview | None = None
        self.futures_training_checkpoints_tree: ttk.Treeview | None = None
        self.futures_paper_positions_tree: ttk.Treeview | None = None
        self.futures_paper_orders_tree: ttk.Treeview | None = None
        self.futures_paper_closed_tree: ttk.Treeview | None = None
        self.log_text_full: tk.Text | None = None
        self.telegram_workspace_text: tk.Text | None = None
        self.telegram_workspace_commands_tree: ttk.Treeview | None = None
        self.telegram_workspace_alerts_tree: ttk.Treeview | None = None
        self.telegram_workspace_errors_tree: ttk.Treeview | None = None
        self.log_channel_filter_combo: ttk.Combobox | None = None
        self.log_instrument_filter_combo: ttk.Combobox | None = None
        self.log_level_filter_combo: ttk.Combobox | None = None
        self.log_pair_filter_combo: ttk.Combobox | None = None
        self.log_jump_main: ttk.Button | None = None
        self.log_jump_full: ttk.Button | None = None
        self.log_scroll_main: ttk.Scrollbar | None = None
        self.log_scroll_full: ttk.Scrollbar | None = None
        self.log_filter_channel_var = tk.StringVar(value="ALL")
        self.log_filter_instrument_var = tk.StringVar(value="ALL")
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
        self.futures_notebook: ttk.Notebook | None = None
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
        self._service_actions_inflight: set[str] = set()
        self._telegram_recent_commands: deque[dict[str, str]] = deque(maxlen=80)
        self._telegram_recent_alerts: deque[dict[str, str]] = deque(maxlen=80)
        self._telegram_recent_errors: deque[dict[str, str]] = deque(maxlen=80)
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
        if self.launcher_mode == "packaged":
            py_name = Path(self.packaged_executable or sys.executable).name or "botik.exe"
        else:
            py_name = Path(self.python_var.get()).name or "python"
        cfg_name = Path(self.config_var.get()).name or "config.yaml"
        self.runtime_python_name_var.set(py_name)
        self.runtime_config_name_var.set(cfg_name)
        self._refresh_settings_workspace_summary()

    def _refresh_settings_workspace_summary(
        self,
        *,
        raw_cfg: dict[str, Any] | None = None,
        env_data: dict[str, str] | None = None,
    ) -> None:
        try:
            cfg = raw_cfg if raw_cfg is not None else self._load_yaml()
        except Exception:
            cfg = {}
        try:
            env_map = env_data if env_data is not None else _read_env_map(ENV_PATH)
        except Exception:
            env_map = {}
        sections = build_dashboard_settings_workspace_sections(
            launcher_mode=self.launcher_mode,
            packaged_executable=self.packaged_executable,
            python_path=self.python_var.get(),
            config_path=self.config_var.get(),
            raw_cfg=cfg,
            env_data=env_map,
            release_manifest=load_dashboard_release_manifest(),
        )
        self.settings_diagnostics_var.set(str(sections.get("diagnostics_line") or "launcher=unknown"))
        self.settings_profile_var.set(str(sections.get("profile_line") or "execution.mode=unknown"))
        self.settings_paths_var.set(str(sections.get("paths_line") or ".env=.env"))
        self.settings_secrets_var.set(str(sections.get("secrets_line") or "telegram_token=missing"))
        self.settings_notice_var.set(str(sections.get("notice_line") or "Instrument controls live elsewhere."))

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
            text=f"Botik Dashboard Shell {self.app_version}",
            style="Title.TLabel",
        )
        self.title_label.pack(anchor=tk.W)
        ttk.Label(
            root_frame,
            text="Single-window Dashboard Shell for runtime, workspaces and operations.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        notebook = ttk.Notebook(root_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook = notebook

        self.home_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.control_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.futures_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.futures_training_tab = ttk.Frame(self.futures_tab, style="Root.TFrame")
        self.futures_paper_tab = ttk.Frame(self.futures_tab, style="Root.TFrame")
        self.model_registry_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.telegram_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.logs_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.settings_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.statistics_tab = ttk.Frame(notebook, style="Root.TFrame")

        settings_shell = ttk.Frame(self.settings_tab, style="Root.TFrame")
        settings_shell.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.settings_notebook = ttk.Notebook(settings_shell)
        self.settings_notebook.pack(fill=tk.BOTH, expand=True)
        self.settings_main_tab = ttk.Frame(self.settings_notebook, style="Root.TFrame")
        self.settings_notebook.add(self.settings_main_tab, text="Technical Settings")

        statistics_shell = ttk.Frame(self.statistics_tab, style="Root.TFrame")
        statistics_shell.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.statistics_notebook = ttk.Notebook(statistics_shell)
        self.statistics_notebook.pack(fill=tk.BOTH, expand=True)
        self.stats_tab = ttk.Frame(self.statistics_notebook, style="Root.TFrame")
        self.statistics_notebook.add(self.stats_tab, text="Ops Snapshot")
        self.models_tab = self.model_registry_tab

        self._build_dashboard_home_tab()
        self._build_control_tab()
        self._build_futures_workspace_tab()
        self._build_telegram_workspace_tab()
        self._build_logs_tab()
        self._build_settings_tab()
        self._build_stats_tab()
        self._build_models_tab()
        self.dashboard_workspace_manifest = load_dashboard_workspace_manifest()
        self._apply_workspace_manifest_to_notebook(self.dashboard_workspace_manifest)
        self._attach_context_menu_to_entries(self.root)

    def _workspace_frame_map(self) -> dict[str, ttk.Frame]:
        return {
            "home": self.home_tab,
            "spot": self.control_tab,
            "futures": self.futures_tab,
            "model_registry": self.model_registry_tab,
            "telegram": self.telegram_tab,
            "logs": self.logs_tab,
            "ops": self.statistics_tab,
            "settings": self.settings_tab,
        }

    def _apply_workspace_manifest_to_notebook(self, manifest: dict[str, Any] | None) -> None:
        if self.notebook is None:
            return
        try:
            for tab_id in list(self.notebook.tabs()):
                self.notebook.forget(tab_id)
        except Exception:
            pass
        frame_map = self._workspace_frame_map()
        for key, label in resolve_dashboard_workspace_tabs(manifest):
            frame = frame_map.get(key)
            if frame is None:
                continue
            self.notebook.add(frame, text=label)

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

    def _open_workspace(self, workspace: ttk.Frame | None) -> None:
        if self.notebook is None or workspace is None:
            return
        if workspace in {self.futures_training_tab, self.futures_paper_tab} and self.futures_tab is not None:
            try:
                self.notebook.select(self.futures_tab)
                if self.futures_notebook is not None:
                    self.futures_notebook.select(workspace)
                return
            except Exception:
                return
        if workspace is self.settings_main_tab and self.settings_tab is not None:
            try:
                self.notebook.select(self.settings_tab)
                if self.settings_notebook is not None:
                    self.settings_notebook.select(workspace)
                return
            except Exception:
                return
        try:
            self.notebook.select(workspace)
        except Exception:
            return

    def _build_dashboard_home_tab(self) -> None:
        home_root = ttk.Frame(self.home_tab, style="Root.TFrame")
        home_root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        hero = ttk.Frame(home_root, style="Card.TFrame", padding=16)
        hero.pack(fill=tk.X)
        ttk.Label(hero, text="Dashboard Home", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            hero,
            text="Single-window Dashboard Shell for Spot, Futures, models and operations. No visible console windows.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Button(hero, text="Open Full Stats", command=lambda: self._open_workspace(self.statistics_tab)).grid(
            row=0, column=1, rowspan=2, sticky=tk.E, padx=(12, 0)
        )
        hero.columnconfigure(0, weight=1)

        metrics = ttk.Frame(home_root, style="Root.TFrame")
        metrics.pack(fill=tk.X, pady=(8, 0))
        for idx, (title, value_var) in enumerate(
            [
                ("Total Balance", self.dashboard_balance_summary_var),
                ("Day PnL", self.dashboard_pnl_summary_var),
                ("Active Profile", self.dashboard_profile_summary_var),
                ("Shell / Ops", self.dashboard_ops_status_var),
            ]
        ):
            card_frame = ttk.Frame(metrics, style="CardAlt.TFrame", padding=12)
            card_frame.grid(row=0, column=idx, sticky=tk.NSEW, padx=(0 if idx == 0 else 8, 0))
            ttk.Label(card_frame, text=title, style="SectionAlt.TLabel").pack(anchor=tk.W)
            ttk.Label(
                card_frame,
                textvariable=value_var,
                style="MetricValue.TLabel",
                justify=tk.LEFT,
                wraplength=220,
            ).pack(anchor=tk.W, pady=(8, 0))
            metrics.columnconfigure(idx, weight=1)

        instruments = ttk.Frame(home_root, style="Root.TFrame")
        instruments.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        spot_card = ttk.Frame(instruments, style="Card.TFrame", padding=14)
        spot_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        futures_card = ttk.Frame(instruments, style="Card.TFrame", padding=14)
        futures_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(spot_card, text="Spot", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(spot_card, textvariable=self.dashboard_spot_status_var, style="Body.TLabel", justify=tk.LEFT).grid(
            row=1, column=0, sticky=tk.W, pady=(8, 2)
        )
        ttk.Label(
            spot_card,
            textvariable=self.dashboard_spot_primary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=2, column=0, sticky=tk.W, pady=(0, 2))
        ttk.Label(
            spot_card,
            textvariable=self.dashboard_spot_meta_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=3, column=0, sticky=tk.W, pady=(0, 10))

        spot_settings = ttk.Frame(spot_card, style="CardAlt.TFrame", padding=10)
        spot_settings.grid(row=4, column=0, sticky=tk.EW, pady=(0, 10))
        ttk.Label(spot_settings, text="Spot Mini Settings", style="SectionAlt.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W)
        ttk.Label(spot_settings, text="TP", style="BodyAlt.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(spot_settings, textvariable=self.cfg_take_profit, width=10).grid(row=1, column=1, sticky=tk.W, padx=(6, 0))
        ttk.Label(spot_settings, text="SL", style="BodyAlt.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(16, 0))
        ttk.Entry(spot_settings, textvariable=self.cfg_stop_loss, width=10).grid(row=1, column=3, sticky=tk.W, padx=(6, 0))
        ttk.Label(spot_settings, text="Max Pos", style="BodyAlt.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(spot_settings, textvariable=self.cfg_target_profit, width=10).grid(row=2, column=1, sticky=tk.W, padx=(6, 0))
        ttk.Label(spot_settings, text="Dust", style="BodyAlt.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(16, 0))
        ttk.Entry(spot_settings, textvariable=self.cfg_min_active_usdt, width=10).grid(row=2, column=3, sticky=tk.W, padx=(6, 0))
        ttk.Label(
            spot_settings,
            textvariable=self.dashboard_spot_settings_var,
            style="BodyAlt.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))

        spot_actions = ttk.Frame(spot_card, style="Root.TFrame")
        spot_actions.grid(row=5, column=0, sticky=tk.EW)
        ttk.Button(spot_actions, text="Start", command=self.start_spot_runtime, style="Start.TButton").grid(
            row=0, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(spot_actions, text="Stop", command=self.stop_spot_runtime, style="Stop.TButton").grid(
            row=0, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(spot_actions, text="Go To Spot Workspace", command=lambda: self._open_workspace(self.control_tab)).grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(spot_actions, text="Open Spot Logs", command=self.open_spot_logs_workspace).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=4
        )
        for idx in range(2):
            spot_actions.columnconfigure(idx, weight=1)
        spot_card.columnconfigure(0, weight=1)

        ttk.Label(futures_card, text="Futures", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            futures_card,
            textvariable=self.dashboard_futures_status_var,
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.W, pady=(8, 2))
        ttk.Label(
            futures_card,
            textvariable=self.dashboard_futures_primary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=2, column=0, sticky=tk.W, pady=(0, 2))
        ttk.Label(
            futures_card,
            textvariable=self.dashboard_futures_meta_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=3, column=0, sticky=tk.W, pady=(0, 10))

        futures_settings = ttk.Frame(futures_card, style="CardAlt.TFrame", padding=10)
        futures_settings.grid(row=4, column=0, sticky=tk.EW, pady=(0, 10))
        ttk.Label(futures_settings, text="Futures Mini Settings", style="SectionAlt.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W)
        ttk.Label(futures_settings, text="TP", style="BodyAlt.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(futures_settings, textvariable=self.cfg_take_profit, width=10).grid(row=1, column=1, sticky=tk.W, padx=(6, 0))
        ttk.Label(futures_settings, text="SL", style="BodyAlt.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(16, 0))
        ttk.Entry(futures_settings, textvariable=self.cfg_stop_loss, width=10).grid(row=1, column=3, sticky=tk.W, padx=(6, 0))
        ttk.Label(futures_settings, text="Max Pos", style="BodyAlt.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(futures_settings, textvariable=self.cfg_target_profit, width=10).grid(row=2, column=1, sticky=tk.W, padx=(6, 0))
        ttk.Label(futures_settings, text="Training", style="BodyAlt.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(16, 0))
        ttk.Label(futures_settings, textvariable=self.ml_training_state_var, style="BodyAlt.TLabel").grid(
            row=2, column=3, sticky=tk.W, padx=(6, 0)
        )
        ttk.Label(
            futures_settings,
            textvariable=self.dashboard_futures_settings_var,
            style="BodyAlt.TLabel",
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))

        futures_actions = ttk.Frame(futures_card, style="Root.TFrame")
        futures_actions.grid(row=5, column=0, sticky=tk.EW)
        ttk.Button(futures_actions, text="Start Training", command=self.start_ml, style="Accent.TButton").grid(
            row=0, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(futures_actions, text="Pause Training", command=self.pause_training).grid(
            row=0, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(
            futures_actions,
            text="Go To Futures Workspace",
            command=lambda: self._open_workspace(self.futures_tab),
        ).grid(row=1, column=0, sticky=tk.EW, padx=4, pady=4)
        ttk.Button(futures_actions, text="Open Futures Logs", command=self.open_futures_logs_workspace).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=4
        )
        for idx in range(2):
            futures_actions.columnconfigure(idx, weight=1)
        futures_card.columnconfigure(0, weight=1)

        bottom_row = ttk.Frame(home_root, style="Root.TFrame")
        bottom_row.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        components_card = ttk.Frame(bottom_row, style="Card.TFrame", padding=12)
        components_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        model_card = ttk.Frame(bottom_row, style="Card.TFrame", padding=12)
        model_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        ttk.Label(components_card, text="Loaded Components / Releases", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            components_card,
            textvariable=self.dashboard_release_status_var,
            style="MetricValue.TLabel",
            justify=tk.LEFT,
            wraplength=620,
        ).pack(anchor=tk.W, pady=(8, 2))
        ttk.Label(
            components_card,
            textvariable=self.dashboard_release_shell_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=620,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            components_card,
            textvariable=self.dashboard_release_components_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=620,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            components_card,
            textvariable=self.dashboard_release_models_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=620,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            components_card,
            textvariable=self.dashboard_release_manifests_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=620,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            components_card,
            text=f"Manifest source: {DASHBOARD_RELEASE_MANIFEST_PATH.name}",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(6, 0))

        ttk.Label(model_card, text="Model Registry", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            model_card,
            textvariable=self.models_summary_var,
            style="MetricValue.TLabel",
            justify=tk.LEFT,
            wraplength=420,
        ).pack(anchor=tk.W, pady=(8, 4))
        ttk.Label(
            model_card,
            textvariable=self.models_status_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=420,
        ).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(
            model_card,
            text="Champion/challenger evaluation stays in Model Registry Workspace; Home only surfaces active state.",
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=420,
        ).pack(anchor=tk.W)
        ttk.Button(
            model_card,
            text="Open Model Registry Workspace",
            command=lambda: self._open_workspace(self.model_registry_tab),
        ).pack(anchor=tk.W, pady=(10, 0))

    def _build_futures_workspace_tab(self) -> None:
        root = ttk.Frame(self.futures_tab, style="Root.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        shell_head = ttk.Frame(root, style="Card.TFrame", padding=14)
        shell_head.pack(fill=tk.X)
        ttk.Label(shell_head, text="Futures Workspace", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            shell_head,
            text=(
                "Futures are split into two internal zones: Training and Paper Workspace. "
                "This release does not present a live futures trading terminal."
            ),
            style="Body.TLabel",
            foreground=self._ui_colors.get("warning", "#F0B23A"),
            justify=tk.LEFT,
            wraplength=1180,
        ).pack(anchor=tk.W, pady=(6, 0))

        self.futures_notebook = ttk.Notebook(root)
        self.futures_notebook.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.futures_notebook.add(self.futures_training_tab, text="Futures Training Workspace")
        self.futures_notebook.add(self.futures_paper_tab, text="Futures Paper Workspace")

        self._build_futures_training_subworkspace()
        self._build_futures_paper_subworkspace()

    def _build_futures_training_subworkspace(self) -> None:
        root = ttk.Frame(self.futures_training_tab, style="Root.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        summary = ttk.Frame(root, style="Card.TFrame", padding=12)
        summary.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(summary, text="Training Status Summary", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            summary,
            textvariable=self.futures_training_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            summary,
            textvariable=self.futures_run_progress_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        summary.columnconfigure(0, weight=1)

        pipelines = ttk.Frame(root, style="Root.TFrame")
        pipelines.pack(fill=tk.X, pady=(0, 8))
        dataset_card = ttk.Frame(pipelines, style="Card.TFrame", padding=12)
        dataset_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pipeline_card = ttk.Frame(pipelines, style="Card.TFrame", padding=12)
        pipeline_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(dataset_card, text="Dataset / Candles", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            dataset_card,
            textvariable=self.futures_dataset_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=530,
        ).pack(anchor=tk.W, pady=(6, 0))

        ttk.Label(pipeline_card, text="Feature & Label Pipeline", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            pipeline_card,
            textvariable=self.futures_pipeline_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=530,
        ).pack(anchor=tk.W, pady=(6, 0))

        eval_row = ttk.Frame(root, style="Root.TFrame")
        eval_row.pack(fill=tk.X, pady=(0, 8))
        eval_card = ttk.Frame(eval_row, style="Card.TFrame", padding=12)
        eval_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        metrics_card = ttk.Frame(eval_row, style="Card.TFrame", padding=12)
        metrics_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(eval_card, text="Evaluation / Metrics Summary", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            eval_card,
            textvariable=self.futures_eval_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=530,
        ).pack(anchor=tk.W, pady=(6, 0))

        ttk.Label(metrics_card, text="Training Run Progress", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Label(metrics_card, text="Model", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Label(metrics_card, textvariable=self.ml_model_id_var, style="Body.TLabel").grid(
            row=1, column=1, sticky=tk.W, pady=3
        )
        ttk.Label(metrics_card, text="State", style="Body.TLabel").grid(
            row=1, column=2, sticky=tk.W, pady=3, padx=(12, 0)
        )
        ttk.Label(metrics_card, textvariable=self.ml_training_state_var, style="Body.TLabel").grid(
            row=1, column=3, sticky=tk.W, pady=3
        )
        ttk.Label(metrics_card, text="Progress", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.ml_progress = ttk.Progressbar(metrics_card, mode="indeterminate", maximum=100)
        self.ml_progress.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=3, padx=(0, 8))
        self.ml_progress_label = ttk.Label(
            metrics_card,
            textvariable=self.ml_progress_text_var,
            style="Body.TLabel",
            justify=tk.LEFT,
        )
        self.ml_progress_label.grid(row=2, column=3, sticky=tk.W, pady=3)
        self.ml_progress_label.configure(wraplength=220)
        self.ml_chart_canvas = tk.Canvas(
            metrics_card,
            height=48,
            bg=self._ui_colors.get("bg_soft", "#111D33"),
            highlightthickness=1,
            highlightbackground=self._ui_colors.get("line", "#2A4063"),
        )
        self.ml_chart_canvas.grid(row=3, column=0, columnspan=4, sticky=tk.EW, pady=(6, 0))
        for i in range(4):
            metrics_card.columnconfigure(i, weight=1)

        checkpoints_card = ttk.Frame(root, style="Card.TFrame", padding=12)
        checkpoints_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(checkpoints_card, text="Checkpoints / Active Futures Model", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            checkpoints_card,
            textvariable=self.futures_checkpoints_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).pack(anchor=tk.W, pady=(6, 6))
        cp_wrap = ttk.Frame(checkpoints_card, style="Card.TFrame")
        cp_wrap.pack(fill=tk.BOTH, expand=True)
        cp_wrap.columnconfigure(0, weight=1)
        cp_wrap.rowconfigure(0, weight=1)
        self.futures_training_checkpoints_tree = ttk.Treeview(
            cp_wrap,
            columns=("n", "model", "created", "active", "quality", "open_acc", "train_loss", "val_loss", "path"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("model", "Model", 200),
            ("created", "Created", 150),
            ("active", "Active", 60),
            ("quality", "BestMetric", 90),
            ("open_acc", "OpenAcc", 90),
            ("train_loss", "TrainLoss", 92),
            ("val_loss", "ValLoss", 92),
            ("path", "Checkpoint Path", 260),
        ]:
            self.futures_training_checkpoints_tree.heading(col, text=title)
            self.futures_training_checkpoints_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.futures_training_checkpoints_tree.column("path", stretch=True)
        cp_scroll_y = ttk.Scrollbar(cp_wrap, orient=tk.VERTICAL, command=self.futures_training_checkpoints_tree.yview)
        cp_scroll_x = ttk.Scrollbar(cp_wrap, orient=tk.HORIZONTAL, command=self.futures_training_checkpoints_tree.xview)
        self.futures_training_checkpoints_tree.configure(yscrollcommand=cp_scroll_y.set, xscrollcommand=cp_scroll_x.set)
        self.futures_training_checkpoints_tree.grid(row=0, column=0, sticky=tk.NSEW)
        cp_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        cp_scroll_x.grid(row=1, column=0, sticky=tk.EW)

        preset_card = ttk.Frame(root, style="Card.TFrame", padding=12)
        preset_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(preset_card, text="Futures Research Preset", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky=tk.W
        )
        ttk.Label(
            preset_card,
            text=(
                "Futures Workspace stays research-first. The available preset configures the futures paper/training "
                "flow without pretending to be a live trading terminal."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=900,
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            preset_card,
            text="Preset: Futures Spike Reversal (research / paper)",
            style="Body.TLabel",
        ).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Button(
            preset_card,
            text="Apply Futures Research Preset",
            command=self.apply_futures_research_preset,
        ).grid(row=2, column=1, sticky=tk.W, padx=(12, 0), pady=(2, 0))
        ttk.Button(
            preset_card,
            text="Open Model Registry",
            command=self.open_model_registry_workspace,
        ).grid(row=2, column=2, sticky=tk.W, padx=(12, 0), pady=(2, 0))
        preset_card.columnconfigure(0, weight=1)

        actions = ttk.Frame(root, style="Card.TFrame", padding=12)
        actions.pack(fill=tk.X)
        ttk.Label(actions, text="Training Actions", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Button(actions, text="Refresh", command=self.refresh_runtime_snapshot).grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Prepare Dataset", command=self.prepare_futures_training_dataset).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Build Features / Labels", command=self.build_futures_features_labels).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Start Training", command=self.start_training, style="Start.TButton").grid(
            row=1, column=3, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Pause Training", command=self.pause_training).grid(
            row=2, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Run Evaluation", command=self.run_futures_training_evaluation).grid(
            row=2, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Checkpoints", command=self.open_futures_checkpoints_dir).grid(
            row=2, column=2, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Futures Logs", command=self.open_futures_logs_workspace).grid(
            row=2, column=3, sticky=tk.EW, padx=4, pady=4
        )
        for idx in range(4):
            actions.columnconfigure(idx, weight=1)

    def _build_futures_paper_subworkspace(self) -> None:
        root = ttk.Frame(self.futures_paper_tab, style="Root.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        summary = ttk.Frame(root, style="Card.TFrame", padding=12)
        summary.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(summary, text="Futures Paper Workspace", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            summary,
            text=(
                "Paper evaluation stays separate from live execution. This workspace shows training-adjacent "
                "paper results, open paper positions and pending paper orders without pretending to be a "
                "live futures trading terminal."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            summary,
            textvariable=self.futures_paper_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=2, column=0, sticky=tk.W)
        ttk.Label(
            summary,
            textvariable=self.futures_paper_status_var,
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=3, column=0, sticky=tk.W, pady=(4, 0))
        summary.columnconfigure(0, weight=1)

        tables_row = ttk.Frame(root, style="Root.TFrame")
        tables_row.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        pos_card = ttk.Frame(tables_row, style="Card.TFrame", padding=12)
        pos_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ord_card = ttk.Frame(tables_row, style="Card.TFrame", padding=12)
        ord_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(pos_card, text="Paper Positions Snapshot", style="Section.TLabel").pack(anchor=tk.W)
        pos_wrap = ttk.Frame(pos_card, style="Card.TFrame")
        pos_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        pos_wrap.columnconfigure(0, weight=1)
        pos_wrap.rowconfigure(0, weight=1)
        self.futures_paper_positions_tree = ttk.Treeview(
            pos_wrap,
            columns=("n", "symbol", "side", "qty", "entry", "mark", "liq", "u_pnl", "tp", "sl", "protection"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 120),
            ("side", "Side", 70),
            ("qty", "Qty", 80),
            ("entry", "Entry", 92),
            ("mark", "Mark", 92),
            ("liq", "Liq", 92),
            ("u_pnl", "Unrealized", 92),
            ("tp", "TP", 92),
            ("sl", "SL", 92),
            ("protection", "Protection", 96),
        ]:
            self.futures_paper_positions_tree.heading(col, text=title)
            self.futures_paper_positions_tree.column(col, width=width, anchor=tk.W, stretch=False)
        pos_scroll = ttk.Scrollbar(pos_wrap, orient=tk.VERTICAL, command=self.futures_paper_positions_tree.yview)
        self.futures_paper_positions_tree.configure(yscrollcommand=pos_scroll.set)
        self.futures_paper_positions_tree.grid(row=0, column=0, sticky=tk.NSEW)
        pos_scroll.grid(row=0, column=1, sticky=tk.NS)

        ttk.Label(ord_card, text="Pending Futures Orders", style="Section.TLabel").pack(anchor=tk.W)
        ord_wrap = ttk.Frame(ord_card, style="Card.TFrame")
        ord_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ord_wrap.columnconfigure(0, weight=1)
        ord_wrap.rowconfigure(0, weight=1)
        self.futures_paper_orders_tree = ttk.Treeview(
            ord_wrap,
            columns=("n", "symbol", "side", "order_id", "link_id", "type", "price", "qty", "status"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 120),
            ("side", "Side", 70),
            ("order_id", "OrderID", 120),
            ("link_id", "LinkID", 120),
            ("type", "Type", 72),
            ("price", "Price", 92),
            ("qty", "Qty", 80),
            ("status", "Status", 92),
        ]:
            self.futures_paper_orders_tree.heading(col, text=title)
            self.futures_paper_orders_tree.column(col, width=width, anchor=tk.W, stretch=False)
        ord_scroll = ttk.Scrollbar(ord_wrap, orient=tk.VERTICAL, command=self.futures_paper_orders_tree.yview)
        self.futures_paper_orders_tree.configure(yscrollcommand=ord_scroll.set)
        self.futures_paper_orders_tree.grid(row=0, column=0, sticky=tk.NSEW)
        ord_scroll.grid(row=0, column=1, sticky=tk.NS)

        closed_card = ttk.Frame(root, style="Card.TFrame", padding=12)
        closed_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(closed_card, text="Closed Paper Results", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            closed_card,
            text="Result class is derived from final net PnL after close: good=green, bad=red, flat=neutral.",
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).pack(anchor=tk.W, pady=(4, 0))
        closed_wrap = ttk.Frame(closed_card, style="Card.TFrame")
        closed_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        closed_wrap.columnconfigure(0, weight=1)
        closed_wrap.rowconfigure(0, weight=1)
        self.futures_paper_closed_tree = ttk.Treeview(
            closed_wrap,
            columns=("n", "symbol", "side", "entry", "exit", "net_pnl", "result", "model", "policy", "opened", "closed"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 120),
            ("side", "Side", 70),
            ("entry", "Entry", 92),
            ("exit", "Exit", 92),
            ("net_pnl", "Net PnL", 96),
            ("result", "Result", 76),
            ("model", "Model", 150),
            ("policy", "Policy", 96),
            ("opened", "Opened", 144),
            ("closed", "Closed", 144),
        ]:
            self.futures_paper_closed_tree.heading(col, text=title)
            self.futures_paper_closed_tree.column(col, width=width, anchor=tk.W, stretch=False)
        closed_scroll = ttk.Scrollbar(closed_wrap, orient=tk.VERTICAL, command=self.futures_paper_closed_tree.yview)
        self.futures_paper_closed_tree.configure(yscrollcommand=closed_scroll.set)
        self.futures_paper_closed_tree.grid(row=0, column=0, sticky=tk.NSEW)
        closed_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.futures_paper_closed_tree.tag_configure("paper_good", foreground="#5FE08C")
        self.futures_paper_closed_tree.tag_configure("paper_bad", foreground="#FF7F7F")
        self.futures_paper_closed_tree.tag_configure("paper_flat", foreground="#A0B6D8")

        actions = ttk.Frame(root, style="Card.TFrame", padding=12)
        actions.pack(fill=tk.X)
        ttk.Label(actions, text="Paper Actions", style="Section.TLabel").grid(row=0, column=0, columnspan=6, sticky=tk.W)
        ttk.Button(actions, text="Refresh", command=self.refresh_runtime_snapshot).grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Close Selected Paper Position", command=self.close_selected_paper_position).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Close All Paper Positions", command=self.close_all_paper_positions).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Reset Paper Session", command=self.reset_paper_session).grid(
            row=1, column=3, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Futures Logs", command=self.open_futures_logs_workspace).grid(
            row=1, column=4, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Model Registry", command=lambda: self._open_workspace(self.model_registry_tab)).grid(
            row=1, column=5, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Label(
            actions,
            text="Close/reset controls are intentionally explicit but remain unsupported until paper execution lifecycle is implemented.",
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=2, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(4, 0))
        for idx in range(6):
            actions.columnconfigure(idx, weight=1)

    def _refresh_telegram_workspace_text(self) -> None:
        # Legacy text panel compatibility; current Telegram Workspace uses structured cards/tables.
        if self.telegram_workspace_text is None:
            return
        lines = [
            self.telegram_workspace_summary_var.get(),
            self.telegram_workspace_profile_var.get(),
            self.telegram_workspace_access_var.get(),
            self.telegram_workspace_commands_var.get(),
            self.telegram_workspace_health_var.get(),
            self.telegram_workspace_capabilities_var.get(),
        ]
        try:
            self.telegram_workspace_text.configure(state=tk.NORMAL)
            self.telegram_workspace_text.delete("1.0", tk.END)
            self.telegram_workspace_text.insert(tk.END, "\n".join(lines))
            self.telegram_workspace_text.configure(state=tk.DISABLED)
        except Exception:
            return

    def _telegram_workspace_test_send(self) -> None:
        token = str(self.env_vars.get("TELEGRAM_BOT_TOKEN").get() if self.env_vars.get("TELEGRAM_BOT_TOKEN") else "").strip()
        if not token:
            self._record_telegram_error(source="test_send", error="configuration_missing_token")
            self._enqueue_log("[telegram-workspace] test send skipped: token is not configured")
            messagebox.showwarning("Telegram Workspace", "TELEGRAM_BOT_TOKEN не задан. Test Send недоступен.")
            self.refresh_runtime_snapshot()
            return
        self._record_telegram_command(command="/status", source="workspace_test_send", status="intent")
        self._record_telegram_alert(
            source="test_send",
            message="Test send intent recorded (network send is not executed from Dashboard Workspace).",
            status="ok",
        )
        self._enqueue_log("[telegram-workspace] test send intent recorded")
        self.refresh_runtime_snapshot()

    def _reload_telegram_workspace_status(self) -> None:
        try:
            self._start_telegram_control_if_configured()
            self._record_telegram_alert(source="workspace", message="Telegram status reloaded", status="ok")
        except Exception as exc:
            self._record_telegram_error(source="reload_status", error=str(exc))
            self._enqueue_log(f"[telegram-workspace] reload failed: {exc}")
        self.refresh_runtime_snapshot()

    def copy_telegram_chat_summary(self) -> None:
        payload = (
            f"{self.telegram_workspace_access_var.get()}\n"
            f"{self.telegram_workspace_profile_var.get()}\n"
            f"{self.telegram_workspace_health_var.get()}"
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self._enqueue_log("[telegram-workspace] copied chat summary")

    def _build_telegram_workspace_tab(self) -> None:
        root = ttk.Frame(self.telegram_tab, style="Root.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        summary = ttk.Frame(root, style="Card.TFrame", padding=12)
        summary.pack(fill=tk.X)
        ttk.Label(summary, text="Telegram Workspace", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            summary,
            text="Operational visibility for Telegram bot module. Token values are never shown in plain text.",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Label(
            summary,
            textvariable=self.telegram_workspace_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=2, column=0, sticky=tk.W, pady=(8, 2))
        ttk.Label(
            summary,
            textvariable=self.telegram_workspace_capabilities_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=3, column=0, sticky=tk.W)
        summary.columnconfigure(0, weight=1)

        details = ttk.Frame(root, style="Card.TFrame", padding=12)
        details.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(details, text="Bot Profile / Connection", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            details,
            textvariable=self.telegram_workspace_profile_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(details, text="Allowed Chats / Access", style="Section.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Label(
            details,
            textvariable=self.telegram_workspace_access_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=3, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(details, text="Available Commands", style="Section.TLabel").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Label(
            details,
            textvariable=self.telegram_workspace_commands_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=5, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(details, text="Telegram Errors / Health", style="Section.TLabel").grid(
            row=6, column=0, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(
            details,
            textvariable=self.telegram_workspace_health_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1060,
        ).grid(row=7, column=0, sticky=tk.W, pady=(6, 0))
        details.columnconfigure(0, weight=1)

        activity = ttk.Frame(root, style="Card.TFrame", padding=12)
        activity.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(activity, text="Recent Incoming Commands / Alerts / Errors", style="Section.TLabel").pack(anchor=tk.W)
        activity_notebook = ttk.Notebook(activity)
        activity_notebook.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        commands_tab = ttk.Frame(activity_notebook, style="Root.TFrame")
        alerts_tab = ttk.Frame(activity_notebook, style="Root.TFrame")
        errors_tab = ttk.Frame(activity_notebook, style="Root.TFrame")
        activity_notebook.add(commands_tab, text="Recent Incoming Commands")
        activity_notebook.add(alerts_tab, text="Recent Alerts / Notifications")
        activity_notebook.add(errors_tab, text="Telegram Errors / Health")

        self.telegram_workspace_commands_tree = ttk.Treeview(
            commands_tab,
            columns=("n", "ts", "command", "source", "status"),
            show="headings",
            height=7,
        )
        for col, title, width in [
            ("n", "N", 50),
            ("ts", "Time", 180),
            ("command", "Command", 240),
            ("source", "Source", 160),
            ("status", "Status", 120),
        ]:
            self.telegram_workspace_commands_tree.heading(col, text=title)
            self.telegram_workspace_commands_tree.column(col, width=width, anchor=tk.W, stretch=(col == "command"))
        cmd_scroll = ttk.Scrollbar(commands_tab, orient=tk.VERTICAL, command=self.telegram_workspace_commands_tree.yview)
        self.telegram_workspace_commands_tree.configure(yscrollcommand=cmd_scroll.set)
        self.telegram_workspace_commands_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cmd_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.telegram_workspace_alerts_tree = ttk.Treeview(
            alerts_tab,
            columns=("n", "ts", "message", "source", "status"),
            show="headings",
            height=7,
        )
        for col, title, width in [
            ("n", "N", 50),
            ("ts", "Time", 180),
            ("message", "Alert / Notification", 520),
            ("source", "Source", 160),
            ("status", "Status", 120),
        ]:
            self.telegram_workspace_alerts_tree.heading(col, text=title)
            self.telegram_workspace_alerts_tree.column(col, width=width, anchor=tk.W, stretch=(col == "message"))
        alert_scroll = ttk.Scrollbar(alerts_tab, orient=tk.VERTICAL, command=self.telegram_workspace_alerts_tree.yview)
        self.telegram_workspace_alerts_tree.configure(yscrollcommand=alert_scroll.set)
        self.telegram_workspace_alerts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        alert_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.telegram_workspace_errors_tree = ttk.Treeview(
            errors_tab,
            columns=("n", "ts", "error", "source", "status"),
            show="headings",
            height=7,
        )
        for col, title, width in [
            ("n", "N", 50),
            ("ts", "Time", 180),
            ("error", "Error", 520),
            ("source", "Source", 160),
            ("status", "Status", 120),
        ]:
            self.telegram_workspace_errors_tree.heading(col, text=title)
            self.telegram_workspace_errors_tree.column(col, width=width, anchor=tk.W, stretch=(col == "error"))
        error_scroll = ttk.Scrollbar(errors_tab, orient=tk.VERTICAL, command=self.telegram_workspace_errors_tree.yview)
        self.telegram_workspace_errors_tree.configure(yscrollcommand=error_scroll.set)
        self.telegram_workspace_errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        error_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        actions = ttk.Frame(root, style="Card.TFrame", padding=12)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(actions, text="Telegram Actions", style="Section.TLabel").grid(row=0, column=0, columnspan=6, sticky=tk.W)
        ttk.Button(actions, text="Refresh", command=self.refresh_runtime_snapshot).grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Test Send", command=self._telegram_workspace_test_send).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Reload Telegram Status", command=self._reload_telegram_workspace_status).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Telegram Logs", command=self.open_telegram_logs_workspace).grid(
            row=1, column=3, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Open Settings/Profile", command=lambda: self._open_workspace(self.settings_tab)).grid(
            row=1, column=4, sticky=tk.EW, padx=4, pady=4
        )
        ttk.Button(actions, text="Copy Chat Summary", command=self.copy_telegram_chat_summary).grid(
            row=1, column=5, sticky=tk.EW, padx=4, pady=4
        )
        for idx in range(6):
            actions.columnconfigure(idx, weight=1)

    def _build_control_tab(self) -> None:
        split = ttk.Panedwindow(self.control_tab, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        left = ttk.Frame(split, style="Root.TFrame")
        right = ttk.Frame(split, style="Root.TFrame")
        split.add(left, weight=4)
        split.add(right, weight=2)

        summary_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        summary_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(summary_card, text="Spot Status Summary", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Label(
            summary_card,
            textvariable=self.spot_workspace_summary_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=760,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            summary_card,
            textvariable=self.spot_workspace_policy_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=760,
        ).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        summary_card.columnconfigure(0, weight=1)

        path_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        path_card.pack(fill=tk.X)
        ttk.Label(path_card, text="Spot Runtime", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W, columnspan=4)
        ttk.Label(path_card, text="Python", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Label(path_card, textvariable=self.runtime_python_name_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=6)
        ttk.Label(path_card, text="Config", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, pady=6, padx=(18, 0))
        ttk.Label(path_card, textvariable=self.runtime_config_name_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=6)

        action_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        action_card.pack(fill=tk.X, pady=8)
        ttk.Label(action_card, text="Spot Actions", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)

        ttk.Button(action_card, text="Start Spot", command=self.start_spot_runtime, style="Start.TButton").grid(
            row=1, column=0, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Stop Spot", command=self.stop_spot_runtime, style="Stop.TButton").grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Refresh", command=self.refresh_runtime_snapshot).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=3
        )

        ttk.Button(action_card, text="Run Spot Reconcile", command=self.run_spot_reconcile).grid(
            row=2, column=0, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Sell Selected", command=self.sell_selected_spot_holding).grid(
            row=2, column=1, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Close Stale Holds", command=self.close_stale_spot_holds).grid(
            row=2, column=2, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Open Details", command=self.inspect_selected_spot_holding).grid(
            row=3, column=0, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Copy Selected", command=self.copy_selected_spot_holding).grid(
            row=3, column=1, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Button(action_card, text="Run Preflight", command=self.run_preflight, style="Accent.TButton").grid(
            row=3, column=2, sticky=tk.EW, padx=4, pady=3
        )
        ttk.Label(
            action_card,
            text="Sell actions respect hold policy: recovered/manual/dust are protected unless policy allows.",
            style="Body.TLabel",
        ).grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=4, pady=(4, 2)
        )

        for i in range(3):
            action_card.columnconfigure(i, weight=1)

        strategy_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        strategy_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(strategy_card, text="Strategy Selection", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Checkbutton(strategy_card, text="Spot Spread (Maker)", variable=self.enable_spot_spread_var).grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(strategy_card, text="Spot Spike Burst", variable=self.enable_spot_spike_var).grid(
            row=1, column=1, sticky=tk.W, pady=4, padx=(12, 0)
        )
        ttk.Label(
            strategy_card,
            text="Start Spot launches enabled spot presets only. Futures research presets are managed in Futures Workspace.",
            style="Body.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(2, 0))
        strategy_card.columnconfigure(3, weight=1)

        self._build_spot_strategy_presets_panel(left)

        account_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        account_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(account_card, text="Spot Inventory and Orders", style="Section.TLabel").grid(
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
        ttk.Button(account_card, text="Inspect Holding", command=self.inspect_selected_spot_holding).grid(
            row=2, column=6, sticky=tk.E, padx=(14, 0), pady=2
        )
        account_card.columnconfigure(6, weight=1)
        account_card.rowconfigure(3, weight=1)
        account_card.rowconfigure(4, weight=1)

        orders_grid = ttk.Frame(account_card, style="Card.TFrame")
        orders_grid.grid(row=3, column=0, columnspan=7, sticky=tk.NSEW, pady=(8, 0))
        orders_grid.columnconfigure(0, weight=1, uniform="orders")
        orders_grid.columnconfigure(1, weight=1, uniform="orders")
        orders_grid.rowconfigure(0, weight=1)
        orders_grid.rowconfigure(1, weight=1)

        open_card = ttk.Frame(orders_grid, style="Card.TFrame")
        open_card.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))
        ttk.Label(open_card, text="Spot Open Orders (domain)", style="Body.TLabel").pack(anchor=tk.W)
        open_table_wrap = ttk.Frame(open_card, style="Card.TFrame")
        open_table_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        open_table_wrap.columnconfigure(0, weight=1)
        open_table_wrap.rowconfigure(0, weight=1)
        self.open_orders_tree = ttk.Treeview(
            open_table_wrap,
            columns=(
                "n",
                "symbol",
                "side",
                "status",
                "type",
                "price",
                "qty",
                "filled",
                "strategy",
                "updated",
            ),
            show="headings",
            height=11,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 96),
            ("side", "Side", 58),
            ("status", "Status", 100),
            ("type", "Type", 72),
            ("price", "Price", 90),
            ("qty", "Qty", 80),
            ("filled", "Filled", 86),
            ("strategy", "Strategy", 110),
            ("updated", "Updated", 145),
        ]:
            self.open_orders_tree.heading(col, text=title)
            self.open_orders_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.open_orders_tree.column("updated", stretch=True)
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
        ttk.Label(history_card, text="Spot Holdings Lifecycle", style="Body.TLabel").pack(anchor=tk.W)
        history_table_wrap = ttk.Frame(history_card, style="Card.TFrame")
        history_table_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        history_table_wrap.columnconfigure(0, weight=1)
        history_table_wrap.rowconfigure(0, weight=1)
        self.spot_workspace_holdings_tree = ttk.Treeview(
            history_table_wrap,
            columns=(
                "n",
                "symbol",
                "base",
                "free",
                "locked",
                "entry",
                "reason",
                "recovered",
                "owner",
                "class",
                "state",
                "policy",
                "last_seen",
                "stale",
            ),
            show="headings",
            height=11,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("symbol", "Symbol", 90),
            ("base", "Base", 64),
            ("free", "Free", 90),
            ("locked", "Locked", 90),
            ("entry", "AvgEntry", 90),
            ("reason", "HoldReason", 145),
            ("recovered", "Recovered", 88),
            ("owner", "StrategyOwner", 120),
            ("class", "Class", 120),
            ("state", "State", 90),
            ("policy", "ExitPolicy", 120),
            ("last_seen", "LastSeen", 145),
            ("stale", "Stale", 66),
        ]:
            self.spot_workspace_holdings_tree.heading(col, text=title)
            self.spot_workspace_holdings_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.spot_workspace_holdings_tree.column("last_seen", stretch=True)
        history_scroll_y = ttk.Scrollbar(
            history_table_wrap, orient=tk.VERTICAL, command=self.spot_workspace_holdings_tree.yview
        )
        history_scroll_x = ttk.Scrollbar(
            history_table_wrap, orient=tk.HORIZONTAL, command=self.spot_workspace_holdings_tree.xview
        )
        self.spot_workspace_holdings_tree.configure(
            yscrollcommand=history_scroll_y.set,
            xscrollcommand=history_scroll_x.set,
        )
        self.spot_workspace_holdings_tree.grid(row=0, column=0, sticky=tk.NSEW)
        history_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        history_scroll_x.grid(row=1, column=0, sticky=tk.EW)

        fills_card = ttk.Frame(orders_grid, style="Card.TFrame")
        fills_card.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 6), pady=(8, 0))
        ttk.Label(fills_card, text="Spot Fills / Executions", style="Body.TLabel").pack(anchor=tk.W)
        fills_wrap = ttk.Frame(fills_card, style="Card.TFrame")
        fills_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        fills_wrap.columnconfigure(0, weight=1)
        fills_wrap.rowconfigure(0, weight=1)
        self.spot_workspace_fills_tree = ttk.Treeview(
            fills_wrap,
            columns=("n", "ts", "symbol", "side", "price", "qty", "fee", "fee_ccy", "maker", "exec_id"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("ts", "Time", 145),
            ("symbol", "Symbol", 90),
            ("side", "Side", 60),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
            ("fee", "Fee", 85),
            ("fee_ccy", "FeeCCY", 80),
            ("maker", "Maker", 68),
            ("exec_id", "ExecID", 120),
        ]:
            self.spot_workspace_fills_tree.heading(col, text=title)
            self.spot_workspace_fills_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.spot_workspace_fills_tree.column("exec_id", stretch=True)
        fills_scroll_y = ttk.Scrollbar(fills_wrap, orient=tk.VERTICAL, command=self.spot_workspace_fills_tree.yview)
        fills_scroll_x = ttk.Scrollbar(fills_wrap, orient=tk.HORIZONTAL, command=self.spot_workspace_fills_tree.xview)
        self.spot_workspace_fills_tree.configure(yscrollcommand=fills_scroll_y.set, xscrollcommand=fills_scroll_x.set)
        self.spot_workspace_fills_tree.grid(row=0, column=0, sticky=tk.NSEW)
        fills_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        fills_scroll_x.grid(row=1, column=0, sticky=tk.EW)

        exit_card = ttk.Frame(orders_grid, style="Card.TFrame")
        exit_card.grid(row=1, column=1, sticky=tk.NSEW, padx=(6, 0), pady=(8, 0))
        ttk.Label(exit_card, text="Spot Exit Decisions / Inventory Actions", style="Body.TLabel").pack(anchor=tk.W)
        exit_wrap = ttk.Frame(exit_card, style="Card.TFrame")
        exit_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        exit_wrap.columnconfigure(0, weight=1)
        exit_wrap.rowconfigure(0, weight=1)
        self.spot_workspace_exit_tree = ttk.Treeview(
            exit_wrap,
            columns=("n", "ts", "symbol", "type", "reason", "policy", "pnl_pct", "pnl_quote", "applied"),
            show="headings",
            height=8,
        )
        for col, title, width in [
            ("n", "№", 44),
            ("ts", "Time", 145),
            ("symbol", "Symbol", 90),
            ("type", "Type", 100),
            ("reason", "Reason", 170),
            ("policy", "Policy", 110),
            ("pnl_pct", "PnL %", 80),
            ("pnl_quote", "PnL Quote", 95),
            ("applied", "Applied", 72),
        ]:
            self.spot_workspace_exit_tree.heading(col, text=title)
            self.spot_workspace_exit_tree.column(col, width=width, anchor=tk.W, stretch=False)
        self.spot_workspace_exit_tree.column("reason", stretch=True)
        exit_scroll_y = ttk.Scrollbar(exit_wrap, orient=tk.VERTICAL, command=self.spot_workspace_exit_tree.yview)
        exit_scroll_x = ttk.Scrollbar(exit_wrap, orient=tk.HORIZONTAL, command=self.spot_workspace_exit_tree.xview)
        self.spot_workspace_exit_tree.configure(yscrollcommand=exit_scroll_y.set, xscrollcommand=exit_scroll_x.set)
        self.spot_workspace_exit_tree.grid(row=0, column=0, sticky=tk.NSEW)
        exit_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        exit_scroll_x.grid(row=1, column=0, sticky=tk.EW)

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
        training_redirect = ttk.Frame(right, style="Card.TFrame", padding=10)
        training_redirect.pack(fill=tk.X, pady=8)
        ttk.Label(training_redirect, text="Futures Workspace", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            training_redirect,
            text="Training and paper research controls are separated inside Futures Workspace.",
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=320,
        ).pack(anchor=tk.W, pady=(6, 4))
        ttk.Button(
            training_redirect,
            text="Open Futures Workspace",
            command=lambda: self._open_workspace(self.futures_tab),
        ).pack(anchor=tk.W)

        hint = ttk.Frame(right, style="Card.TFrame", padding=10)
        hint.pack(fill=tk.X, pady=8)
        ttk.Label(hint, text="Hint", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hint,
            text="Use Dashboard Home quick actions for runtime control.\nPause Training keeps spot runtime active and pauses model updates.",
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
        ttk.Label(head, text="Logs Workspace", style="Section.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        ttk.Label(
            head,
            text="Channel / instrument filters and quick operator routing live here.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, anchor=tk.W, padx=(12, 0))
        self.log_jump_full = ttk.Button(head, text="⬇", width=3, command=lambda: self._jump_log_to_end("full"))
        self.log_jump_full.pack(side=tk.RIGHT)
        self.log_jump_full.pack_forget()

        filters = ttk.Frame(logs_card, style="Card.TFrame")
        filters.pack(fill=tk.X, pady=(0, 8))
        self.log_channel_filter_combo = labeled_combobox(
            filters,
            label="Channel",
            variable=self.log_filter_channel_var,
            values=list(DASHBOARD_LOG_CHANNELS),
            width=18,
        )
        self.log_instrument_filter_combo = labeled_combobox(
            filters,
            label="Instrument",
            variable=self.log_filter_instrument_var,
            values=list(DASHBOARD_LOG_INSTRUMENTS),
            width=16,
        )
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
        ttk.Button(filters, text="Spot", command=self.open_spot_logs_workspace).pack(side=tk.LEFT, pady=(18, 0), padx=(8, 0))
        ttk.Button(filters, text="Futures", command=self.open_futures_logs_workspace).pack(side=tk.LEFT, pady=(18, 0), padx=(4, 0))
        ttk.Button(filters, text="Telegram", command=self.open_telegram_logs_workspace).pack(side=tk.LEFT, pady=(18, 0), padx=(4, 0))
        ttk.Button(filters, text="Ops", command=self.open_ops_logs_workspace).pack(side=tk.LEFT, pady=(18, 0), padx=(4, 0))
        ttk.Button(filters, text="Errors", command=self.open_error_logs_workspace).pack(side=tk.LEFT, pady=(18, 0), padx=(4, 0))

        if self.log_channel_filter_combo is not None:
            self.log_channel_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        if self.log_instrument_filter_combo is not None:
            self.log_instrument_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        if self.log_pair_filter_combo is not None:
            self.log_pair_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        if self.log_level_filter_combo is not None:
            self.log_level_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_log_filter_changed())
        self.log_filter_channel_var.trace_add("write", lambda *_: self._on_log_filter_changed())
        self.log_filter_instrument_var.trace_add("write", lambda *_: self._on_log_filter_changed())
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

        ops_head = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        ops_head.pack(fill=tk.X)
        ttk.Label(ops_head, text="Ops Workspace", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            ops_head,
            text="Operational health, reconciliation, protection and domain snapshots live here.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ops_actions = ttk.Frame(ops_head, style="Card.TFrame")
        ops_actions.grid(row=0, column=1, rowspan=2, sticky=tk.NE, padx=(12, 0))
        ttk.Button(ops_actions, text="Refresh", command=self.refresh_runtime_snapshot).grid(row=0, column=0, sticky=tk.EW, pady=2)
        ttk.Button(ops_actions, text="Open Ops Logs", command=self.open_ops_logs_workspace).grid(row=1, column=0, sticky=tk.EW, pady=2)
        ttk.Button(ops_actions, text="Focus Issues", command=self.open_ops_issues_view).grid(row=2, column=0, sticky=tk.EW, pady=2)
        ttk.Button(ops_actions, text="Focus Futures Positions", command=self.open_ops_futures_positions_view).grid(
            row=3, column=0, sticky=tk.EW, pady=2
        )
        ops_head.columnconfigure(0, weight=1)

        health_row = ttk.Frame(stats_root, style="Root.TFrame")
        health_row.pack(fill=tk.X, pady=(8, 0))
        for idx, (title, value_var) in enumerate(
            [
                ("Runtime Services", self.ops_service_health_var),
                ("Reconciliation", self.ops_reconciliation_var),
                ("Protection / Risk", self.ops_protection_var),
                ("DB / Freshness", self.ops_db_health_var),
                ("Capabilities", self.ops_capabilities_var),
            ]
        ):
            card_frame = ttk.Frame(health_row, style="CardAlt.TFrame", padding=10)
            card_frame.grid(row=0, column=idx, sticky=tk.NSEW, padx=(0 if idx == 0 else 8, 0))
            ttk.Label(card_frame, text=title, style="SectionAlt.TLabel").pack(anchor=tk.W)
            ttk.Label(
                card_frame,
                textvariable=value_var,
                style="BodyAlt.TLabel",
                justify=tk.LEFT,
                wraplength=220,
            ).pack(anchor=tk.W, pady=(6, 0))
            health_row.columnconfigure(idx, weight=1)

        summary_card = ttk.Frame(stats_root, style="Card.TFrame", padding=10)
        summary_card.pack(fill=tk.X, pady=(8, 0))
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
        self.ops_domain_notebook = domain_notebook
        domain_notebook.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        spot_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        futures_pos_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        futures_ord_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        issues_frame = ttk.Frame(domain_notebook, style="Root.TFrame")
        self.ops_futures_positions_frame = futures_pos_frame
        self.ops_issues_frame = issues_frame
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
        ttk.Label(top_card, text="Model Registry Workspace", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            top_card,
            text="Champion/challenger state, activation and comparison live here as a dedicated Dashboard workspace.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Label(top_card, textvariable=self.models_summary_var, style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Label(top_card, textvariable=self.models_status_var, style="Body.TLabel", justify=tk.LEFT).grid(
            row=3, column=0, sticky=tk.W, pady=(6, 0)
        )
        actions = ttk.Frame(top_card, style="Card.TFrame")
        actions.grid(row=0, column=1, rowspan=4, sticky=tk.NE, padx=(12, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_runtime_snapshot).grid(row=0, column=0, sticky=tk.EW, pady=2)
        ttk.Button(actions, text="Promote Selected to Active", command=self.activate_selected_model).grid(
            row=1, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(actions, text="Compare Selected Models", command=self.compare_selected_models).grid(
            row=2, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(actions, text="Open Model Stats", command=self.open_selected_model_stats).grid(
            row=3, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(actions, text="Copy Artifact Path", command=self.copy_selected_model_artifact).grid(
            row=4, column=0, sticky=tk.EW, pady=2
        )
        top_card.columnconfigure(0, weight=1)

        table_card = ttk.Frame(models_root, style="Card.TFrame", padding=10)
        table_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.models_tree = ttk.Treeview(
            table_card,
            columns=(
                "model_id",
                "instrument",
                "policy",
                "source",
                "role",
                "status",
                "created",
                "outcomes",
                "winrate",
                "net_pnl",
                "edge",
                "artifact",
            ),
            show="headings",
            height=24,
            selectmode="extended",
        )
        for col, title, width in [
            ("model_id", "Model", 180),
            ("instrument", "Instrument", 90),
            ("policy", "Policy", 90),
            ("source", "Source", 90),
            ("role", "Role", 120),
            ("status", "Status", 100),
            ("created", "Created", 150),
            ("outcomes", "Outcomes", 86),
            ("winrate", "WinRate", 86),
            ("net_pnl", "NetPnL", 92),
            ("edge", "Edge bps", 86),
            ("artifact", "Artifact", 220),
        ]:
            self.models_tree.heading(col, text=title)
            self.models_tree.column(col, width=width, anchor=tk.W)
        self.models_tree.column("artifact", stretch=True)
        self.models_tree.tag_configure("model_active", foreground="#5FE08C")
        model_scroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.models_tree.yview)
        self.models_tree.configure(yscrollcommand=model_scroll.set)
        self.models_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        model_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_spot_strategy_presets_panel(self, parent: ttk.Frame) -> None:
        spike_root = ttk.Frame(parent, style="Card.TFrame", padding=10)
        spike_root.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(spike_root, text="Spot Strategy Presets", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            spike_root,
            text=(
                "Preset controls stay inside Spot Workspace. Use them to prepare spot-oriented runtime configs "
                "without turning Settings Workspace into a trading-control surface."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=760,
        ).pack(anchor=tk.W, pady=(6, 0))

        mode_card = ttk.Frame(spike_root, style="Card.TFrame")
        mode_card.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(mode_card, text="Preset", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(mode_card, text="Trading mode", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            mode_card,
            textvariable=self.strategy_mode_var,
            values=dashboard_strategy_preset_labels("spot"),
            state="readonly",
            width=30,
        ).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(
            mode_card,
            text="Spot Spread = классический maker.\nSpot Spike = burst на спайках.\nFutures preset intentionally lives in Futures Workspace.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=2, sticky=tk.W, padx=(16, 0))
        mode_card.columnconfigure(2, weight=1)

        params_card = ttk.Frame(spike_root, style="Card.TFrame")
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

        actions_card = ttk.Frame(spike_root, style="Card.TFrame")
        actions_card.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions_card, text="Apply Selected Preset", command=self.apply_selected_strategy).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions_card, text="Apply Spike Params Only", command=self.apply_spike_preset).pack(side=tk.LEFT, padx=6)
        ttk.Label(
            actions_card,
            text="Запуск/остановка Spot Runtime выполняются через Dashboard Home или Spot Workspace.",
            style="Body.TLabel",
        ).pack(side=tk.LEFT, padx=10)

    def _build_settings_tab(self) -> None:
        settings_parent = self.settings_main_tab if self.settings_main_tab is not None else self.settings_tab
        settings_root = ttk.Frame(settings_parent, style="Root.TFrame")
        settings_root.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

        summary_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        summary_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(summary_card, text="Launcher / Profile Diagnostics", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(
            summary_card,
            textvariable=self.settings_diagnostics_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            summary_card,
            textvariable=self.settings_profile_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(
            summary_card,
            textvariable=self.settings_notice_var,
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=3, column=0, sticky=tk.W, pady=(6, 0))
        summary_card.columnconfigure(0, weight=1)

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
        ttk.Label(cfg_card, text="Technical Runtime Settings", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        ttk.Label(cfg_card, text="config path", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.config_var, width=38).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="runtime", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Label(cfg_card, textvariable=self.runtime_python_name_var, style="Body.TLabel").grid(
            row=1, column=3, sticky=tk.W
        )

        ttk.Label(cfg_card, text="execution.mode", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(
            cfg_card,
            textvariable=self.cfg_execution_mode,
            values=["paper", "live"],
            state="readonly",
            width=14,
        ).grid(row=2, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="start_paused", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Checkbutton(cfg_card, variable=self.cfg_start_paused).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="bybit.host", style="Body.TLabel").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_bybit_host, width=28).grid(row=3, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="ws_public_host", style="Body.TLabel").grid(row=3, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_ws_host, width=28).grid(row=3, column=3, sticky=tk.W)

        ttk.Label(
            cfg_card,
            text="Instrument policy knobs, TP/SL, training source and strategy presets live in Spot/Futures workspaces.",
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=820,
        ).grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

        manifest_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        manifest_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(manifest_card, text="Externalized Dashboard Paths", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(
            manifest_card,
            textvariable=self.settings_paths_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 2))
        ttk.Label(
            manifest_card,
            textvariable=self.settings_secrets_var,
            style="Body.TLabel",
            justify=tk.LEFT,
            wraplength=1100,
        ).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        manifest_card.columnconfigure(0, weight=1)

        btn_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        btn_card.pack(fill=tk.X)
        ttk.Button(btn_card, text="Reload From Files", command=self.load_settings).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            btn_card,
            text="Auto-save is ON for .env and technical runtime fields. Instrument-level controls live outside Settings Workspace.",
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

    @staticmethod
    def _telegram_now_ts() -> str:
        return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def _record_telegram_command(self, *, command: str, source: str = "telegram_bot", status: str = "ok") -> None:
        self._telegram_recent_commands.appendleft(
            {
                "ts": self._telegram_now_ts(),
                "command": str(command or "unknown"),
                "source": str(source or "telegram_bot"),
                "status": str(status or "ok"),
            }
        )

    def _record_telegram_alert(self, *, source: str, message: str, status: str = "ok") -> None:
        self._telegram_recent_alerts.appendleft(
            {
                "ts": self._telegram_now_ts(),
                "message": str(message or ""),
                "source": str(source or "telegram_module"),
                "status": str(status or "ok"),
            }
        )

    def _record_telegram_error(self, *, source: str, error: str, status: str = "error") -> None:
        self._telegram_recent_errors.appendleft(
            {
                "ts": self._telegram_now_ts(),
                "error": str(error or "unknown"),
                "source": str(source or "telegram_module"),
                "status": str(status or "error"),
            }
        )

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
                self._enqueue_log("[telegram-dashboard] TELEGRAM_BOT_TOKEN not set; remote control disabled")
                self._record_telegram_error(source="startup", error="configuration_missing_token")
                self._telegram_missing_token_reported = True
            return
        self._telegram_missing_token_reported = False
        if self._telegram_thread is not None and self._telegram_thread.is_alive():
            return

        try:
            from src.botik.control.telegram_gui import GuiTelegramActions, start_gui_telegram_bot_in_thread
        except Exception as exc:
            self._record_telegram_error(source="startup_import", error=str(exc))
            self._enqueue_log(f"[telegram-dashboard] failed to import telegram module: {exc}")
            return

        try:
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
            self._record_telegram_alert(source="startup", message="telegram control bot started", status="ok")
            self._enqueue_log("[telegram-dashboard] control bot started")
        except Exception as exc:
            self._record_telegram_error(source="startup_run", error=str(exc))
            self._enqueue_log(f"[telegram-dashboard] failed to start control bot: {exc}")

    def _git_short_head(self) -> str:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            **dashboard_subprocess_run_kwargs(),
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
            **dashboard_subprocess_run_kwargs(),
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

    def _selected_spot_holding_row(self) -> list[Any] | None:
        tree = self.spot_workspace_holdings_tree
        selected = tree.selection() if tree is not None else ()
        if not selected:
            return None
        item_id = selected[0]
        values = tree.item(item_id, "values") if tree is not None else ()
        row = list(values or [])
        return row if row else None

    @staticmethod
    def _spot_holding_from_row(row: list[Any]) -> dict[str, Any]:
        # Row format is defined in _build_control_tab Spot Holdings Lifecycle table.
        def _f(value: Any) -> float:
            try:
                return float(str(value or "0").strip() or 0.0)
            except (TypeError, ValueError):
                return 0.0

        return {
            "symbol": str(row[1] or "").strip().upper() if len(row) > 1 else "",
            "base_asset": str(row[2] or "").strip().upper() if len(row) > 2 else "",
            "free_qty": _f(row[3]) if len(row) > 3 else 0.0,
            "locked_qty": _f(row[4]) if len(row) > 4 else 0.0,
            "avg_entry_price": str(row[5] or "").strip() if len(row) > 5 else "",
            "hold_reason": str(row[6] or "").strip() if len(row) > 6 else "unknown",
            "recovered": str(row[7] or "").strip().lower() == "yes" if len(row) > 7 else False,
            "strategy_owner": str(row[8] or "").strip() if len(row) > 8 else "unknown",
            "hold_class": str(row[9] or "").strip() if len(row) > 9 else "unknown",
            "position_state": str(row[10] or "").strip() if len(row) > 10 else "unknown",
            "exit_policy": str(row[11] or "").strip() if len(row) > 11 else "unknown",
            "last_seen": str(row[12] or "").strip() if len(row) > 12 else "-",
            "stale": str(row[13] or "").strip().lower() == "yes" if len(row) > 13 else False,
        }

    @staticmethod
    def _spot_policy_allows_sell(policy: str) -> bool:
        return str(policy or "").strip().lower() == "sell_allowed"

    def run_spot_reconcile(self) -> None:
        self._enqueue_log(
            "[spot-workspace] run spot reconcile requested; refreshing snapshot. "
            "Runtime reconciliation is executed by runtime startup/scheduler."
        )
        self.refresh_runtime_snapshot()

    def inspect_selected_spot_holding(self) -> None:
        row = self._selected_spot_holding_row()
        if not row:
            messagebox.showwarning("Spot Workspace", "Select a holding in Spot Holdings Lifecycle.")
            return
        data = self._spot_holding_from_row(row)
        text = (
            f"Symbol: {data['symbol']}\n"
            f"Base Asset: {data['base_asset']}\n"
            f"Free Qty: {data['free_qty']:.8f}\n"
            f"Locked Qty: {data['locked_qty']:.8f}\n"
            f"Avg Entry: {data['avg_entry_price'] or 'unknown'}\n"
            f"Hold Reason: {data['hold_reason']}\n"
            f"Class: {data['hold_class']}\n"
            f"Position State: {data['position_state']}\n"
            f"Exit Policy: {data['exit_policy']}\n"
            f"Recovered: {'yes' if data['recovered'] else 'no'}\n"
            f"Stale: {'yes' if data['stale'] else 'no'}\n"
            f"Strategy Owner: {data['strategy_owner']}\n"
            f"Last Seen: {data['last_seen']}"
        )
        messagebox.showinfo("Spot Workspace - Holding Details", text)

    def copy_selected_spot_holding(self) -> None:
        row = self._selected_spot_holding_row()
        if not row:
            messagebox.showwarning("Spot Workspace", "Select a holding to copy.")
            return
        payload = "\t".join(str(x or "") for x in row)
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self._enqueue_log("[spot-workspace] copied selected holding row")

    def _record_spot_exit_request(self, *, holding: dict[str, Any], decision_type: str, reason: str) -> str:
        raw_cfg = self._load_yaml()
        db_path = self._resolve_db_path(raw_cfg)
        conn = sqlite3.connect(str(db_path))
        try:
            decision_id = insert_spot_exit_decision(
                conn,
                account_type="UNIFIED",
                symbol=str(holding.get("symbol") or ""),
                decision_type=str(decision_type),
                reason=str(reason),
                policy_name=str(holding.get("exit_policy") or "unknown"),
                pnl_pct=None,
                pnl_quote=None,
                payload_json=json.dumps(
                    {
                        "source": "dashboard_spot_workspace",
                        "holding_class": holding.get("hold_class"),
                        "hold_reason": holding.get("hold_reason"),
                        "recovered": bool(holding.get("recovered")),
                        "stale": bool(holding.get("stale")),
                    },
                    ensure_ascii=False,
                ),
                applied=False,
            )
            return decision_id
        finally:
            conn.close()

    def sell_selected_spot_holding(self) -> None:
        row = self._selected_spot_holding_row()
        if not row:
            messagebox.showwarning("Spot Workspace", "Select a holding in Spot Holdings Lifecycle.")
            return
        holding = self._spot_holding_from_row(row)
        if not holding.get("symbol"):
            messagebox.showwarning("Spot Workspace", "Selected holding does not have a valid symbol.")
            return
        if not self._spot_policy_allows_sell(str(holding.get("exit_policy") or "")):
            messagebox.showwarning(
                "Spot Workspace",
                "Sell is blocked by policy for this holding. "
                "Recovered/manual/dust holdings require explicit policy override.",
            )
            return
        if not messagebox.askyesno(
            "Spot Workspace",
            f"Create manual sell request for {holding['symbol']}?\n"
            f"class={holding['hold_class']} policy={holding['exit_policy']}",
        ):
            return
        decision_id = self._record_spot_exit_request(
            holding=holding,
            decision_type="manual_sell_request",
            reason="operator_sell_selected",
        )
        self._enqueue_log(
            f"[spot-workspace] manual sell request recorded: symbol={holding['symbol']} decision_id={decision_id}"
        )
        self.refresh_runtime_snapshot()

    def close_stale_spot_holds(self) -> None:
        tree = self.spot_workspace_holdings_tree
        if tree is None:
            return
        stale_candidates: list[dict[str, Any]] = []
        skipped = 0
        for item_id in tree.get_children():
            row = list(tree.item(item_id, "values") or [])
            if not row:
                continue
            holding = self._spot_holding_from_row(row)
            if not bool(holding.get("stale")):
                continue
            if not self._spot_policy_allows_sell(str(holding.get("exit_policy") or "")):
                skipped += 1
                continue
            stale_candidates.append(holding)
        if not stale_candidates:
            messagebox.showinfo(
                "Spot Workspace",
                f"No stale holdings eligible for close request (protected/none). skipped={skipped}",
            )
            return
        if not messagebox.askyesno(
            "Spot Workspace",
            f"Create close requests for stale holdings?\neligible={len(stale_candidates)} skipped={skipped}",
        ):
            return
        for holding in stale_candidates:
            decision_id = self._record_spot_exit_request(
                holding=holding,
                decision_type="stale_close_request",
                reason="operator_close_stale_holds",
            )
            self._enqueue_log(
                f"[spot-workspace] stale close request recorded: symbol={holding['symbol']} decision_id={decision_id}"
            )
        self.refresh_runtime_snapshot()

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
        instrument = str(row[1] or "").strip().lower() if len(row) > 1 else "unknown"
        if not model_id:
            messagebox.showwarning("Models", "Пустой model_id.")
            return
        if instrument not in {"spot", "futures"}:
            messagebox.showerror("Models", f"Не удалось определить instrument для model_id={model_id}.")
            return
        if not messagebox.askyesno("Models", f"Сделать модель активной?\n{model_id}"):
            return

        raw_cfg = self._load_yaml()
        db_path = self._resolve_db_path(raw_cfg)
        if not db_path.exists():
            messagebox.showerror("Models", f"DB not found: {db_path}")
            return
        pointer_ok, pointer_msg = write_active_model_pointer(model_id, instrument)
        if not pointer_ok:
            messagebox.showerror("Models", pointer_msg)
            return
        db_ok, db_msg = promote_model_registry_model(db_path, model_id, instrument)
        if not db_ok:
            self._enqueue_log(f"[models] pointer updated but DB legacy flag failed for {model_id}: {db_msg}")
            messagebox.showwarning("Models", f"Active model pointer updated, but legacy DB flag failed:\n{db_msg}")
        self._enqueue_log(f"[models] promoted model_id={model_id} instrument={instrument} | {pointer_msg}")
        self.refresh_runtime_snapshot()

    def _selected_model_registry_rows(self) -> list[list[str]]:
        if self.models_tree is None:
            return []
        rows: list[list[str]] = []
        for item_id in self.models_tree.selection():
            values = [str(v or "") for v in list(self.models_tree.item(item_id, "values") or [])]
            if values:
                rows.append(values)
        return rows

    def open_selected_model_stats(self) -> None:
        rows = self._selected_model_registry_rows()
        if not rows:
            messagebox.showwarning("Models", "Выберите модель в таблице.")
            return
        row = rows[0]
        lines = [
            f"Model: {row[0]}",
            f"Instrument: {row[1] if len(row) > 1 else 'unknown'}",
            f"Policy: {row[2] if len(row) > 2 else 'unknown'}",
            f"Source: {row[3] if len(row) > 3 else 'unknown'}",
            f"Role: {row[4] if len(row) > 4 else 'unknown'}",
            f"Status: {row[5] if len(row) > 5 else 'unknown'}",
            f"Created: {row[6] if len(row) > 6 else '-'}",
            f"Outcomes: {row[7] if len(row) > 7 else '0'}",
            f"WinRate: {row[8] if len(row) > 8 else '0.0%'}",
            f"NetPnL: {row[9] if len(row) > 9 else '0.000000'}",
            f"Edge: {row[10] if len(row) > 10 else '0.000'}",
            f"Artifact: {row[11] if len(row) > 11 else '-'}",
        ]
        messagebox.showinfo("Model Stats", "\n".join(lines))

    def compare_selected_models(self) -> None:
        rows = self._selected_model_registry_rows()
        if len(rows) < 2:
            messagebox.showwarning("Models", "Выберите минимум две модели для сравнения.")
            return
        left = rows[0]
        right = rows[1]
        comparison = build_model_registry_comparison(
            {
                "model_id": left[0] if len(left) > 0 else "left",
                "instrument": left[1] if len(left) > 1 else "unknown",
                "policy": left[2] if len(left) > 2 else "unknown",
                "source_mode": left[3] if len(left) > 3 else "unknown",
                "role": left[4] if len(left) > 4 else "unknown",
                "status": left[5] if len(left) > 5 else "unknown",
                "created": left[6] if len(left) > 6 else "-",
                "outcomes": left[7] if len(left) > 7 else "0",
                "win_rate": _parse_win_rate_fraction(left[8] if len(left) > 8 else "0%"),
                "net_pnl": left[9] if len(left) > 9 else "0.000000",
                "edge": left[10] if len(left) > 10 else "0.000",
            },
            {
                "model_id": right[0] if len(right) > 0 else "right",
                "instrument": right[1] if len(right) > 1 else "unknown",
                "policy": right[2] if len(right) > 2 else "unknown",
                "source_mode": right[3] if len(right) > 3 else "unknown",
                "role": right[4] if len(right) > 4 else "unknown",
                "status": right[5] if len(right) > 5 else "unknown",
                "created": right[6] if len(right) > 6 else "-",
                "outcomes": right[7] if len(right) > 7 else "0",
                "win_rate": _parse_win_rate_fraction(right[8] if len(right) > 8 else "0%"),
                "net_pnl": right[9] if len(right) > 9 else "0.000000",
                "edge": right[10] if len(right) > 10 else "0.000",
            },
        )
        lines = [
            f"Left:  {left[0]} | role={left[4] if len(left) > 4 else 'unknown'} | outcomes={left[7] if len(left) > 7 else '0'} | win={left[8] if len(left) > 8 else '0.0%'} | pnl={left[9] if len(left) > 9 else '0.000000'}",
            f"Right: {right[0]} | role={right[4] if len(right) > 4 else 'unknown'} | outcomes={right[7] if len(right) > 7 else '0'} | win={right[8] if len(right) > 8 else '0.0%'} | pnl={right[9] if len(right) > 9 else '0.000000'}",
            "",
            f"Verdict: {comparison.get('summary', 'hold / no clear winner')}",
            f"Why: {comparison.get('reason_line', 'metrics too close or insufficient data')}",
            f"Scores: left={comparison.get('left_score', '0')} right={comparison.get('right_score', '0')}",
            "",
            "Champion selection stays externalized through active_models.yaml.",
        ]
        messagebox.showinfo("Compare Models", "\n".join(lines))

    def copy_selected_model_artifact(self) -> None:
        rows = self._selected_model_registry_rows()
        if not rows:
            messagebox.showwarning("Models", "Выберите модель в таблице.")
            return
        artifact = rows[0][11] if len(rows[0]) > 11 else ""
        artifact = str(artifact or "").strip()
        if not artifact or artifact == "-":
            messagebox.showwarning("Models", "Для выбранной модели нет artifact path.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(artifact)
        except Exception as exc:
            messagebox.showerror("Models", f"Не удалось скопировать artifact path:\n{exc}")
            return
        self._enqueue_log(f"[models] artifact copied: {artifact}")

    def _paper_workspace_unsupported_action(self, action_name: str) -> None:
        message = (
            f"{action_name} is not supported in the current release.\n\n"
            "Futures Paper Workspace stays read-only until the dedicated paper execution lifecycle "
            "is separated from training and evaluation."
        )
        self._enqueue_log(
            f"[futures-paper] {action_name.lower().replace(' ', '_')} unsupported: read-only evaluator workspace"
        )
        messagebox.showinfo("Futures Paper Workspace", message)

    def close_selected_paper_position(self) -> None:
        if self.futures_paper_positions_tree is None:
            return
        if not self.futures_paper_positions_tree.selection():
            messagebox.showwarning("Futures Paper Workspace", "Выберите paper position в таблице.")
            return
        self._paper_workspace_unsupported_action("Close Selected Paper Position")

    def close_all_paper_positions(self) -> None:
        self._paper_workspace_unsupported_action("Close All Paper Positions")

    def reset_paper_session(self) -> None:
        self._paper_workspace_unsupported_action("Reset Paper Session")

    def _telegram_status_text_ui(self) -> str:
        current_version = get_app_version_label()
        mode = self._load_execution_mode()
        running_modes = self._running_trading_modes()
        running_txt = ",".join(running_modes) if running_modes else "none"
        return (
            "Dashboard shell supervisor:\n"
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
        self.root.title(f"Botik Dashboard {self.app_version}")
        self.title_label.config(text=f"Botik Dashboard Shell {self.app_version}")
        self.version_label.config(text=f"app.version: {self.app_version}")
        self._enqueue_log(f"[ui] app.version updated -> {self.app_version}")

    def telegram_status_text(self) -> str:
        self._record_telegram_command(command="/status", source="telegram_bot")
        return str(self._invoke_on_ui_thread(self._telegram_status_text_ui))

    def telegram_balance_text(self) -> str:
        self._record_telegram_command(command="/balance", source="telegram_bot")
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
        self._record_telegram_command(command="/orders", source="telegram_bot")
        snapshot = self._invoke_on_ui_thread(self._load_runtime_snapshot)
        rows = list(snapshot.get("open_orders_rows") or [])
        lines = [f"Активные ордера: {len(rows)}"]
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
        self._record_telegram_command(command="/starttrading", source="telegram_bot")
        result = str(self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False)))
        self._record_telegram_alert(source="telegram_bot", message="start trading requested", status="ok")
        return result

    def telegram_stop_trading(self) -> str:
        self._record_telegram_command(command="/stoptrading", source="telegram_bot")
        result = str(self._invoke_on_ui_thread(self._stop_trading_impl))
        self._record_telegram_alert(source="telegram_bot", message="stop trading requested", status="ok")
        return result

    def telegram_pull_updates(self) -> str:
        self._record_telegram_command(command="/pull", source="telegram_bot")
        ok, msg = self._git_pull_ff_only()
        if self._running_trading_modes():
            msg += "\nTrading уже запущен на старой версии. Нужен рестарт для применения обновлений."
        if ok:
            self._record_telegram_alert(source="telegram_bot", message="pull completed", status="ok")
            return msg
        err = f"Ошибка обновления:\n{msg}"
        self._record_telegram_error(source="telegram_bot", error=err)
        return err

    def telegram_restart_soft(self) -> str:
        self._record_telegram_command(command="/restartsoft", source="telegram_bot")
        lines: list[str] = []
        ok_cancel_before, msg_cancel_before = self._cancel_open_orders_best_effort()
        lines.append(f"[1/4] cancel before stop: {msg_cancel_before}")
        lines.append(f"[2/4] {self._invoke_on_ui_thread(self._stop_trading_impl)}")
        ok_cancel_after, msg_cancel_after = self._cancel_open_orders_best_effort()
        lines.append(f"[3/4] cancel after stop: {msg_cancel_after}")
        lines.append(f"[4/4] {self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False))}")
        if not ok_cancel_before or not ok_cancel_after:
            lines.append("Внимание: cancel_all не полностью успешен, проверьте open orders.")
        result = "\n".join(lines)
        if not ok_cancel_before or not ok_cancel_after:
            self._record_telegram_error(source="telegram_bot", error="restart_soft_cancel_not_fully_successful")
        else:
            self._record_telegram_alert(source="telegram_bot", message="restart soft completed", status="ok")
        return result

    def telegram_restart_hard(self) -> str:
        self._record_telegram_command(command="/restarthard", source="telegram_bot")
        lines: list[str] = []
        ok_pull, pull_msg = self._git_pull_ff_only()
        lines.append(f"[1/3] update: {pull_msg}")
        lines.append(f"[2/3] {self._invoke_on_ui_thread(self._stop_trading_impl)}")
        lines.append(f"[3/3] {self._invoke_on_ui_thread(lambda: self._start_trading_impl(interactive=False))}")
        if not ok_pull:
            lines.append("Обновление не применилось, запущена текущая локальная версия.")
            self._record_telegram_error(source="telegram_bot", error="restarthard_update_failed")
        else:
            self._record_telegram_alert(source="telegram_bot", message="restart hard completed", status="ok")
        return "\n".join(lines)

    @staticmethod
    def _detect_log_level(text: str) -> str:
        return detect_dashboard_log_level(text)

    @staticmethod
    def _detect_log_pair(text: str) -> str:
        return detect_dashboard_log_pair(text)

    def _log_matches_full_filters(self, text: str) -> bool:
        return dashboard_log_matches_filters(
            str(text or ""),
            level_filter=str(self.log_filter_level_var.get() or "ALL"),
            pair_filter=str(self.log_filter_pair_var.get() or "ALL"),
            channel_filter=str(self.log_filter_channel_var.get() or "ALL"),
            instrument_filter=str(self.log_filter_instrument_var.get() or "ALL"),
            query_filter=str(self.log_filter_query_var.get() or ""),
        )

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
        self.log_filter_channel_var.set("ALL")
        self.log_filter_instrument_var.set("ALL")
        self.log_filter_level_var.set("ALL")
        self.log_filter_pair_var.set("ALL")
        self.log_filter_query_var.set("")
        self._on_log_filter_changed()

    def open_logs_workspace(
        self,
        *,
        channel: str = "ALL",
        instrument: str = "ALL",
        level: str = "ALL",
        query: str = "",
    ) -> None:
        self.log_filter_channel_var.set(str(channel or "ALL").upper() if str(channel or "ALL").upper() == "ALL" else str(channel or "").lower())
        self.log_filter_instrument_var.set(
            str(instrument or "ALL").upper() if str(instrument or "ALL").upper() == "ALL" else str(instrument or "").lower()
        )
        self.log_filter_level_var.set(str(level or "ALL").upper())
        self.log_filter_pair_var.set("ALL")
        self.log_filter_query_var.set(str(query or ""))
        self._open_workspace(self.logs_tab)
        self._on_log_filter_changed()

    def open_spot_logs_workspace(self) -> None:
        self.open_logs_workspace(channel="spot", instrument="spot")

    def open_futures_logs_workspace(self) -> None:
        self.open_logs_workspace(instrument="futures")

    def open_telegram_logs_workspace(self) -> None:
        self.open_logs_workspace(channel="telegram", instrument="telegram")

    def open_ops_logs_workspace(self) -> None:
        self.open_logs_workspace(channel="ops", instrument="ops")

    def open_error_logs_workspace(self) -> None:
        self.open_logs_workspace(level="ERROR")

    def open_ops_issues_view(self) -> None:
        self._open_workspace(self.statistics_tab)
        if self.ops_domain_notebook is not None and self.ops_issues_frame is not None:
            try:
                self.ops_domain_notebook.select(self.ops_issues_frame)
            except Exception:
                pass

    def open_ops_futures_positions_view(self) -> None:
        self._open_workspace(self.statistics_tab)
        if self.ops_domain_notebook is not None and self.ops_futures_positions_frame is not None:
            try:
                self.ops_domain_notebook.select(self.ops_futures_positions_frame)
            except Exception:
                pass

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
        exec_mode = self._load_execution_mode()
        self.mode_label.config(text=f"execution.mode: {exec_mode}")
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
            ml_mode = str(self.ml_runtime_mode or "bootstrap").strip().lower()
            if ml_mode == "bootstrap":
                self.ml_training_state_var.set("bootstrap")
            elif ml_mode == "online":
                self.ml_training_state_var.set("online")
            elif ml_mode == "predict":
                self.ml_training_state_var.set("predict")
            else:
                self.ml_training_state_var.set("training")
            if not self._ml_progress_running and self.ml_progress is not None:
                self.ml_progress.start(9)
                self._ml_progress_running = True
        else:
            if self._ml_progress_running and self.ml_progress is not None:
                self.ml_progress.stop()
                self._ml_progress_running = False
            if self.ml.running and self.ml_training_paused:
                self.ml_training_state_var.set("paused")
            elif self.ml.state == "error":
                self.ml_training_state_var.set("error")
            else:
                self.ml_training_state_var.set("stopped")
        telegram_running = bool(self._telegram_thread is not None and self._telegram_thread.is_alive())
        telegram_state = "RUNNING" if telegram_running else ("DISABLED (no token)" if self._telegram_missing_token_reported else "STOPPED")
        spot_modes_running = filter_dashboard_strategy_modes(running_modes, "spot")
        spot_mode_set = set(filter_dashboard_strategy_modes(tuple(self.trading_processes.keys()), "spot"))
        spot_procs = [proc for mode, proc in self.trading_processes.items() if mode in spot_mode_set]
        if any(proc.running for proc in spot_procs):
            spot_state = "running"
        elif any(proc.state == "error" for proc in spot_procs):
            spot_state = "error"
        else:
            spot_state = "stopped"
        self.dashboard_spot_status_var.set(
            f"Spot: {spot_state.upper()} | modes={','.join(spot_modes_running) if spot_modes_running else '-'} | execution={exec_mode}"
        )
        self.dashboard_futures_status_var.set(
            f"Futures: training={self._status_text(self.ml)} | state={self.ml_training_state_var.get()} | execution=research-only"
        )
        self.dashboard_telegram_status_var.set(f"Telegram: {telegram_state}")
        self.dashboard_ops_status_var.set(str(self.reconciliation_status_var.get()))
        self._refresh_telegram_workspace_text()
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
        ops_sections = build_dashboard_ops_workspace_sections(
            ops_status=ops_status,
            runtime_caps=runtime_caps,
            trading_state=self._trading_group_state(),
            running_modes=self._running_trading_modes(),
            ml_state=str(self.ml.state or "stopped"),
            telegram_state=("running" if bool(self._telegram_thread is not None and self._telegram_thread.is_alive()) else "stopped"),
            db_path=db_path,
        )
        release_manifest = load_dashboard_release_manifest()
        release_panel = format_dashboard_release_panel(release_manifest)
        release_sections = build_dashboard_release_home_sections(release_manifest)
        spot_workspace = load_spot_workspace_read_model(db_path, account_type="UNIFIED", limit=400)
        futures_training_workspace = load_futures_training_workspace_read_model(
            db_path,
            raw_cfg=raw_cfg,
            release_manifest=release_manifest,
            ml_running=bool(self.ml.running),
            ml_paused=bool(self.ml_training_paused),
            ml_process_state=str(self.ml.state),
            training_mode=ml_mode,
        )
        futures_paper_workspace = load_futures_paper_workspace_read_model(
            db_path,
            release_manifest=release_manifest,
            limit=400,
        )
        dashboard_home_sections = build_dashboard_home_instrument_sections(
            raw_cfg=raw_cfg,
            release_manifest=release_manifest,
            spot_workspace=spot_workspace,
            futures_training_workspace=futures_training_workspace,
            futures_paper_workspace=futures_paper_workspace,
            exec_mode=mode,
        )
        model_registry_workspace = load_model_registry_workspace_read_model(
            db_path,
            release_manifest=release_manifest,
            limit=400,
        )
        try:
            recent_log_lines = list(self._log_messages)[-240:]
        except RuntimeError:
            recent_log_lines = []
        telegram_workspace = load_telegram_workspace_read_model(
            raw_cfg=raw_cfg,
            env_data=env_data,
            release_manifest=release_manifest,
            thread_running=bool(self._telegram_thread is not None and self._telegram_thread.is_alive()),
            missing_token_reported=bool(self._telegram_missing_token_reported),
            runtime_capabilities=runtime_caps,
            recent_commands=list(self._telegram_recent_commands),
            recent_alerts=list(self._telegram_recent_alerts),
            recent_errors=list(self._telegram_recent_errors),
            log_lines=recent_log_lines,
        )
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
            active_tab = "home"
        now_mono = time.monotonic()
        heavy_due = (now_mono - float(self._last_heavy_refresh_ts)) >= float(self._heavy_refresh_min_interval_sec)
        need_heavy_refresh = heavy_due or active_tab in {"ops", "model_registry", "futures_paper"}
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
            model_rows = list(model_registry_workspace.get("rows") or [])
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
            "open_orders_count": int(spot_workspace.get("open_orders_count") or 0),
            "open_orders_rows": [],
            "spot_workspace_open_orders_rows": list(spot_workspace.get("open_orders_rows") or []),
            "spot_workspace_holdings_rows": list(spot_workspace.get("holdings_rows") or []),
            "spot_workspace_fills_rows": list(spot_workspace.get("fills_rows") or []),
            "spot_workspace_exit_rows": list(spot_workspace.get("exit_decisions_rows") or []),
            "spot_workspace_summary_line": (
                "Spot runtime={runtime} | holdings={holdings} (recovered={recovered}, stale={stale}) | "
                "open_orders={orders} | last_reconcile={reconcile} | last_error={error}"
            ).format(
                runtime=str(spot_workspace.get("runtime_status") or "unknown"),
                holdings=int(spot_workspace.get("holdings_count") or 0),
                recovered=int(spot_workspace.get("recovered_holdings_count") or 0),
                stale=int(spot_workspace.get("stale_holdings_count") or 0),
                orders=int(spot_workspace.get("open_orders_count") or 0),
                reconcile=str(spot_workspace.get("last_reconcile") or "-"),
                error=str(spot_workspace.get("last_error") or "-"),
            ),
            "spot_workspace_policy_line": (
                "Policy classes: strategy-owned={strategy} | manual/imported={manual} | recovered={recovered} | "
                "stale={stale}. Protected holdings are not sold automatically."
            ).format(
                strategy=int(spot_workspace.get("strategy_owned_count") or 0),
                manual=int(spot_workspace.get("manual_holdings_count") or 0),
                recovered=int(spot_workspace.get("recovered_holdings_count") or 0),
                stale=int(spot_workspace.get("stale_holdings_count") or 0),
            ),
            "futures_training_summary_line": (
                "status={status} | symbol={symbol} timeframe={timeframe} | dataset_range={dataset_range} | "
                "best_checkpoint={best_cp} | latest_checkpoint={latest_cp} | last_error={last_error}"
            ).format(
                status=str(futures_training_workspace.get("training_runtime_status") or "unknown"),
                symbol=str(futures_training_workspace.get("active_symbol") or "unknown"),
                timeframe=str(futures_training_workspace.get("active_timeframe") or "not available"),
                dataset_range=str(futures_training_workspace.get("active_dataset_range") or "not available"),
                best_cp=str(futures_training_workspace.get("best_checkpoint") or "not available"),
                latest_cp=str(futures_training_workspace.get("latest_checkpoint") or "not available"),
                last_error=str(futures_training_workspace.get("last_error") or "not available"),
            ),
            "futures_dataset_summary_line": (
                "candles_source={source} | dataset_prepared={prepared} | rows={rows} windows={windows} | "
                "candidate_events={events} outcomes={outcomes}"
            ).format(
                source=str(futures_training_workspace.get("candles_source") or "unknown"),
                prepared=str(futures_training_workspace.get("dataset_prepared") or "no"),
                rows=int(futures_training_workspace.get("dataset_rows") or 0),
                windows=int(futures_training_workspace.get("dataset_windows_count") or 0),
                events=int(futures_training_workspace.get("candidate_events_count") or 0),
                outcomes=int(futures_training_workspace.get("outcomes_count") or 0),
            ),
            "futures_pipeline_summary_line": (
                "features={features} labels={labels} | recipe={recipe} | last_prepared={prepared_at} | "
                "last_failure={failure}"
            ).format(
                features=str(futures_training_workspace.get("features_prepared") or "no"),
                labels=str(futures_training_workspace.get("labels_prepared") or "no"),
                recipe=str(futures_training_workspace.get("active_recipe") or "unknown"),
                prepared_at=str(futures_training_workspace.get("pipeline_last_prepared_at") or "-"),
                failure=str(futures_training_workspace.get("pipeline_last_failure") or "not available"),
            ),
            "futures_run_progress_line": (
                "run_status={run_status} | epoch={epoch} step={step} | train_loss={train_loss} val_loss={val_loss} | "
                "started={started} updated={updated} duration={duration}"
            ).format(
                run_status=str(futures_training_workspace.get("run_status") or "unknown"),
                epoch=str(futures_training_workspace.get("run_epoch") or "not available"),
                step=str(futures_training_workspace.get("run_step") or "not available"),
                train_loss=str(futures_training_workspace.get("train_loss") or "not available"),
                val_loss=str(futures_training_workspace.get("val_loss") or "not available"),
                started=str(futures_training_workspace.get("run_started_at") or "-"),
                updated=str(futures_training_workspace.get("run_updated_at") or "-"),
                duration=str(futures_training_workspace.get("run_duration") or "not available"),
            ),
            "futures_eval_summary_line": (
                "evaluation={evaluation} | best_metric={best_metric} @ {last_eval} | "
                "active_futures_model={active_model} | engine={engine} | profile={profile}"
            ).format(
                evaluation=str(futures_training_workspace.get("evaluation_summary") or "not available"),
                best_metric=str(futures_training_workspace.get("best_metric") or "not available"),
                last_eval=str(futures_training_workspace.get("last_evaluation_ts") or "-"),
                active_model=str(futures_training_workspace.get("active_futures_model_version") or "unknown"),
                engine=str(futures_training_workspace.get("training_engine_version") or "unknown"),
                profile=str(release_manifest.get("active_config_profile") or "unknown"),
            ),
            "futures_checkpoints_summary_line": (
                "checkpoints={count} | best={best_cp} | latest={latest_cp} | "
                "active_futures_model={active_model}"
            ).format(
                count=len(list(futures_training_workspace.get("checkpoints_rows") or [])),
                best_cp=str(futures_training_workspace.get("best_checkpoint") or "not available"),
                latest_cp=str(futures_training_workspace.get("latest_checkpoint") or "not available"),
                active_model=str(futures_training_workspace.get("active_futures_model_version") or "unknown"),
            ),
            "futures_training_checkpoints_rows": list(futures_training_workspace.get("checkpoints_rows") or []),
            "futures_paper_summary_line": str(futures_paper_workspace.get("summary_line") or "Paper Results: n/a"),
            "futures_paper_status_line": str(futures_paper_workspace.get("status_line") or "Paper Status: n/a"),
            "futures_paper_positions_rows": list(futures_paper_workspace.get("positions_rows") or []),
            "futures_paper_orders_rows": list(futures_paper_workspace.get("open_orders_rows") or []),
            "futures_paper_closed_rows": list(futures_paper_workspace.get("closed_results_rows") or []),
            "telegram_workspace_summary_line": (
                "Telegram Status Summary: {line}"
            ).format(
                line=str(telegram_workspace.get("summary_line") or "n/a"),
            ),
            "telegram_workspace_profile_line": (
                "Bot Profile / Connection: {line}"
            ).format(
                line=str(telegram_workspace.get("profile_connection_line") or "n/a"),
            ),
            "telegram_workspace_access_line": (
                "Allowed Chats / Access: {line}"
            ).format(
                line=str(telegram_workspace.get("access_line") or "n/a"),
            ),
            "telegram_workspace_commands_line": (
                "Available Commands ({count}): {line}"
            ).format(
                count=int(telegram_workspace.get("commands_count") or 0),
                line=str(telegram_workspace.get("commands_line") or "not available"),
            ),
            "telegram_workspace_health_line": (
                "Telegram Errors / Health: last_error={last_error} | recent_errors={errors} | recent_alerts={alerts}"
            ).format(
                last_error=str(telegram_workspace.get("last_error") or "not available"),
                errors=int(telegram_workspace.get("recent_errors_count") or 0),
                alerts=int(telegram_workspace.get("recent_alerts_count") or 0),
            ),
            "telegram_workspace_capabilities_line": (
                "module_version={module_version} | startup={startup} | {caps}"
            ).format(
                module_version=str(telegram_workspace.get("module_version") or "unknown"),
                startup=str(telegram_workspace.get("startup_status") or "unknown"),
                caps=str(telegram_workspace.get("capability_line") or "capabilities: unknown"),
            ),
            "telegram_workspace_recent_commands_rows": list(telegram_workspace.get("recent_commands_rows") or []),
            "telegram_workspace_recent_alerts_rows": list(telegram_workspace.get("recent_alerts_rows") or []),
            "telegram_workspace_recent_errors_rows": list(telegram_workspace.get("recent_errors_rows") or []),
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
            "models_total": int(model_registry_workspace.get("total_models") or len(model_rows)),
            "model_registry_summary_line": str(model_registry_workspace.get("summary_line") or "total=0"),
            "model_registry_status_line": str(model_registry_workspace.get("status_line") or "selector=active_models.yaml"),
            "dashboard_release_status_line": release_sections["status_line"],
            "dashboard_release_shell_line": release_sections["shell_line"],
            "dashboard_release_components_line": release_sections["components_line"],
            "dashboard_release_models_line": release_sections["models_line"],
            "dashboard_release_manifests_line": (
                f"{release_sections['manifests_line']} | {release_sections['workspace_line']}"
            ),
            "dashboard_balance_summary_line": f"{str('USDT total')} {str('=')} {str('n/a')}",
            "dashboard_pnl_summary_line": f"{float(outcomes_summary.get('sum_net_pnl_quote', 0.0)):.6f} quote",
            "dashboard_profile_summary_line": str(release_manifest.get("active_config_profile") or "unknown"),
            "dashboard_spot_primary_line": str(dashboard_home_sections.get("spot_primary_line") or "Spot primary: n/a"),
            "dashboard_spot_meta_line": str(dashboard_home_sections.get("spot_meta_line") or "Spot meta: n/a"),
            "dashboard_spot_settings_line": str(dashboard_home_sections.get("spot_settings_line") or "Spot settings: n/a"),
            "dashboard_futures_primary_line": str(dashboard_home_sections.get("futures_primary_line") or "Futures primary: n/a"),
            "dashboard_futures_meta_line": str(dashboard_home_sections.get("futures_meta_line") or "Futures meta: n/a"),
            "dashboard_futures_settings_line": str(dashboard_home_sections.get("futures_settings_line") or "Futures settings: n/a"),
            "ops_service_health_line": str(ops_sections.get("service_health_line") or "services: n/a"),
            "ops_reconciliation_line": str(ops_sections.get("reconciliation_line") or "reconciliation: n/a"),
            "ops_protection_line": str(ops_sections.get("protection_line") or "protection: n/a"),
            "ops_db_health_line": str(ops_sections.get("db_health_line") or "db: n/a"),
            "ops_capabilities_line": str(ops_sections.get("capabilities_line") or "capabilities: n/a"),
            "api_status": f"mode={mode}; modes={','.join(enabled_modes)}",
            "updated_at": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
            "runtime_capabilities_status": (
                f"capabilities: recon={runtime_caps.get('reconciliation')} | protection={runtime_caps.get('protection')}"
            ),
            "dashboard_release_panel": release_panel,
            "reconciliation_status_line": (
                f"reconciliation: {ops_status.get('reconciliation_last_status')} @ {ops_status.get('reconciliation_last_timestamp')} "
                f"({ops_status.get('reconciliation_last_trigger')})"
                f" | issues open={ops_status.get('reconciliation_open_issues')} resolved={ops_status.get('reconciliation_resolved_issues')}"
                f" | locks={','.join(list(ops_status.get('reconciliation_lock_symbols') or [])[:3]) or '-'}"
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
            snapshot["open_orders_count"] = int(spot_workspace.get("open_orders_count") or 0)
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
            snapshot["open_orders_count"] = int(spot_workspace.get("open_orders_count") or 0)
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
            snapshot["open_orders_count"] = int(spot_workspace.get("open_orders_count") or 0)
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
        live_data["open_orders_count"] = int(spot_workspace.get("open_orders_count") or 0)
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
            return self._reindex_rows(out, width=11)
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
            return self._reindex_rows(out, width=9)
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
            elif tree is self.futures_paper_closed_tree:
                row_list = list(row)
                result_class = str(row_list[6] if len(row_list) > 6 else "").strip().lower()
                if result_class == "good":
                    tags = ("paper_good",)
                elif result_class == "bad":
                    tags = ("paper_bad",)
                elif result_class == "flat":
                    tags = ("paper_flat",)
            elif tree is self.models_tree:
                row_list = list(row)
                row_text = " | ".join(str(cell or "").lower() for cell in row_list)
                if "champion:" in row_text or "legacy-active" in row_text:
                    tags = ("model_active",)
            tree.insert("", tk.END, values=row, tags=tags)

    def _active_tab_key(self) -> str:
        if self.notebook is None:
            return "home"
        try:
            selected = self.notebook.select()
            widget = self.notebook.nametowidget(selected)
        except Exception:
            return "home"
        if widget is self.home_tab:
            return "home"
        if widget is self.control_tab:
            return "spot"
        if widget is self.futures_tab:
            if self.futures_notebook is not None:
                try:
                    inner = self.futures_notebook.nametowidget(self.futures_notebook.select())
                    if inner is self.futures_paper_tab:
                        return "futures_paper"
                except Exception:
                    pass
            return "futures_training"
        if widget is self.model_registry_tab:
            return "model_registry"
        if widget is self.telegram_tab:
            return "telegram"
        if widget is self.logs_tab:
            return "logs"
        if widget is self.settings_tab:
            return "settings"
        if widget is self.statistics_tab:
            return "ops"
        return "home"

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
        self.dashboard_release_panel_var.set(
            str(snapshot.get("dashboard_release_panel", "Loaded Components / Releases: not loaded"))
        )
        self.dashboard_release_status_var.set(
            str(snapshot.get("dashboard_release_status_line") or "release=missing")
        )
        self.dashboard_release_shell_var.set(
            str(snapshot.get("dashboard_release_shell_line") or "Dashboard Shell: unknown")
        )
        self.dashboard_release_components_var.set(
            str(snapshot.get("dashboard_release_components_line") or "workspace_pack=unknown")
        )
        self.dashboard_release_models_var.set(
            str(snapshot.get("dashboard_release_models_line") or "spot_model=unknown | futures_model=unknown")
        )
        self.dashboard_release_manifests_var.set(
            str(snapshot.get("dashboard_release_manifests_line") or "release=dashboard_release_manifest.yaml")
        )
        self.dashboard_balance_summary_var.set(
            f"{snapshot.get('balance_total', 'n/a')} total | wallet={snapshot.get('balance_wallet', 'n/a')}"
        )
        self.dashboard_pnl_summary_var.set(
            f"{float(snapshot.get('stats_net_pnl_quote', 0.0)):.6f} quote | balance-flow={float(snapshot.get('stats_balance_delta_total', 0.0)):.6f}"
        )
        self.dashboard_profile_summary_var.set(
            f"{snapshot.get('api_status', 'n/a')} | profile={snapshot.get('dashboard_profile_summary_line', 'unknown')}"
        )
        self.ops_service_health_var.set(str(snapshot.get("ops_service_health_line") or "services: n/a"))
        self.ops_reconciliation_var.set(str(snapshot.get("ops_reconciliation_line") or "reconciliation: n/a"))
        self.ops_protection_var.set(str(snapshot.get("ops_protection_line") or "protection: n/a"))
        self.ops_db_health_var.set(str(snapshot.get("ops_db_health_line") or "db: n/a"))
        self.ops_capabilities_var.set(str(snapshot.get("ops_capabilities_line") or "capabilities: n/a"))
        self.reconciliation_status_var.set(str(snapshot.get("reconciliation_status_line", "reconciliation: n/a")))
        self.panel_freshness_var.set(str(snapshot.get("panel_freshness_line", "freshness: n/a")))
        self.futures_protection_status_var.set(
            str(snapshot.get("futures_protection_status_line", "protection: n/a"))
        )
        self.dashboard_spot_primary_var.set(
            str(snapshot.get("dashboard_spot_primary_line") or "Spot primary: n/a")
        )
        self.dashboard_spot_meta_var.set(
            str(snapshot.get("dashboard_spot_meta_line") or "Spot meta: n/a")
        )
        self.dashboard_spot_settings_var.set(
            str(snapshot.get("dashboard_spot_settings_line") or "Spot settings: n/a")
        )
        self.dashboard_futures_primary_var.set(
            str(snapshot.get("dashboard_futures_primary_line") or "Futures primary: n/a")
        )
        self.dashboard_futures_meta_var.set(
            str(snapshot.get("dashboard_futures_meta_line") or "Futures meta: n/a")
        )
        self.dashboard_futures_settings_var.set(
            str(snapshot.get("dashboard_futures_settings_line") or "Futures settings: n/a")
        )
        self.spot_workspace_summary_var.set(str(snapshot.get("spot_workspace_summary_line") or "Spot Summary: n/a"))
        self.spot_workspace_policy_var.set(str(snapshot.get("spot_workspace_policy_line") or "Policy: n/a"))
        self.futures_training_summary_var.set(
            str(snapshot.get("futures_training_summary_line") or "Training Summary: n/a")
        )
        self.futures_dataset_summary_var.set(
            str(snapshot.get("futures_dataset_summary_line") or "Dataset/Candles: n/a")
        )
        self.futures_pipeline_summary_var.set(
            str(snapshot.get("futures_pipeline_summary_line") or "Features/Labels Pipeline: n/a")
        )
        self.futures_run_progress_var.set(
            str(snapshot.get("futures_run_progress_line") or "Training Run Progress: n/a")
        )
        self.futures_eval_summary_var.set(
            str(snapshot.get("futures_eval_summary_line") or "Evaluation Summary: n/a")
        )
        self.futures_checkpoints_summary_var.set(
            str(snapshot.get("futures_checkpoints_summary_line") or "Checkpoints: n/a")
        )
        self.futures_paper_summary_var.set(
            str(snapshot.get("futures_paper_summary_line") or "Paper Results: n/a")
        )
        self.futures_paper_status_var.set(
            str(snapshot.get("futures_paper_status_line") or "Paper Status: n/a")
        )
        self.telegram_workspace_summary_var.set(
            str(snapshot.get("telegram_workspace_summary_line") or "Telegram Status Summary: n/a")
        )
        self.telegram_workspace_profile_var.set(
            str(snapshot.get("telegram_workspace_profile_line") or "Bot Profile / Connection: n/a")
        )
        self.telegram_workspace_access_var.set(
            str(snapshot.get("telegram_workspace_access_line") or "Allowed Chats / Access: n/a")
        )
        self.telegram_workspace_commands_var.set(
            str(snapshot.get("telegram_workspace_commands_line") or "Available Commands: n/a")
        )
        self.telegram_workspace_health_var.set(
            str(snapshot.get("telegram_workspace_health_line") or "Telegram Errors / Health: n/a")
        )
        self.telegram_workspace_capabilities_var.set(
            str(snapshot.get("telegram_workspace_capabilities_line") or "Capabilities: n/a")
        )
        self._set_tree_rows(self.open_orders_tree, list(snapshot.get("spot_workspace_open_orders_rows") or []))
        if self.spot_workspace_holdings_tree is not None:
            self._set_tree_rows(self.spot_workspace_holdings_tree, list(snapshot.get("spot_workspace_holdings_rows") or []))
        if self.spot_workspace_fills_tree is not None:
            self._set_tree_rows(self.spot_workspace_fills_tree, list(snapshot.get("spot_workspace_fills_rows") or []))
        if self.spot_workspace_exit_tree is not None:
            self._set_tree_rows(self.spot_workspace_exit_tree, list(snapshot.get("spot_workspace_exit_rows") or []))
        if self.futures_training_checkpoints_tree is not None:
            self._set_tree_rows(
                self.futures_training_checkpoints_tree,
                list(snapshot.get("futures_training_checkpoints_rows") or []),
            )
        if self.futures_paper_positions_tree is not None:
            self._set_tree_rows(
                self.futures_paper_positions_tree,
                list(snapshot.get("futures_paper_positions_rows") or []),
            )
        if self.futures_paper_orders_tree is not None:
            self._set_tree_rows(
                self.futures_paper_orders_tree,
                list(snapshot.get("futures_paper_orders_rows") or []),
            )
        if self.futures_paper_closed_tree is not None:
            self._set_tree_rows(
                self.futures_paper_closed_tree,
                list(snapshot.get("futures_paper_closed_rows") or []),
            )
        if self.telegram_workspace_commands_tree is not None:
            self._set_tree_rows(
                self.telegram_workspace_commands_tree,
                list(snapshot.get("telegram_workspace_recent_commands_rows") or []),
            )
        if self.telegram_workspace_alerts_tree is not None:
            self._set_tree_rows(
                self.telegram_workspace_alerts_tree,
                list(snapshot.get("telegram_workspace_recent_alerts_rows") or []),
            )
        if self.telegram_workspace_errors_tree is not None:
            self._set_tree_rows(
                self.telegram_workspace_errors_tree,
                list(snapshot.get("telegram_workspace_recent_errors_rows") or []),
            )
        if self.order_history_tree is not None:
            self._set_tree_rows(self.order_history_tree, list(snapshot.get("history_rows") or []))
        if self.stats_history_tree is not None and active_tab == "ops":
            self._set_tree_rows(self.stats_history_tree, list(snapshot.get("history_rows_full") or []))
        if self.stats_balance_tree is not None and active_tab == "ops":
            self._set_tree_rows(self.stats_balance_tree, list(snapshot.get("stats_balance_rows") or []))
        if self.stats_spot_holdings_tree is not None and active_tab == "ops":
            self._set_tree_rows(self.stats_spot_holdings_tree, list(snapshot.get("stats_spot_holdings_rows") or []))
        if self.stats_futures_positions_tree is not None and active_tab == "ops":
            self._set_tree_rows(self.stats_futures_positions_tree, list(snapshot.get("stats_futures_positions_rows") or []))
        if self.stats_futures_orders_tree is not None and active_tab == "ops":
            self._set_tree_rows(self.stats_futures_orders_tree, list(snapshot.get("stats_futures_orders_rows") or []))
        if self.stats_reconciliation_issues_tree is not None and active_tab == "ops":
            self._set_tree_rows(
                self.stats_reconciliation_issues_tree,
                list(snapshot.get("stats_reconciliation_issue_rows") or []),
            )
        if self.models_tree is not None and active_tab == "model_registry":
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
            str(snapshot.get("model_registry_summary_line") or f"total={int(snapshot.get('models_total', 0))}")
        )
        self.models_status_var.set(
            str(snapshot.get("model_registry_status_line") or "selector=active_models.yaml")
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
        if canvas is None:
            return
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
        self._refresh_settings_workspace_summary(raw_cfg=raw, env_data=env_data)
        self._enqueue_log("[settings] loaded from files")

    def save_env(self, show_popup: bool = True) -> bool:
        updates = {k: v.get().strip() for k, v in self.env_vars.items()}
        try:
            _upsert_env(ENV_PATH, updates)
        except Exception as exc:
            if show_popup:
                messagebox.showerror("Save failed", f".env save error:\n{exc}")
            return False
        self._refresh_settings_workspace_summary(env_data=updates)
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

        self._refresh_settings_workspace_summary(raw_cfg=raw)
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

    def apply_futures_research_preset(self) -> None:
        self._flush_autosave()
        ok, msg = self._apply_strategy_preset_impl("futures_spike_reversal", show_popup=True)
        if not ok:
            self._enqueue_log(f"[strategy] {msg}")

    def start_selected_strategy(self) -> None:
        self._flush_autosave()
        mode = self._selected_strategy_mode()
        ok, msg = self._apply_strategy_preset_impl(mode, show_popup=False)
        self._enqueue_log(f"[strategy] {msg}")
        if not ok:
            return
        self._enqueue_log("[strategy] preset applied. Use Dashboard Home quick actions to start runtime.")

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

    def _run_dashboard_service_action_async(
        self,
        action_key: str,
        fn: Callable[[], str],
        *,
        queued_message: str,
    ) -> None:
        if action_key in self._service_actions_inflight:
            self._enqueue_log(f"[ui] action already in progress: {action_key}")
            return
        self._service_actions_inflight.add(action_key)
        self._enqueue_log(f"[ui] {queued_message}")

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                result = f"{action_key} failed: {exc}"
            finally:
                self._service_actions_inflight.discard(action_key)

            def finalize() -> None:
                self._enqueue_log(f"[ui] {result}")
                self.refresh_runtime_snapshot()

            self.root.after(0, finalize)

        threading.Thread(target=worker, daemon=True).start()

    def _start_trading_modes_impl(
        self,
        strategy_modes: list[str] | tuple[str, ...],
        *,
        interactive: bool,
        start_ml: bool,
    ) -> str:
        self._flush_autosave()
        mode = self._load_execution_mode()
        if interactive and mode == "live":
            if not messagebox.askyesno(
                "Live Mode Warning",
                "execution.mode=live. This can place real orders.\nContinue?",
            ):
                return "Start canceled by user."
        selected_modes = self._normalize_strategy_modes(list(strategy_modes))
        if not selected_modes:
            return "Trading start skipped: no enabled modes."
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
            cmd, supported, reason = build_worker_launch_command(
                process_kind="trading",
                launcher_mode=self.launcher_mode,
                python_path=self.python_var.get(),
                config_path=str(cfg_path),
                packaged_executable=self.packaged_executable,
            )
            if not supported or not cmd:
                self._enqueue_log(
                    f"[ui] trading launch skipped for {strategy_mode}: unsupported launcher path ({reason})"
                )
                continue
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

    def _start_trading_impl(self, interactive: bool, start_ml: bool = True) -> str:
        return self._start_trading_modes_impl(
            self._enabled_strategy_modes_from_ui(),
            interactive=interactive,
            start_ml=start_ml,
        )

    def start_trading(self) -> None:
        mode = self._load_execution_mode()
        if mode == "live":
            if not messagebox.askyesno(
                "Live Mode Warning",
                "execution.mode=live. This can place real orders.\nContinue?",
            ):
                self._enqueue_log("[ui] Start canceled by user.")
                return
        self._run_dashboard_service_action_async(
            "start_trading",
            lambda: self._start_trading_impl(interactive=False, start_ml=True),
            queued_message="queued start_trading",
        )

    def _stop_trading_modes_impl(
        self,
        strategy_modes: list[str] | tuple[str, ...],
        *,
        stop_ml: bool,
    ) -> str:
        selected_modes = self._normalize_strategy_modes(list(strategy_modes))
        stopped_modes: list[str] = []
        for mode, proc in self.trading_processes.items():
            if selected_modes and mode not in selected_modes:
                continue
            if proc.stop():
                stopped_modes.append(mode)
        ml_msg = ""
        if stop_ml:
            ml_msg = self._stop_ml_impl()
        stopped_txt = ",".join(stopped_modes) if stopped_modes else "none"
        if stop_ml:
            return f"Trade stop: stopped=[{stopped_txt}]. {ml_msg}"
        return f"Trading stop: stopped=[{stopped_txt}]."

    def _stop_trading_impl(self, stop_ml: bool = True) -> str:
        return self._stop_trading_modes_impl(self._enabled_strategy_modes_from_ui(), stop_ml=stop_ml)

    def stop_trading(self) -> None:
        self._run_dashboard_service_action_async(
            "stop_trading",
            lambda: self._stop_trading_impl(stop_ml=True),
            queued_message="queued stop_trading",
        )

    def start_spot_runtime(self) -> None:
        mode = self._load_execution_mode()
        if mode == "live":
            if not messagebox.askyesno(
                "Live Mode Warning",
                "execution.mode=live. This can place real orders.\nContinue?",
            ):
                self._enqueue_log("[ui] Spot start canceled by user.")
                return
        spot_modes = filter_dashboard_strategy_modes(self._enabled_strategy_modes_from_ui(), "spot")
        self._run_dashboard_service_action_async(
            "start_spot_runtime",
            lambda modes=spot_modes: self._start_trading_modes_impl(modes, interactive=False, start_ml=False),
            queued_message="queued start_spot_runtime",
        )

    def stop_spot_runtime(self) -> None:
        spot_modes = filter_dashboard_strategy_modes(self._enabled_strategy_modes_from_ui(), "spot")
        self._run_dashboard_service_action_async(
            "stop_spot_runtime",
            lambda modes=spot_modes: self._stop_trading_modes_impl(modes, stop_ml=False),
            queued_message="queued stop_spot_runtime",
        )

    def _start_ml_impl(self) -> str:
        self._flush_autosave()
        raw_cfg = self._load_yaml()
        ml_mode = str(((raw_cfg.get("ml") or {}).get("mode") or "bootstrap")).strip().lower()
        if ml_mode not in {"bootstrap", "train", "predict", "online"}:
            ml_mode = "bootstrap"
        cmd, supported, reason = build_worker_launch_command(
            process_kind="ml",
            launcher_mode=self.launcher_mode,
            python_path=self.python_var.get(),
            config_path=self.config_var.get(),
            packaged_executable=self.packaged_executable,
            ml_mode=ml_mode,
        )
        if not supported or not cmd:
            msg = f"ML launch unsupported in current mode ({reason})."
            self._enqueue_log(f"[ui] {msg}")
            return msg
        started = self.ml.start(cmd, ROOT_DIR)
        return "ML process started." if started else "ML already running."

    def _stop_ml_impl(self) -> str:
        stopped = self.ml.stop()
        return "ML process stopped." if stopped else "ML already stopped."

    def start_ml(self) -> None:
        self._run_dashboard_service_action_async(
            "start_ml",
            self._start_ml_impl,
            queued_message="queued start_ml",
        )

    def stop_ml(self) -> None:
        self._run_dashboard_service_action_async(
            "stop_ml",
            self._stop_ml_impl,
            queued_message="queued stop_ml",
        )

    def start_training(self) -> None:
        self.start_ml()

    def stop_training(self) -> None:
        self.stop_ml()

    def pause_training(self) -> None:
        def toggle_pause() -> str:
            flag = self._training_pause_flag_path()
            if flag.exists():
                try:
                    flag.unlink()
                except OSError as exc:
                    return f"failed to resume training: {exc}"
                return "training resumed"
            try:
                flag.write_text("paused\n", encoding="utf-8")
            except OSError as exc:
                return f"failed to pause training: {exc}"
            return "training paused"

        self._run_dashboard_service_action_async(
            "pause_training",
            toggle_pause,
            queued_message="queued pause_training toggle",
        )

    def _run_training_workspace_task(self, *, label: str, cmd: list[str]) -> None:
        if self.launcher_mode == "packaged":
            self._enqueue_log(
                f"[futures-training] {label}: not available in packaged Dashboard Shell one-shot mode. "
                "Use source mode or run background training process."
            )
            return
        threading.Thread(target=self._run_one_shot, args=(cmd,), daemon=True).start()

    def prepare_futures_training_dataset(self) -> None:
        self._flush_autosave()
        raw_cfg = self._load_yaml()
        db_path = self._resolve_db_path(raw_cfg)
        out_csv = ROOT_DIR / "data" / "ml" / "trades_dataset.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.python_var.get(),
            "tools/export_trade_dataset.py",
            "--config",
            self.config_var.get(),
            "--db-path",
            str(db_path),
            "--out-csv",
            str(out_csv),
            "--out-parquet",
            "",
        ]
        self._enqueue_log("[futures-training] prepare dataset requested")
        self._run_training_workspace_task(label="prepare_dataset", cmd=cmd)

    def build_futures_features_labels(self) -> None:
        self._flush_autosave()
        cmd = [
            self.python_var.get(),
            "-m",
            "ml_service.run_loop",
            "--config",
            self.config_var.get(),
            "--mode",
            "bootstrap",
            "--train-once",
        ]
        self._enqueue_log("[futures-training] build features/labels requested")
        self._run_training_workspace_task(label="build_features_labels", cmd=cmd)

    def run_futures_training_evaluation(self) -> None:
        self._flush_autosave()
        cmd = [
            self.python_var.get(),
            "-m",
            "ml_service.run_loop",
            "--config",
            self.config_var.get(),
            "--mode",
            "predict",
            "--predict-once",
        ]
        self._enqueue_log("[futures-training] evaluation run requested")
        self._run_training_workspace_task(label="run_evaluation", cmd=cmd)

    def open_futures_checkpoints_dir(self) -> None:
        raw_cfg = self._load_yaml()
        model_dir = Path(str((raw_cfg.get("ml") or {}).get("model_dir") or "data/models"))
        if not model_dir.is_absolute():
            model_dir = ROOT_DIR / model_dir
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(model_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(model_dir)], cwd=str(ROOT_DIR))
            else:
                subprocess.Popen(["xdg-open", str(model_dir)], cwd=str(ROOT_DIR))
            self._enqueue_log(f"[futures-training] opened checkpoints dir: {model_dir}")
        except Exception as exc:
            self._enqueue_log(f"[futures-training] open checkpoints dir failed: {exc}")

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
            "4) Model Registry Workspace\n"
            "- Показывает champion/challenger registry: role, policy, source, outcomes, net PnL и artifact path.\n"
            "- Можно вручную активировать выбранную модель.\n\n"
            "5) Strategies tab\n"
            "- Здесь настраиваются пресеты; запуск Spot Runtime делается из Dashboard Home.\n"
            "- Для Spot Workspace доступны чекбоксы мульти-режима.\n"
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
            **dashboard_subprocess_popen_kwargs(),
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

