"""
DataMixin — Data Layer UI API (M4).

Public API:
  get_data_status()    — symbols table + per-category summary + worker states
  start_backfill()     — launch BackfillWorker subprocess
  stop_backfill()      — terminate BackfillWorker subprocess
  start_live_data()    — launch LiveDataWorker subprocess
  stop_live_data()     — terminate LiveDataWorker subprocess
"""
from __future__ import annotations

import json
import logging
import sys

from .api_helpers import _resolve_db_path, _load_yaml, _build_subprocess_cmd

log = logging.getLogger("botik.webview")

# Seconds since last_candle_ms to mark ws as "recent"
_WS_RECENT_THRESHOLD_S = 120


class DataMixin:
    """Mixin providing data-layer control methods to DashboardAPI."""

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _read_symbol_registry(self) -> tuple[list[dict], dict]:
        """
        Read all rows from symbol_registry.
        Returns (symbols_list, summary_dict) directly via SQL.
        """
        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn = self._db_connect(db_path)  # type: ignore[attr-defined]
        if conn is None:
            return [], {}

        symbols: list[dict] = []
        summary: dict[str, dict] = {}

        try:
            if not self._table_exists(conn, "symbol_registry"):  # type: ignore[attr-defined]
                return [], {}

            rows = conn.execute(
                "SELECT symbol, category, interval, candle_count, "
                "last_candle_ms, ws_active, data_status, updated_at_utc "
                "FROM symbol_registry "
                "ORDER BY category, symbol, interval"
            ).fetchall()

            for row in rows:
                symbol, cat, interval, candle_count, last_ms, ws_active, status, updated = row
                symbols.append({
                    "symbol":       str(symbol),
                    "category":     str(cat),
                    "interval":     str(interval),
                    "candle_count": int(candle_count or 0),
                    "last_candle_ms": int(last_ms) if last_ms is not None else None,
                    "ws_active":    bool(ws_active),
                    "data_status":  str(status or "empty"),
                    "updated_at":   str(updated or ""),
                })
                # Build per-category summary
                if cat not in summary:
                    summary[cat] = {
                        "total": 0, "ready": 0, "partial": 0,
                        "empty": 0, "ws_active": 0, "total_candles": 0,
                    }
                s = summary[cat]
                s["total"] += 1
                s[str(status or "empty")] = s.get(str(status or "empty"), 0) + 1
                if ws_active:
                    s["ws_active"] += 1
                s["total_candles"] += int(candle_count or 0)

        except Exception as exc:
            log.warning("DataMixin._read_symbol_registry: %s", exc)
        finally:
            conn.close()

        return symbols, summary

    # ── Public API ────────────────────────────────────────────────────────────

    def get_data_status(self) -> str:
        """Returns JSON with symbol registry contents and worker states."""
        symbols, summary = self._read_symbol_registry()
        return json.dumps({
            "symbols":         symbols,
            "summary":         summary,
            "backfill_state":  self._backfill_process.state,   # type: ignore[attr-defined]
            "livedata_state":  self._livedata_process.state,   # type: ignore[attr-defined]
        }, default=str)

    def start_backfill(self) -> str:
        """Start BackfillWorker subprocess."""
        if self._backfill_process.running:  # type: ignore[attr-defined]
            return json.dumps({"ok": False, "error": "already_running"})
        cmd = _build_subprocess_cmd("backfill")
        ok, msg = self._backfill_process.start(cmd)   # type: ignore[attr-defined]
        self._add_log(f"[data] start_backfill ok={ok} cmd={cmd[0]}", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": ok, "msg": msg})

    def stop_backfill(self) -> str:
        """Terminate BackfillWorker subprocess."""
        self._backfill_process.stop()   # type: ignore[attr-defined]
        self._add_log("[data] stop_backfill", "ml")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    def start_live_data(self) -> str:
        """Start LiveDataWorker subprocess."""
        if self._livedata_process.running:  # type: ignore[attr-defined]
            return json.dumps({"ok": False, "error": "already_running"})
        cmd = _build_subprocess_cmd("live")
        ok, msg = self._livedata_process.start(cmd)   # type: ignore[attr-defined]
        self._add_log(f"[data] start_live_data ok={ok} cmd={cmd[0]}", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": ok, "msg": msg})

    def stop_live_data(self) -> str:
        """Terminate LiveDataWorker subprocess."""
        self._livedata_process.stop()   # type: ignore[attr-defined]
        self._add_log("[data] stop_live_data", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    # ── Symbol seeding ────────────────────────────────────────────────────────

    _SEED_INTERVALS: tuple[str, ...] = ("1", "5", "15", "60")

    def seed_symbol_registry(self) -> str:
        """Discover ALL trading symbols from Bybit and register them for all intervals.

        Fetches the full instrument list from Bybit public API:
          - Linear (USDT perpetuals): ~300-400 contracts
          - Spot (USDT pairs):        ~400-600 pairs

        Safe to call multiple times — INSERT OR IGNORE prevents duplicates.
        Existing symbols with collected candles are NOT affected.
        """
        import asyncio
        import os

        try:
            from src.botik.storage.db import get_db
            from src.botik.data.symbol_registry import SymbolRegistry
            from src.botik.marketdata.symbol_universe import (
                fetch_linear_instruments, filter_linear_symbols,
                fetch_spot_instruments,   filter_spot_symbols,
            )

            # Instruments-info is a public endpoint — always use mainnet
            host = os.environ.get("BYBIT_HOST", "api.bybit.com")
            if "demo" in host.lower():
                host = "api.bybit.com"

            async def _fetch_all():
                linear_instr = await fetch_linear_instruments(host)
                spot_instr   = await fetch_spot_instruments(host)
                return filter_linear_symbols(linear_instr), filter_spot_symbols(spot_instr)

            linear_symbols, spot_symbols = asyncio.run(_fetch_all())

            db = get_db()
            registry = SymbolRegistry(db)
            for interval in self._SEED_INTERVALS:
                registry.register_many(linear_symbols, "linear", interval)
                registry.register_many(spot_symbols,   "spot",   interval)

            total = (len(linear_symbols) + len(spot_symbols)) * len(self._SEED_INTERVALS)
            self._add_log(  # type: ignore[attr-defined]
                f"[data] seeded {len(linear_symbols)} linear + {len(spot_symbols)} spot "
                f"symbols → {total} rows",
                "sys",
            )
            return json.dumps({
                "ok": True,
                "linear": len(linear_symbols),
                "spot":   len(spot_symbols),
                "rows":   total,
            })
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    # ── History cleanup ───────────────────────────────────────────────────────

    def clear_training_history(self) -> str:
        """Delete all rows from ml_training_runs and model_stats.

        Used to wipe old bootstrap data before starting fresh ML pipeline.
        """
        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn = self._db_connect(db_path)  # type: ignore[attr-defined]
        if not conn:
            return json.dumps({"ok": False, "error": "no_db"})
        try:
            deleted = 0
            for table in ("ml_training_runs", "model_stats"):
                if self._table_exists(conn, table):  # type: ignore[attr-defined]
                    cur = conn.execute(f"DELETE FROM {table}")
                    deleted += cur.rowcount
            conn.commit()
            self._add_log(f"[data] clear_training_history deleted={deleted}", "sys")  # type: ignore[attr-defined]
            return json.dumps({"ok": True, "deleted": deleted})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        finally:
            conn.close()
