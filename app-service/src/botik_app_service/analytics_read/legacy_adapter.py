from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from botik_app_service.contracts.analytics import (
    AnalyticsClosedTrade,
    AnalyticsEquityPoint,
    AnalyticsReadSnapshot,
    AnalyticsReadSourceMode,
    AnalyticsReadTruncation,
    AnalyticsSummary,
)

MAX_TRADES_PER_SOURCE = 250
EQUITY_CURVE_LIMIT = 60
RECENT_CLOSED_TRADES_LIMIT = 20


class LegacyAnalyticsReadAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(
        self,
        *,
        db_path: Path | None = None,
        source_mode: AnalyticsReadSourceMode,
    ) -> AnalyticsReadSnapshot:
        resolved_db_path = db_path or self._resolve_db_path()
        if not resolved_db_path.exists():
            return self._empty_snapshot(source_mode=source_mode)

        try:
            with sqlite3.connect(f"file:{resolved_db_path}?mode=ro", uri=True, timeout=2) as connection:
                connection.row_factory = sqlite3.Row
                return self._build_snapshot(connection, source_mode=source_mode)
        except sqlite3.Error:
            return self._empty_snapshot(source_mode=source_mode)

    def _build_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        source_mode: AnalyticsReadSourceMode,
    ) -> AnalyticsReadSnapshot:
        trades = self._collect_bounded_trades(connection)
        if not trades:
            return self._empty_snapshot(source_mode=source_mode)

        from src.botik.gui.api_analytics_mixin import _compute_analytics

        analytics = _compute_analytics(trades)
        wins = sum(int(trade["win"]) for trade in trades)
        total_trades = len(trades)
        recent_trades = analytics.get("recent_trades", [])
        equity_curve = analytics.get("equity_curve", [])

        return AnalyticsReadSnapshot(
            source_mode=source_mode,
            summary=AnalyticsSummary(
                total_closed_trades=total_trades,
                winning_trades=wins,
                losing_trades=max(total_trades - wins, 0),
                win_rate=float(analytics.get("win_rate") or 0.0),
                total_net_pnl=float(analytics.get("total_pnl") or 0.0),
                average_net_pnl=float(analytics.get("avg_pnl") or 0.0),
                today_net_pnl=float(analytics.get("today_pnl") or 0.0),
            ),
            equity_curve=[
                AnalyticsEquityPoint(
                    date=str(row["date"]),
                    daily_pnl=float(row["daily_pnl"] or 0.0),
                    cumulative_pnl=float(row["cumulative_pnl"] or 0.0),
                )
                for row in equity_curve[-EQUITY_CURVE_LIMIT:]
            ],
            recent_closed_trades=[
                AnalyticsClosedTrade(
                    symbol=str(row["symbol"]),
                    scope=str(row["scope"]),
                    net_pnl=float(row["pnl"] or 0.0),
                    was_profitable=bool(int(row["win"] or 0)),
                    closed_at=str(row["closed_at"]),
                )
                for row in recent_trades[:RECENT_CLOSED_TRADES_LIMIT]
            ],
            truncated=AnalyticsReadTruncation(
                equity_curve=len(equity_curve) > EQUITY_CURVE_LIMIT,
                recent_closed_trades=len(recent_trades) > RECENT_CLOSED_TRADES_LIMIT,
            ),
        )

    def _collect_bounded_trades(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        trades: list[dict[str, Any]] = []
        trades.extend(self._read_futures_paper(connection))
        trades.extend(self._read_outcomes(connection))
        trades.sort(key=lambda row: row["closed_at"])
        return trades

    def _read_futures_paper(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        if not self._table_exists(connection, "futures_paper_trades"):
            return []
        columns = self._table_columns(connection, "futures_paper_trades")
        pnl_column = "net_pnl" if "net_pnl" in columns else ("gross_pnl" if "gross_pnl" in columns else None)
        if pnl_column is None:
            return []

        rows = connection.execute(
            f"""
            SELECT
                symbol,
                COALESCE(model_scope, 'futures') AS model_scope,
                COALESCE({pnl_column}, 0.0) AS pnl,
                COALESCE(was_profitable, CASE WHEN {pnl_column} > 0 THEN 1 ELSE 0 END) AS win,
                closed_at_utc
            FROM futures_paper_trades
            WHERE closed_at_utc IS NOT NULL
            ORDER BY closed_at_utc DESC
            LIMIT ?
            """,
            (MAX_TRADES_PER_SOURCE,),
        ).fetchall()
        return [
            {
                "symbol": str(row["symbol"]),
                "scope": str(row["model_scope"]),
                "pnl": float(row["pnl"] or 0.0),
                "win": int(row["win"] or 0),
                "closed_at": str(row["closed_at_utc"]),
            }
            for row in reversed(rows)
        ]

    def _read_outcomes(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        if not self._table_exists(connection, "outcomes"):
            return []
        columns = self._table_columns(connection, "outcomes")
        pnl_column = "net_pnl_quote" if "net_pnl_quote" in columns else ("gross_pnl_quote" if "gross_pnl_quote" in columns else None)
        if pnl_column is None:
            return []

        rows = connection.execute(
            f"""
            SELECT
                symbol,
                COALESCE(model_scope, 'spot') AS model_scope,
                COALESCE({pnl_column}, 0.0) AS pnl,
                COALESCE(was_profitable, CASE WHEN {pnl_column} > 0 THEN 1 ELSE 0 END) AS win,
                closed_at_utc
            FROM outcomes
            WHERE closed_at_utc IS NOT NULL
            ORDER BY closed_at_utc DESC
            LIMIT ?
            """,
            (MAX_TRADES_PER_SOURCE,),
        ).fetchall()
        return [
            {
                "symbol": str(row["symbol"]),
                "scope": str(row["model_scope"]),
                "pnl": float(row["pnl"] or 0.0),
                "win": int(row["win"] or 0),
                "closed_at": str(row["closed_at_utc"]),
            }
            for row in reversed(rows)
        ]

    def _resolve_db_path(self) -> Path:
        from src.botik.gui.api_helpers import _load_yaml, _resolve_db_path

        return _resolve_db_path(_load_yaml())

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}

    @staticmethod
    def _empty_snapshot(*, source_mode: AnalyticsReadSourceMode) -> AnalyticsReadSnapshot:
        return AnalyticsReadSnapshot(source_mode=source_mode)
