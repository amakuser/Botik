"""
SystemMixin — snapshot, system status, logs, and diagnostics.

Public API: get_snapshot, get_version_info, get_system_status, get_logs.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from .api_helpers import CONFIG_PATH, _load_yaml, _read_env_map, _resolve_db_path

log = logging.getLogger("botik.webview")


class SystemMixin:
    """Mixin providing system-level read methods to DashboardAPI."""

    # ── Internal helpers ──────────────────────────────────────

    def _read_pnl_chart(self, conn: sqlite3.Connection, days: int = 7) -> list[float]:
        try:
            rows = conn.execute(
                "SELECT DATE(finished_at_utc) AS d, SUM(net_pnl_quote) "
                "FROM outcomes GROUP BY d ORDER BY d DESC LIMIT ?",
                (days,),
            ).fetchall()
            vals = [float(r[1] or 0) for r in reversed(rows)]
            while len(vals) < 7:
                vals.insert(0, 0.0)
            return vals[-7:]
        except Exception:
            return [0.0] * 7

    def _read_diag_rows(self, conn: sqlite3.Connection, raw_cfg: dict) -> list[dict]:
        rows: list[dict] = []
        # DB
        try:
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
            rows.append({"key": "База данных", "val": "SQLite OK", "state": "ok"})
        except Exception:
            rows.append({"key": "База данных", "val": "ошибка", "state": "warn"})
        # Config
        cfg_ok = CONFIG_PATH.exists()
        rows.append({
            "key": "Config",
            "val": "config.yaml" if cfg_ok else "не найден",
            "state": "ok" if cfg_ok else "warn",
        })
        # Mode
        mode = str((raw_cfg.get("execution") or {}).get("mode") or "paper")
        rows.append({"key": "Режим", "val": mode.upper(), "state": "ok"})
        # Trading processes
        running = self._running_modes()  # type: ignore[attr-defined]
        rows.append({
            "key": "Торговля",
            "val": f"running: {', '.join(running)}" if running else "остановлена",
            "state": "ok" if running else "warn",
        })
        # ML
        rows.append({
            "key": "ML обучение",
            "val": self._ml_process.state,  # type: ignore[attr-defined]
            "state": "ok" if self._ml_process.state == "running" else "warn",  # type: ignore[attr-defined]
        })
        # Reconciliation
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM reconciliation_issues WHERE resolved_at_utc IS NULL"
            ).fetchone()
            issues = int((dict(row).get("cnt") or 0)) if row else 0
            rows.append({
                "key": "Сверка",
                "val": "Нет расхождений" if issues == 0 else f"{issues} проблем",
                "state": "ok" if issues == 0 else "warn",
            })
        except Exception:
            rows.append({"key": "Сверка", "val": "n/a", "state": "warn"})
        return rows

    def _read_recent_errors(self, conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
        try:
            if not self._table_exists(conn, "app_logs"):  # type: ignore[attr-defined]
                return []
            rows = conn.execute(
                "SELECT channel, level, message, recorded_at_utc FROM app_logs "
                "WHERE level IN ('ERROR','WARNING') "
                "ORDER BY recorded_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"channel": r[0], "level": r[1], "message": r[2], "ts": r[3]} for r in rows]
        except Exception:
            return []

    def _read_db_stats(self, conn: sqlite3.Connection) -> list[dict]:
        tables = [
            ("price_history",        "OHLCV свечи"),
            ("futures_paper_trades", "Futures сделки"),
            ("futures_positions",    "Futures позиции"),
            ("spot_holdings",        "Spot холдинги"),
            ("spot_orders",          "Spot ордера"),
            ("labeled_samples",      "ML образцы"),
            ("ml_training_runs",     "ML запуски"),
            ("app_logs",             "Логи"),
        ]
        result: list[dict] = []
        for tname, label in tables:
            try:
                row   = conn.execute(f"SELECT COUNT(*) AS cnt FROM {tname}").fetchone()
                count = int((dict(row).get("cnt") or 0)) if row else 0
            except Exception:
                count = -1
            result.append({"table": tname, "label": label, "count": count})
        return result

    def _read_pipeline_status(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Quick status for the home-page pipeline widget (Data → Train → Trade)."""
        result: dict[str, Any] = {
            "data_futures_ready": 0,
            "data_spot_ready":    0,
            "data_total":         0,
            "models_futures":     "missing",
            "models_spot":        "missing",
            "ml_futures_state":   self._ml_futures_process.state,   # type: ignore[attr-defined]
            "ml_spot_state":      self._ml_spot_process.state,       # type: ignore[attr-defined]
            "backfill_state":     self._backfill_process.state,      # type: ignore[attr-defined]
            "livedata_state":     self._livedata_process.state,      # type: ignore[attr-defined]
        }
        # ── Data readiness (symbol_registry) ──────────────────
        try:
            if self._table_exists(conn, "symbol_registry"):   # type: ignore[attr-defined]
                rows = conn.execute(
                    "SELECT category, COUNT(*) AS cnt, SUM(CASE WHEN candle_count >= 100 THEN 1 ELSE 0 END) AS ready "
                    "FROM symbol_registry GROUP BY category"
                ).fetchall()
                for row in rows:
                    cat, total, ready = str(row[0] or "").lower(), int(row[1] or 0), int(row[2] or 0)
                    result["data_total"] = result["data_total"] + total
                    if "linear" in cat or "future" in cat:
                        result["data_futures_ready"] = ready
                    elif "spot" in cat:
                        result["data_spot_ready"] = ready
        except Exception:
            pass
        # ── Model states (active_models.yaml + training_runs) ─
        try:
            from pathlib import Path as _Path
            import yaml as _yaml
            from .api_helpers import ACTIVE_MODELS_PATH
            if ACTIVE_MODELS_PATH.exists():
                raw = _yaml.safe_load(ACTIVE_MODELS_PATH.read_text(encoding="utf-8")) or {}
                for scope in ("futures", "spot"):
                    key      = f"active_{scope}_model"
                    cp_key   = f"{scope}_checkpoint_path"
                    active   = str(raw.get(key) or "").strip()
                    cp_path  = str(raw.get(cp_key) or "").strip()
                    has_file = bool(cp_path and _Path(cp_path).exists())
                    if has_file and active and active.lower() not in ("", "unknown", "none"):
                        result[f"models_{scope}"] = "trained"
                    elif cp_path:
                        result[f"models_{scope}"] = "checkpoint"
                    else:
                        result[f"models_{scope}"] = "missing"
        except Exception:
            pass
        # Override with live training state if running
        if result["ml_futures_state"] == "running":
            result["models_futures"] = "training"
        if result["ml_spot_state"] == "running":
            result["models_spot"] = "training"
        return result

    # ── Public API ────────────────────────────────────────────

    def get_snapshot(self) -> str:
        """Returns JSON with all dashboard metrics."""
        log.info("[API] get_snapshot called from JS — bridge is working")
        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn    = self._db_connect(db_path)  # type: ignore[attr-defined]

        execution_mode = str((raw_cfg.get("execution") or {}).get("mode") or "paper").upper()
        running_modes  = self._running_modes()   # type: ignore[attr-defined]
        trading_state  = self._trading_state()   # type: ignore[attr-defined]

        data: dict[str, Any] = {
            "version":        self._app_version,    # type: ignore[attr-defined]
            "uptime":         self._uptime_str(),    # type: ignore[attr-defined]
            "execution_mode": execution_mode,
            "trading_state":  trading_state,
            "running_modes":  running_modes,
            "ml_state":       self._ml_process.state,  # type: ignore[attr-defined]
            "spot_pid":       self._trading_processes["spot_spread"].pid,  # type: ignore[attr-defined]
        }

        if conn:
            try:
                data.update(self._read_balance(conn))          # type: ignore[attr-defined]
                data.update(self._read_pnl(conn))              # type: ignore[attr-defined]
                data.update(self._read_spot_summary(conn))     # type: ignore[attr-defined]
                data.update(self._read_futures_summary(conn))  # type: ignore[attr-defined]
                data["pnl_chart"]    = self._read_pnl_chart(conn)
                data["diag_rows"]    = self._read_diag_rows(conn, raw_cfg)
                data["ml_training"]  = self._read_ml_training_status(conn)  # type: ignore[attr-defined]
                data["pipeline"]     = self._read_pipeline_status(conn)
            except Exception as exc:
                data["db_error"] = str(exc)
            finally:
                conn.close()
        else:
            data["db_error"] = "db not found"

        return json.dumps(data, default=str)

    def get_logs(self, limit: int = 120) -> str:
        """Returns JSON list of recent log entries."""
        with self._buf_lock:  # type: ignore[attr-defined]
            logs = list(self._log_buffer)[-int(limit):]  # type: ignore[attr-defined]
        return json.dumps(logs)

    def get_version_info(self) -> str:
        """Returns version / system info JSON."""
        import platform
        return json.dumps({
            "version": self._app_version,  # type: ignore[attr-defined]
            "python":  platform.python_version(),
            "os":      platform.system() + " " + platform.release(),
            "config":  str(CONFIG_PATH),
        })

    def get_system_status(self) -> str:
        """Returns full system status JSON for the Ops tab."""
        import platform

        process_labels = {
            "spot_spread":            "Spot Spread",
            "spot_spike":             "Spot Spike",
            "futures_spike_reversal": "Futures Spike",
        }
        processes: list[dict] = []
        for mode, proc in self._trading_processes.items():  # type: ignore[attr-defined]
            processes.append({
                "name":  mode,
                "label": process_labels.get(mode, mode),
                "state": proc.state,
                "pid":   proc.pid,
            })
        processes.append({
            "name":  "ml",
            "label": "ML Training",
            "state": self._ml_process.state,  # type: ignore[attr-defined]
            "pid":   self._ml_process.pid,    # type: ignore[attr-defined]
        })

        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn    = self._db_connect(db_path)  # type: ignore[attr-defined]

        diag_rows     = self._read_diag_rows(conn, raw_cfg) if conn else []
        recent_errors = self._read_recent_errors(conn)      if conn else []
        db_stats      = self._read_db_stats(conn)           if conn else []
        if conn:
            conn.close()

        env_map      = _read_env_map()
        has_api_key  = bool(env_map.get("BYBIT_API_KEY", "").strip())
        has_telegram = bool(env_map.get("TELEGRAM_BOT_TOKEN", "").strip())

        # RAM / CPU (psutil optional)
        ram_used_mb = ram_total_mb = ram_percent = cpu_percent = None
        try:
            import psutil
            vm           = psutil.virtual_memory()
            ram_used_mb  = round(vm.used  / 1024 / 1024)
            ram_total_mb = round(vm.total / 1024 / 1024)
            ram_percent  = vm.percent
            cpu_percent  = psutil.cpu_percent(interval=0.2)
        except Exception:
            pass

        # DB ping
        db_ping_ms = None
        try:
            t0    = time.perf_counter()
            conn2 = sqlite3.connect(str(_resolve_db_path(_load_yaml())), timeout=2)
            conn2.execute("SELECT 1").fetchone()
            conn2.close()
            db_ping_ms = round((time.perf_counter() - t0) * 1000, 1)
        except Exception:
            pass

        return json.dumps({
            "processes":     processes,
            "diag_rows":     diag_rows,
            "recent_errors": recent_errors,
            "db_stats":      db_stats,
            "env_status":    {"has_api_key": has_api_key, "has_telegram": has_telegram},
            "uptime":        self._uptime_str(),    # type: ignore[attr-defined]
            "version":       self._app_version,     # type: ignore[attr-defined]
            "python":        platform.python_version(),
            "os":            platform.system() + " " + platform.release(),
            "ram_used_mb":   ram_used_mb,
            "ram_total_mb":  ram_total_mb,
            "ram_percent":   ram_percent,
            "cpu_percent":   cpu_percent,
            "db_ping_ms":    db_ping_ms,
        }, default=str)
