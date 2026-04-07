"""
OrderbookMixin — order book REST poller (T41).

Polls Bybit /v5/market/orderbook every _POLL_INTERVAL_S seconds for
a configurable list of symbols and stores snapshots in orderbook_snapshots.

Public API:
  get_orderbook(symbol, category)  — latest snapshot from DB
  get_orderbook_symbols()          — list of tracked symbols + categories
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .api_helpers import _load_yaml, _resolve_db_path

log = logging.getLogger("botik.webview")

# Polling interval in seconds
_POLL_INTERVAL_S: int = 20

# How many snapshots to keep per (symbol, category) — prune older ones
_KEEP_SNAPSHOTS: int = 100

# Depth (how many levels to request)
_DEPTH: int = 25

_DEFAULT_SYMBOLS: list[tuple[str, str]] = [
    ("BTCUSDT", "linear"),
    ("ETHUSDT", "linear"),
    ("SOLUSDT", "linear"),
    ("BTCUSDT", "spot"),
    ("ETHUSDT", "spot"),
]


class OrderbookMixin:
    """Background REST polling for order book data."""

    def _init_orderbook(self) -> None:
        self._ob_symbols: list[tuple[str, str]] = list(_DEFAULT_SYMBOLS)
        self._ob_stop = threading.Event()
        threading.Thread(
            target=self._ob_poll_loop, daemon=True, name="orderbook-poll"
        ).start()

    # ── Background thread ────────────────────────────────────────────────────

    def _ob_poll_loop(self) -> None:
        while not self._ob_stop.is_set():
            try:
                self._ob_fetch_all()
            except Exception as exc:
                log.warning("[orderbook] poll error: %s", exc)
            self._ob_stop.wait(timeout=_POLL_INTERVAL_S)

    def _ob_fetch_all(self) -> None:
        host = os.environ.get("BYBIT_HOST", "api.bybit.com")
        if "demo" in host.lower():
            host = "api.bybit.com"

        for symbol, category in self._ob_symbols:
            if self._ob_stop.is_set():
                break
            try:
                url = (
                    f"https://{host}/v5/market/orderbook"
                    f"?category={category}&symbol={symbol}&limit={_DEPTH}"
                )
                with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
                    data = json.loads(resp.read())

                result = (data.get("result") or {})
                bids = result.get("b") or []
                asks = result.get("a") or []
                ts_ms = int(result.get("ts") or time.time() * 1000)

                self._ob_store(symbol, category, bids, asks, ts_ms)
            except Exception as exc:
                log.debug("[orderbook] %s/%s error: %s", symbol, category, exc)

    def _ob_store(
        self,
        symbol: str,
        category: str,
        bids: list,
        asks: list,
        ts_ms: int,
    ) -> None:
        try:
            raw_cfg = _load_yaml()
            db_path = _resolve_db_path(raw_cfg)
            conn = sqlite3.connect(str(db_path), timeout=10)
            try:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO orderbook_snapshots "
                    "(symbol, category, bids_json, asks_json, ts_ms, created_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        symbol, category,
                        json.dumps(bids), json.dumps(asks),
                        ts_ms, now,
                    ),
                )
                # Prune old snapshots
                conn.execute(
                    "DELETE FROM orderbook_snapshots "
                    "WHERE symbol=? AND category=? AND id NOT IN ("
                    "  SELECT id FROM orderbook_snapshots "
                    "  WHERE symbol=? AND category=? "
                    "  ORDER BY ts_ms DESC LIMIT ?"
                    ")",
                    (symbol, category, symbol, category, _KEEP_SNAPSHOTS),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            log.debug("[orderbook] store error: %s", exc)

    # ── Public API ───────────────────────────────────────────────────────────

    def get_orderbook(self, symbol: str = "BTCUSDT", category: str = "linear") -> str:
        """Return the latest orderbook snapshot for the given symbol/category."""
        try:
            raw_cfg = _load_yaml()
            db_path = _resolve_db_path(raw_cfg)
            conn = sqlite3.connect(str(db_path), timeout=5)
            try:
                row = conn.execute(
                    "SELECT bids_json, asks_json, ts_ms, created_at_utc "
                    "FROM orderbook_snapshots "
                    "WHERE symbol=? AND category=? "
                    "ORDER BY ts_ms DESC LIMIT 1",
                    (symbol, category),
                ).fetchone()
            finally:
                conn.close()

            if not row:
                return json.dumps({"symbol": symbol, "category": category,
                                   "bids": [], "asks": [], "ts_ms": None})

            bids_raw, asks_raw, ts_ms, created_at = row
            return json.dumps({
                "symbol":     symbol,
                "category":   category,
                "bids":       json.loads(bids_raw or "[]"),
                "asks":       json.loads(asks_raw or "[]"),
                "ts_ms":      ts_ms,
                "created_at": created_at,
            })
        except Exception as exc:
            log.warning("[orderbook] get_orderbook error: %s", exc)
            return json.dumps({"error": str(exc), "bids": [], "asks": []})

    def get_orderbook_symbols(self) -> str:
        """Return the list of currently tracked (symbol, category) pairs."""
        return json.dumps([
            {"symbol": s, "category": c} for s, c in self._ob_symbols
        ])

    def set_orderbook_symbols(self, symbols_json: str) -> str:
        """Update the tracked symbols list.

        Expects JSON array of {symbol, category} objects.
        """
        try:
            items = json.loads(symbols_json)
            self._ob_symbols = [(d["symbol"], d["category"]) for d in items]
            return json.dumps({"ok": True, "count": len(self._ob_symbols)})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})
