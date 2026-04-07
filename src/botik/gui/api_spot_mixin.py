"""
SpotMixin — spot holdings reading and sell actions.

Public API: get_spot_positions, get_spot_orders, get_spot_fills,
            sell_spot_position, sell_all_spot.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from .api_helpers import _load_yaml, _resolve_db_path

log = logging.getLogger("botik.webview")


class SpotMixin:
    """Mixin providing spot-market methods to DashboardAPI."""

    # ── Internal readers ──────────────────────────────────────

    def _read_balance(self, conn: sqlite3.Connection) -> dict[str, Any]:
        try:
            row = conn.execute(
                "SELECT total_equity, wallet_balance, available_balance "
                "FROM account_snapshots ORDER BY created_at_utc DESC LIMIT 1"
            ).fetchone()
            if row:
                r = dict(row)
                return {
                    "balance_total":     float(r.get("total_equity") or 0),
                    "balance_wallet":    float(r.get("wallet_balance") or 0),
                    "balance_available": float(r.get("available_balance") or 0),
                }
        except Exception:
            pass
        return {"balance_total": None, "balance_wallet": None, "balance_available": None}

    def _read_pnl(self, conn: sqlite3.Connection) -> dict[str, Any]:
        try:
            row = conn.execute(
                "SELECT SUM(net_pnl_quote) AS pnl_sum FROM outcomes "
                "WHERE DATE(finished_at_utc) = DATE('now')"
            ).fetchone()
            pnl_today = float((dict(row).get("pnl_sum") or 0)) if row else 0.0

            row2 = conn.execute(
                "SELECT COUNT(*) AS cnt FROM outcomes WHERE DATE(finished_at_utc) = DATE('now')"
            ).fetchone()
            trades_today = int((dict(row2).get("cnt") or 0)) if row2 else 0

            row3 = conn.execute(
                "SELECT COUNT(*) AS cnt FROM outcomes "
                "WHERE DATE(finished_at_utc) = DATE('now') AND net_pnl_quote > 0"
            ).fetchone()
            wins_today = int((dict(row3).get("cnt") or 0)) if row3 else 0

            win_rate = round(wins_today / trades_today * 100, 1) if trades_today > 0 else None
            return {
                "pnl_today":    pnl_today,
                "trades_today": trades_today,
                "win_rate":     win_rate,
                "wins_today":   wins_today,
            }
        except Exception:
            return {"pnl_today": 0.0, "trades_today": 0, "win_rate": None}

    def _read_spot_holdings(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "spot_holdings"):  # type: ignore[attr-defined]
                return []
            columns = self._table_columns(conn, "spot_holdings")  # type: ignore[attr-defined]
            cur_price_expr  = "current_price"  if "current_price"  in columns else "NULL AS current_price"
            unreal_pnl_expr = "unrealized_pnl" if "unrealized_pnl" in columns else "NULL AS unrealized_pnl"
            rows = conn.execute(
                f"SELECT symbol, base_asset, free_qty, locked_qty, avg_entry_price, "
                f"{cur_price_expr}, {unreal_pnl_expr}, hold_reason, source_of_truth, "
                "recovered_from_exchange, auto_sell_allowed, updated_at_utc "
                "FROM spot_holdings "
                "WHERE ABS(COALESCE(free_qty, 0.0)) > 0 OR ABS(COALESCE(locked_qty, 0.0)) > 0 "
                "ORDER BY updated_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out: list[dict] = []
            for row in rows:
                payload = dict(row)
                payload["total_qty"] = float(payload.get("free_qty") or 0.0) + float(payload.get("locked_qty") or 0.0)
                out.append(payload)
            return out
        except Exception:
            return []

    def _read_spot_holdings_count(self, conn: sqlite3.Connection) -> int:
        try:
            if not self._table_exists(conn, "spot_holdings"):  # type: ignore[attr-defined]
                return 0
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM spot_holdings "
                "WHERE ABS(COALESCE(free_qty, 0.0)) > 0 OR ABS(COALESCE(locked_qty, 0.0)) > 0"
            ).fetchone()
            return int((dict(row).get("cnt") or 0)) if row else 0
        except Exception:
            return 0

    def _read_spot_summary(self, conn: sqlite3.Connection) -> dict[str, Any]:
        _empty = {
            "spot_open_count": 0, "spot_total_qty": 0.0,
            "spot_unrealized_pnl": None, "spot_recovered_count": 0,
            "spot_auto_sell_count": 0, "spot_open_orders_count": 0,
        }
        try:
            if not self._table_exists(conn, "spot_holdings"):  # type: ignore[attr-defined]
                return _empty
            columns = self._table_columns(conn, "spot_holdings")  # type: ignore[attr-defined]
            unreal_sum_expr = (
                "COALESCE(SUM(unrealized_pnl), 0.0)" if "unrealized_pnl" in columns else "NULL"
            )
            row = conn.execute(f"""
                SELECT
                    COUNT(*) AS open_count,
                    COALESCE(SUM(COALESCE(free_qty, 0.0) + COALESCE(locked_qty, 0.0)), 0.0) AS total_qty,
                    {unreal_sum_expr} AS unrealized_sum,
                    COALESCE(SUM(CASE WHEN COALESCE(recovered_from_exchange, 0) != 0 THEN 1 ELSE 0 END), 0) AS recovered_count,
                    COALESCE(SUM(CASE WHEN COALESCE(auto_sell_allowed, 0) != 0 THEN 1 ELSE 0 END), 0) AS auto_sell_count
                FROM spot_holdings
                WHERE ABS(COALESCE(free_qty, 0.0)) > 0 OR ABS(COALESCE(locked_qty, 0.0)) > 0
            """).fetchone()

            open_orders_count = 0
            if self._table_exists(conn, "spot_orders"):  # type: ignore[attr-defined]
                open_orders_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM spot_orders "
                    "WHERE LOWER(COALESCE(status, '')) IN ('new', 'open', 'partiallyfilled', 'partially_filled')"
                ).fetchone()
                open_orders_count = int((dict(open_orders_row).get("cnt") or 0)) if open_orders_row else 0

            r = dict(row) if row else {}
            return {
                "spot_open_count":       int(r.get("open_count") or 0),
                "spot_total_qty":        float(r.get("total_qty") or 0.0),
                "spot_unrealized_pnl":   None if not r or r.get("unrealized_sum") is None
                                         else float(r.get("unrealized_sum") or 0.0),
                "spot_recovered_count":  int(r.get("recovered_count") or 0),
                "spot_auto_sell_count":  int(r.get("auto_sell_count") or 0),
                "spot_open_orders_count": open_orders_count,
            }
        except Exception:
            return _empty

    def _read_spot_orders(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "spot_orders"):  # type: ignore[attr-defined]
                return []
            rows = conn.execute(
                "SELECT symbol, side, order_type, price, qty, filled_qty, status, updated_at_utc "
                "FROM spot_orders ORDER BY updated_at_utc DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _read_spot_fills(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        try:
            if not self._table_exists(conn, "spot_fills"):  # type: ignore[attr-defined]
                return []
            rows = conn.execute(
                "SELECT symbol, side, price, qty, fee, fee_currency, exec_time_ms, created_at_utc "
                "FROM spot_fills ORDER BY COALESCE(exec_time_ms, 0) DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Public API ────────────────────────────────────────────

    def get_spot_positions(self) -> str:
        """Returns JSON list of open spot holdings."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_spot_holdings(conn), default=str)
        finally:
            conn.close()

    def get_spot_orders(self) -> str:
        """Returns JSON list of recent spot orders."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_spot_orders(conn), default=str)
        finally:
            conn.close()

    def get_spot_fills(self) -> str:
        """Returns JSON list of recent spot fills."""
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps([])
        try:
            return json.dumps(self._read_spot_fills(conn), default=str)
        finally:
            conn.close()

    # ── Sell actions ──────────────────────────────────────────

    def sell_spot_position(self, symbol: str, qty: float | None = None) -> str:
        """Mark a spot holding for immediate sale (queued for SpotRunner)."""
        try:
            db_path = _resolve_db_path(_load_yaml())
            conn    = sqlite3.connect(str(db_path), timeout=5)
            try:
                symbol = str(symbol).upper().strip()
                if not self._table_exists(conn, "spot_holdings"):  # type: ignore[attr-defined]
                    return json.dumps({"ok": False, "error": "spot_holdings table missing"})
                if qty is not None:
                    conn.execute(
                        "UPDATE spot_holdings SET auto_sell_allowed=1, hold_reason='manual_sell',"
                        " free_qty=?, updated_at_utc=CURRENT_TIMESTAMP WHERE symbol=?",
                        (float(qty), symbol),
                    )
                else:
                    conn.execute(
                        "UPDATE spot_holdings SET auto_sell_allowed=1, hold_reason='manual_sell',"
                        " updated_at_utc=CURRENT_TIMESTAMP WHERE symbol=?",
                        (symbol,),
                    )
                conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
                msg = f"[spot] sell_spot_position({symbol}) queued — {affected} row(s)"
                log.info(msg)
                self._add_log(msg, "spot")  # type: ignore[attr-defined]
                return json.dumps({"ok": True, "symbol": symbol, "affected": affected})
            finally:
                conn.close()
        except Exception as exc:
            log.error("sell_spot_position error: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    def sell_all_spot(self) -> str:
        """Mark ALL spot holdings for immediate sale."""
        try:
            db_path = _resolve_db_path(_load_yaml())
            conn    = sqlite3.connect(str(db_path), timeout=5)
            try:
                if not self._table_exists(conn, "spot_holdings"):  # type: ignore[attr-defined]
                    return json.dumps({"ok": False, "error": "spot_holdings table missing"})
                conn.execute(
                    "UPDATE spot_holdings SET auto_sell_allowed=1, hold_reason='manual_sell',"
                    " updated_at_utc=CURRENT_TIMESTAMP"
                    " WHERE ABS(COALESCE(free_qty,0))>0 OR ABS(COALESCE(locked_qty,0))>0"
                )
                conn.commit()
                affected = conn.execute("SELECT changes()").fetchone()[0]
                msg = f"[spot] sell_all_spot() — {affected} holding(s) queued for sale"
                log.info(msg)
                self._add_log(msg, "spot")  # type: ignore[attr-defined]
                return json.dumps({"ok": True, "affected": affected})
            finally:
                conn.close()
        except Exception as exc:
            log.error("sell_all_spot error: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})
