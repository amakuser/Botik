from __future__ import annotations

import sqlite3
from pathlib import Path

from botik_app_service.contracts.spot import (
    SpotBalance,
    SpotFill,
    SpotHolding,
    SpotOrder,
    SpotReadSnapshot,
    SpotReadSourceMode,
    SpotReadSummary,
    SpotReadTruncation,
)

OPEN_ORDER_STATUSES = ("new", "open", "partiallyfilled", "partially_filled")
BALANCES_LIMIT = 8
HOLDINGS_LIMIT = 25
ACTIVE_ORDERS_LIMIT = 20
RECENT_FILLS_LIMIT = 20


class LegacySpotReadAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(
        self,
        *,
        account_type: str,
        db_path: Path | None = None,
        source_mode: SpotReadSourceMode,
    ) -> SpotReadSnapshot:
        resolved_db_path = db_path or self._resolve_db_path()
        if not resolved_db_path.exists():
            return self._empty_snapshot(account_type=account_type, source_mode=source_mode)

        try:
            with sqlite3.connect(f"file:{resolved_db_path}?mode=ro", uri=True, timeout=2) as connection:
                connection.row_factory = sqlite3.Row
                return self._build_snapshot(connection, account_type=account_type, source_mode=source_mode)
        except sqlite3.Error:
            return self._empty_snapshot(account_type=account_type, source_mode=source_mode)

    def _build_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        account_type: str,
        source_mode: SpotReadSourceMode,
    ) -> SpotReadSnapshot:
        balances, balances_count = self._read_balances(connection, account_type=account_type)
        holdings = self._read_holdings(connection, account_type=account_type)
        active_orders, open_orders_count = self._read_active_orders(connection, account_type=account_type)
        recent_fills, recent_fills_count = self._read_recent_fills(connection, account_type=account_type)
        pending_intents_count = self._read_pending_intents_count(connection, account_type=account_type)

        summary = SpotReadSummary(
            account_type=account_type,
            balance_assets_count=balances_count,
            holdings_count=len(holdings),
            recovered_holdings_count=sum(1 for row in holdings if row.recovered_from_exchange),
            strategy_owned_holdings_count=sum(1 for row in holdings if row.strategy_owner or row.hold_reason == "strategy_entry"),
            open_orders_count=open_orders_count,
            recent_fills_count=recent_fills_count,
            pending_intents_count=pending_intents_count,
        )

        return SpotReadSnapshot(
            source_mode=source_mode,
            summary=summary,
            balances=balances[:BALANCES_LIMIT],
            holdings=holdings[:HOLDINGS_LIMIT],
            active_orders=active_orders[:ACTIVE_ORDERS_LIMIT],
            recent_fills=recent_fills[:RECENT_FILLS_LIMIT],
            truncated=SpotReadTruncation(
                balances=balances_count > BALANCES_LIMIT,
                holdings=len(holdings) > HOLDINGS_LIMIT,
                active_orders=open_orders_count > ACTIVE_ORDERS_LIMIT,
                recent_fills=recent_fills_count > RECENT_FILLS_LIMIT,
            ),
        )

    def _read_balances(self, connection: sqlite3.Connection, *, account_type: str) -> tuple[list[SpotBalance], int]:
        if not self._table_exists(connection, "spot_balances"):
            return ([], 0)

        count_row = connection.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM spot_balances
            WHERE account_type = ?
              AND ABS(COALESCE(total_qty, 0.0)) > 0
            """,
            (account_type,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT asset, free_qty, locked_qty, total_qty, source_of_truth, updated_at_utc
            FROM spot_balances
            WHERE account_type = ?
              AND ABS(COALESCE(total_qty, 0.0)) > 0
            ORDER BY total_qty DESC, asset ASC
            LIMIT ?
            """,
            (account_type, BALANCES_LIMIT),
        ).fetchall()
        balances = [
            SpotBalance(
                asset=str(row["asset"]),
                free_qty=float(row["free_qty"] or 0.0),
                locked_qty=float(row["locked_qty"] or 0.0),
                total_qty=float(row["total_qty"] or 0.0),
                source_of_truth=str(row["source_of_truth"]) if row["source_of_truth"] is not None else None,
                updated_at_utc=row["updated_at_utc"],
            )
            for row in rows
        ]
        return (balances, int(count_row["cnt"] or 0) if count_row else 0)

    def _read_holdings(self, connection: sqlite3.Connection, *, account_type: str) -> list[SpotHolding]:
        if not self._table_exists(connection, "spot_holdings"):
            return []

        rows = connection.execute(
            """
            SELECT
                account_type, symbol, base_asset, free_qty, locked_qty, avg_entry_price,
                hold_reason, source_of_truth, recovered_from_exchange, strategy_owner,
                auto_sell_allowed, updated_at_utc
            FROM spot_holdings
            WHERE account_type = ?
              AND (
                ABS(COALESCE(free_qty, 0.0)) > 0
                OR ABS(COALESCE(locked_qty, 0.0)) > 0
              )
            ORDER BY updated_at_utc DESC, symbol ASC
            """,
            (account_type,),
        ).fetchall()
        return [
            SpotHolding(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                base_asset=str(row["base_asset"]),
                free_qty=float(row["free_qty"] or 0.0),
                locked_qty=float(row["locked_qty"] or 0.0),
                total_qty=float(row["free_qty"] or 0.0) + float(row["locked_qty"] or 0.0),
                avg_entry_price=float(row["avg_entry_price"]) if row["avg_entry_price"] is not None else None,
                hold_reason=str(row["hold_reason"]),
                source_of_truth=str(row["source_of_truth"]),
                recovered_from_exchange=bool(int(row["recovered_from_exchange"] or 0)),
                strategy_owner=str(row["strategy_owner"]) if row["strategy_owner"] is not None else None,
                auto_sell_allowed=bool(int(row["auto_sell_allowed"] or 0)),
                updated_at_utc=row["updated_at_utc"],
            )
            for row in rows
        ]

    def _read_active_orders(self, connection: sqlite3.Connection, *, account_type: str) -> tuple[list[SpotOrder], int]:
        if not self._table_exists(connection, "spot_orders"):
            return ([], 0)

        placeholders = ",".join("?" for _ in OPEN_ORDER_STATUSES)
        params = [account_type, *OPEN_ORDER_STATUSES]
        count_row = connection.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM spot_orders
            WHERE account_type = ?
              AND LOWER(COALESCE(status, '')) IN ({placeholders})
            """,
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                account_type, symbol, side, order_id, order_link_id, order_type, time_in_force,
                price, qty, filled_qty, status, strategy_owner, updated_at_utc
            FROM spot_orders
            WHERE account_type = ?
              AND LOWER(COALESCE(status, '')) IN ({placeholders})
            ORDER BY updated_at_utc DESC, id DESC
            LIMIT ?
            """,
            (*params, ACTIVE_ORDERS_LIMIT),
        ).fetchall()
        orders = [
            SpotOrder(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                order_id=str(row["order_id"]) if row["order_id"] is not None else None,
                order_link_id=str(row["order_link_id"]) if row["order_link_id"] is not None else None,
                order_type=str(row["order_type"]) if row["order_type"] is not None else None,
                time_in_force=str(row["time_in_force"]) if row["time_in_force"] is not None else None,
                price=float(row["price"] or 0.0),
                qty=float(row["qty"] or 0.0),
                filled_qty=float(row["filled_qty"] or 0.0),
                status=str(row["status"]),
                strategy_owner=str(row["strategy_owner"]) if row["strategy_owner"] is not None else None,
                updated_at_utc=row["updated_at_utc"],
            )
            for row in rows
        ]
        return (orders, int(count_row["cnt"] or 0) if count_row else 0)

    def _read_recent_fills(self, connection: sqlite3.Connection, *, account_type: str) -> tuple[list[SpotFill], int]:
        if not self._table_exists(connection, "spot_fills"):
            return ([], 0)

        count_row = connection.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM spot_fills
            WHERE account_type = ?
            """,
            (account_type,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT
                account_type, symbol, side, exec_id, order_id, order_link_id, price, qty,
                fee, fee_currency, is_maker, exec_time_ms, created_at_utc
            FROM spot_fills
            WHERE account_type = ?
            ORDER BY COALESCE(exec_time_ms, 0) DESC, id DESC
            LIMIT ?
            """,
            (account_type, RECENT_FILLS_LIMIT),
        ).fetchall()
        fills = [
            SpotFill(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                exec_id=str(row["exec_id"]),
                order_id=str(row["order_id"]) if row["order_id"] is not None else None,
                order_link_id=str(row["order_link_id"]) if row["order_link_id"] is not None else None,
                price=float(row["price"] or 0.0),
                qty=float(row["qty"] or 0.0),
                fee=float(row["fee"]) if row["fee"] is not None else None,
                fee_currency=str(row["fee_currency"]) if row["fee_currency"] is not None else None,
                is_maker=(None if row["is_maker"] is None else bool(int(row["is_maker"] or 0))),
                exec_time_ms=int(row["exec_time_ms"]) if row["exec_time_ms"] is not None else None,
                created_at_utc=row["created_at_utc"],
            )
            for row in rows
        ]
        return (fills, int(count_row["cnt"] or 0) if count_row else 0)

    def _read_pending_intents_count(self, connection: sqlite3.Connection, *, account_type: str) -> int:
        if not self._table_exists(connection, "spot_position_intents"):
            return 0
        row = connection.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM spot_position_intents
            WHERE account_type = ?
            """,
            (account_type,),
        ).fetchone()
        return int(row["cnt"] or 0) if row else 0

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
    def _empty_snapshot(*, account_type: str, source_mode: SpotReadSourceMode) -> SpotReadSnapshot:
        return SpotReadSnapshot(
            source_mode=source_mode,
            summary=SpotReadSummary(account_type=account_type),
        )
