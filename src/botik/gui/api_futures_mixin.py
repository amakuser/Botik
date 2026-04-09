"""
FuturesMixin — futures position reading and management actions.

Public API: get_futures_positions, close_futures_position, update_futures_tp_sl.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from .api_helpers import _load_yaml, _resolve_db_path

log = logging.getLogger("botik.webview")


class FuturesMixin:
    """Mixin providing futures-market methods to DashboardAPI."""

    # ── Internal readers ──────────────────────────────────────

    def _read_futures_summary(self, conn: sqlite3.Connection) -> dict[str, Any]:
        _empty = {
            "futures_open_count":      0,
            "futures_unrealised_pnl":  0.0,
            "futures_protected_count": 0,
            "futures_attention_count": 0,
        }
        try:
            if not self._table_exists(conn, "futures_positions"):  # type: ignore[attr-defined]
                return _empty
            columns    = self._table_columns(conn, "futures_positions")  # type: ignore[attr-defined]
            qty_column = "size" if "size" in columns else ("qty" if "qty" in columns else "")
            pnl_column = (
                "unrealised_pnl"  if "unrealised_pnl"  in columns else
                ("unrealized_pnl" if "unrealized_pnl"  in columns else "")
            )
            if not qty_column:
                return _empty
            pnl_sum_expr = f"COALESCE(SUM({pnl_column}), 0.0)" if pnl_column else "0.0"
            row = conn.execute(f"""
                SELECT
                    COUNT(*) AS open_count,
                    {pnl_sum_expr} AS unrealised_pnl,
                    COALESCE(SUM(CASE WHEN LOWER(COALESCE(protection_status, '')) = 'protected'
                                      THEN 1 ELSE 0 END), 0) AS protected_count,
                    COALESCE(SUM(CASE WHEN LOWER(COALESCE(protection_status, ''))
                                      IN ('pending', 'repairing', 'failed', 'unprotected')
                                      THEN 1 ELSE 0 END), 0) AS attention_count
                FROM futures_positions
                WHERE ABS(COALESCE({qty_column}, 0.0)) > 0
            """).fetchone()
            if not row:
                return _empty
            r = dict(row)
            return {
                "futures_open_count":      int(r.get("open_count") or 0),
                "futures_unrealised_pnl":  float(r.get("unrealised_pnl") or 0.0),
                "futures_protected_count": int(r.get("protected_count") or 0),
                "futures_attention_count": int(r.get("attention_count") or 0),
            }
        except Exception:
            return _empty

    def _read_futures_positions(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "futures_positions"):  # type: ignore[attr-defined]
                return []
            columns    = self._table_columns(conn, "futures_positions")  # type: ignore[attr-defined]
            qty_column = "size" if "size" in columns else ("qty" if "qty" in columns else "")
            pnl_column = (
                "unrealised_pnl"  if "unrealised_pnl"  in columns else
                ("unrealized_pnl" if "unrealized_pnl"  in columns else "")
            )
            if not qty_column:
                return []
            leverage_expr   = "leverage"          if "leverage"          in columns else "NULL AS leverage"
            liq_expr        = "liq_price"         if "liq_price"         in columns else "NULL AS liq_price"
            protection_expr = "protection_status" if "protection_status" in columns else "NULL AS protection_status"
            pnl_expr        = f"{pnl_column} AS unrealised_pnl" if pnl_column else "NULL AS unrealised_pnl"
            rows = conn.execute(
                f"SELECT symbol, side, {qty_column} AS size, entry_price, mark_price, "
                f"{leverage_expr}, {liq_expr}, {pnl_expr}, {protection_expr}, updated_at_utc "
                "FROM futures_positions "
                f"WHERE ABS(COALESCE({qty_column}, 0.0)) > 0 "
                "ORDER BY updated_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _read_futures_orders(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "futures_orders"):  # type: ignore[attr-defined]
                return []
            rows = conn.execute(
                "SELECT symbol, side, order_type, price, qty, filled_qty, status, updated_at_utc "
                "FROM futures_orders ORDER BY updated_at_utc DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _read_futures_fills(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "futures_fills"):  # type: ignore[attr-defined]
                return []
            rows = conn.execute(
                "SELECT symbol, side, price, qty, fee, fee_currency, pnl, exec_time_ms, created_at_utc "
                "FROM futures_fills ORDER BY COALESCE(exec_time_ms,0) DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Public API ────────────────────────────────────────────

    def get_futures_positions(self) -> str:
        """Returns JSON list of open futures positions."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_futures_positions(conn), default=str)
        finally:
            conn.close()

    def get_futures_orders(self) -> str:
        """Returns JSON list of recent futures orders."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_futures_orders(conn), default=str)
        finally:
            conn.close()

    def get_futures_fills(self) -> str:
        """Returns JSON list of recent futures fills."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_futures_fills(conn), default=str)
        finally:
            conn.close()

    def close_futures_position(self, symbol: str, side: str) -> str:
        """Mark a futures position for closure (sets protection_status='close_requested')."""
        try:
            db_path = _resolve_db_path(_load_yaml())
            conn    = sqlite3.connect(str(db_path), timeout=5)
            try:
                symbol = str(symbol).upper().strip()
                side   = str(side).upper().strip()
                if not self._table_exists(conn, "futures_positions"):  # type: ignore[attr-defined]
                    return json.dumps({"ok": False, "error": "futures_positions table missing"})
                cols = self._table_columns(conn, "futures_positions")  # type: ignore[attr-defined]
                if "protection_status" in cols:
                    conn.execute(
                        "UPDATE futures_positions SET protection_status='close_requested',"
                        " updated_at_utc=CURRENT_TIMESTAMP WHERE symbol=? AND side=?",
                        (symbol, side),
                    )
                    conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
                msg = f"[futures] close_position({symbol} {side}) requested — {affected} row(s)"
                log.info(msg)
                self._add_log(msg, "futures")  # type: ignore[attr-defined]
                return json.dumps({"ok": True, "symbol": symbol, "side": side, "affected": affected})
            finally:
                conn.close()
        except Exception as exc:
            log.error("close_futures_position error: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    def update_futures_tp_sl(
        self,
        symbol: str,
        side: str,
        tp_price: float | None,
        sl_price: float | None,
    ) -> str:
        """Update TP and/or SL for an open futures position."""
        try:
            db_path = _resolve_db_path(_load_yaml())
            conn    = sqlite3.connect(str(db_path), timeout=5)
            try:
                symbol = str(symbol).upper().strip()
                side   = str(side).upper().strip()
                if not self._table_exists(conn, "futures_positions"):  # type: ignore[attr-defined]
                    return json.dumps({"ok": False, "error": "futures_positions table missing"})
                cols: set[str] = self._table_columns(conn, "futures_positions")  # type: ignore[attr-defined]
                sets: list[str] = ["updated_at_utc=CURRENT_TIMESTAMP"]
                params: list[Any] = []
                if tp_price is not None and "tp_price" in cols:
                    sets.append("tp_price=?")
                    params.append(float(tp_price))
                if sl_price is not None and "sl_price" in cols:
                    sets.append("sl_price=?")
                    params.append(float(sl_price))
                if len(sets) <= 1:
                    return json.dumps({"ok": False, "error": "no valid columns to update (tp_price/sl_price missing)"})
                params.extend([symbol, side])
                conn.execute(
                    f"UPDATE futures_positions SET {', '.join(sets)} WHERE symbol=? AND side=?",
                    params,
                )
                conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
                msg = f"[futures] update_tp_sl({symbol} {side} tp={tp_price} sl={sl_price}) — {affected} row(s)"
                log.info(msg)
                self._add_log(msg, "futures")  # type: ignore[attr-defined]
                return json.dumps({"ok": True, "affected": affected})
            finally:
                conn.close()
        except Exception as exc:
            log.error("update_futures_tp_sl error: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})
