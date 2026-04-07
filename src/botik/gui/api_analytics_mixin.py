"""
AnalyticsMixin — PnL analytics: equity curve, drawdown, win rate.

Data sources:
  futures_paper_trades  — net_pnl / gross_pnl, was_profitable, closed_at_utc
  outcomes              — net_pnl_quote / gross_pnl_quote, was_profitable, closed_at_utc
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date
from typing import Any

from .api_helpers import _load_yaml, _resolve_db_path

log = logging.getLogger("botik.webview")

_VALID_DAYS = frozenset({7, 30, 90, 0})   # 0 = all time


class AnalyticsMixin:
    """Mixin providing PnL analytics methods to DashboardAPI."""

    # ── Public API ────────────────────────────────────────────

    def get_pnl_analytics(self, scope: str = "all", days: int = 30) -> str:
        """Return JSON with equity curve, drawdown, win rate, trade stats.

        Args:
            scope: "all" | "futures" | "spot"
            days:  7 | 30 | 90 | 0 (0 = all time)
        """
        empty = _empty_analytics()
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return json.dumps(empty)
        try:
            days_int  = int(days)  if int(days)  in _VALID_DAYS else 30
            scope_str = str(scope).lower().strip()
            trades    = self._collect_trades(conn, scope_str, days_int)
            if not trades:
                return json.dumps(empty)
            return json.dumps(_compute_analytics(trades), default=str)
        except Exception as exc:
            log.error("get_pnl_analytics error: %s", exc)
            return json.dumps(empty)
        finally:
            conn.close()

    # ── Internal helpers ──────────────────────────────────────

    def _collect_trades(
        self,
        conn: sqlite3.Connection,
        scope: str,
        days: int,
    ) -> list[dict[str, Any]]:
        """Collect closed trades from futures_paper_trades and outcomes tables."""
        rows: list[dict[str, Any]] = []

        date_filter  = f"AND date(closed_at_utc) >= date('now', '-{days} days')" if days > 0 else ""
        scope_filter = f"AND model_scope = '{scope}'" if scope != "all" else ""

        rows.extend(self._read_futures_paper(conn, date_filter, scope_filter))
        rows.extend(self._read_outcomes(conn, date_filter, scope_filter))

        rows.sort(key=lambda r: r["closed_at"])
        return rows

    def _read_futures_paper(
        self,
        conn: sqlite3.Connection,
        date_filter: str,
        scope_filter: str,
    ) -> list[dict[str, Any]]:
        if not self._table_exists(conn, "futures_paper_trades"):  # type: ignore[attr-defined]
            return []
        cols    = self._table_columns(conn, "futures_paper_trades")  # type: ignore[attr-defined]
        pnl_col = "net_pnl" if "net_pnl" in cols else ("gross_pnl" if "gross_pnl" in cols else None)
        if not pnl_col:
            return []
        try:
            result = conn.execute(f"""
                SELECT
                    symbol,
                    COALESCE(model_scope, 'futures')                        AS model_scope,
                    COALESCE({pnl_col}, 0.0)                               AS pnl,
                    COALESCE(was_profitable,
                             CASE WHEN {pnl_col} > 0 THEN 1 ELSE 0 END)   AS win,
                    closed_at_utc
                FROM futures_paper_trades
                WHERE closed_at_utc IS NOT NULL {date_filter} {scope_filter}
                ORDER BY closed_at_utc ASC
            """).fetchall()
        except Exception as exc:
            log.warning("futures_paper_trades read error: %s", exc)
            return []
        return [
            {
                "symbol":    r[0],
                "scope":     r[1],
                "pnl":       float(r[2]),
                "win":       int(r[3]),
                "closed_at": str(r[4]),
            }
            for r in result
        ]

    def _read_outcomes(
        self,
        conn: sqlite3.Connection,
        date_filter: str,
        scope_filter: str,
    ) -> list[dict[str, Any]]:
        if not self._table_exists(conn, "outcomes"):  # type: ignore[attr-defined]
            return []
        cols    = self._table_columns(conn, "outcomes")  # type: ignore[attr-defined]
        pnl_col = (
            "net_pnl_quote"   if "net_pnl_quote"   in cols else
            ("gross_pnl_quote" if "gross_pnl_quote" in cols else None)
        )
        if not pnl_col:
            return []
        try:
            result = conn.execute(f"""
                SELECT
                    symbol,
                    COALESCE(model_scope, 'spot')                          AS model_scope,
                    COALESCE({pnl_col}, 0.0)                              AS pnl,
                    COALESCE(was_profitable,
                             CASE WHEN {pnl_col} > 0 THEN 1 ELSE 0 END)  AS win,
                    closed_at_utc
                FROM outcomes
                WHERE closed_at_utc IS NOT NULL {date_filter} {scope_filter}
                ORDER BY closed_at_utc ASC
            """).fetchall()
        except Exception as exc:
            log.warning("outcomes read error: %s", exc)
            return []
        return [
            {
                "symbol":    r[0],
                "scope":     r[1],
                "pnl":       float(r[2]),
                "win":       int(r[3]),
                "closed_at": str(r[4]),
            }
            for r in result
        ]


# ── Pure computation (no DB, easy to test) ───────────────────────────────────

def _empty_analytics() -> dict[str, Any]:
    return {
        "total_pnl":     0.0,
        "win_rate":      0.0,
        "max_drawdown":  0.0,
        "trade_count":   0,
        "avg_pnl":       0.0,
        "today_pnl":     0.0,
        "best_trade":    0.0,
        "worst_trade":   0.0,
        "equity_curve":  [],
        "by_scope":      {},
        "recent_trades": [],
    }


def _compute_analytics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute all analytics from a list of trade dicts (pure function)."""
    pnls  = [t["pnl"] for t in trades]
    wins  = sum(t["win"] for t in trades)
    n     = len(trades)

    total_pnl   = sum(pnls)
    win_rate    = wins / n if n else 0.0
    avg_pnl     = total_pnl / n if n else 0.0
    best_trade  = max(pnls) if pnls else 0.0
    worst_trade = min(pnls) if pnls else 0.0

    today_str = date.today().isoformat()
    today_pnl = sum(t["pnl"] for t in trades if t["closed_at"].startswith(today_str))

    equity_curve = _build_equity_curve(trades)
    max_drawdown = _calc_max_drawdown([p["cumulative_pnl"] for p in equity_curve])
    by_scope     = _build_by_scope(trades)
    recent       = _build_recent_trades(trades)

    return {
        "total_pnl":     round(total_pnl,   4),
        "win_rate":      round(win_rate,     4),
        "max_drawdown":  round(max_drawdown, 4),
        "trade_count":   n,
        "avg_pnl":       round(avg_pnl,      4),
        "today_pnl":     round(today_pnl,    4),
        "best_trade":    round(best_trade,   4),
        "worst_trade":   round(worst_trade,  4),
        "equity_curve":  equity_curve,
        "by_scope":      by_scope,
        "recent_trades": recent,
    }


def _build_equity_curve(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    daily: dict[str, float] = {}
    for t in trades:
        day = t["closed_at"][:10]
        daily[day] = daily.get(day, 0.0) + t["pnl"]
    cumulative = 0.0
    curve = []
    for day in sorted(daily):
        cumulative += daily[day]
        curve.append({
            "date":           day,
            "daily_pnl":      round(daily[day], 4),
            "cumulative_pnl": round(cumulative, 4),
        })
    return curve


def _calc_max_drawdown(curve: list[float]) -> float:
    """Max drawdown (negative value) from peak to trough in a cumulative PnL series."""
    if not curve:
        return 0.0
    peak   = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = v - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _build_by_scope(trades: list[dict[str, Any]]) -> dict[str, Any]:
    scopes: dict[str, list[dict]] = {}
    for t in trades:
        scopes.setdefault(t["scope"], []).append(t)
    result: dict[str, Any] = {}
    for sc, sc_trades in sorted(scopes.items()):
        sc_pnls = [t["pnl"] for t in sc_trades]
        sc_wins = sum(t["win"] for t in sc_trades)
        n       = len(sc_trades)
        result[sc] = {
            "total_pnl":   round(sum(sc_pnls), 4),
            "trade_count": n,
            "win_rate":    round(sc_wins / n, 4) if n else 0.0,
            "avg_pnl":     round(sum(sc_pnls) / n, 4) if n else 0.0,
        }
    return result


def _build_recent_trades(trades: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "symbol":    t["symbol"],
            "scope":     t["scope"],
            "pnl":       round(t["pnl"], 4),
            "win":       t["win"],
            "closed_at": t["closed_at"][:16],
        }
        for t in reversed(trades[-limit:])
    ]
