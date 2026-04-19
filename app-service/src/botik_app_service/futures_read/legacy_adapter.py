from __future__ import annotations

import sqlite3
from pathlib import Path

from botik_app_service.contracts.futures import (
    FuturesFill,
    FuturesOpenOrder,
    FuturesPosition,
    FuturesReadSnapshot,
    FuturesReadSourceMode,
    FuturesReadSummary,
    FuturesReadTruncation,
)

OPEN_ORDER_STATUSES = ("new", "open", "partiallyfilled", "partially_filled")
ATTENTION_PROTECTION_STATUSES = {"pending", "repairing", "failed", "unprotected", "close_requested"}
POSITIONS_LIMIT = 20
ACTIVE_ORDERS_LIMIT = 20
RECENT_FILLS_LIMIT = 20


class LegacyFuturesReadAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(
        self,
        *,
        account_type: str,
        db_path: Path | None = None,
        source_mode: FuturesReadSourceMode,
    ) -> FuturesReadSnapshot:
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
        source_mode: FuturesReadSourceMode,
    ) -> FuturesReadSnapshot:
        positions = self._read_positions(connection, account_type=account_type)
        active_orders, open_orders_count = self._read_active_orders(connection, account_type=account_type)
        recent_fills, recent_fills_count = self._read_recent_fills(connection, account_type=account_type)

        summary = FuturesReadSummary(
            account_type=account_type,
            positions_count=len(positions),
            protected_positions_count=sum(
                1 for row in positions if str(row.protection_status).strip().lower() == "protected"
            ),
            attention_positions_count=sum(
                1 for row in positions if str(row.protection_status).strip().lower() in ATTENTION_PROTECTION_STATUSES
            ),
            recovered_positions_count=sum(1 for row in positions if row.recovered_from_exchange),
            open_orders_count=open_orders_count,
            recent_fills_count=recent_fills_count,
            unrealized_pnl_total=round(
                sum(float(row.unrealized_pnl or 0.0) for row in positions),
                8,
            ),
        )

        return FuturesReadSnapshot(
            source_mode=source_mode,
            summary=summary,
            positions=positions[:POSITIONS_LIMIT],
            active_orders=active_orders[:ACTIVE_ORDERS_LIMIT],
            recent_fills=recent_fills[:RECENT_FILLS_LIMIT],
            truncated=FuturesReadTruncation(
                positions=len(positions) > POSITIONS_LIMIT,
                active_orders=open_orders_count > ACTIVE_ORDERS_LIMIT,
                recent_fills=recent_fills_count > RECENT_FILLS_LIMIT,
            ),
        )

    def _read_positions(self, connection: sqlite3.Connection, *, account_type: str) -> list[FuturesPosition]:
        if not self._table_exists(connection, "futures_positions"):
            return []

        rows = connection.execute(
            """
            SELECT
                account_type, symbol, side, position_idx, margin_mode, leverage, qty,
                entry_price, mark_price, liq_price, unrealized_pnl, take_profit, stop_loss,
                protection_status, source_of_truth, recovered_from_exchange, strategy_owner, updated_at_utc
            FROM futures_positions
            WHERE account_type = ?
              AND ABS(COALESCE(qty, 0.0)) > 0
            ORDER BY updated_at_utc DESC, symbol ASC, side ASC
            """,
            (account_type,),
        ).fetchall()
        return [
            FuturesPosition(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                position_idx=int(row["position_idx"] or 0),
                margin_mode=str(row["margin_mode"]) if row["margin_mode"] is not None else None,
                leverage=float(row["leverage"]) if row["leverage"] is not None else None,
                qty=float(row["qty"] or 0.0),
                entry_price=float(row["entry_price"]) if row["entry_price"] is not None else None,
                mark_price=float(row["mark_price"]) if row["mark_price"] is not None else None,
                liq_price=float(row["liq_price"]) if row["liq_price"] is not None else None,
                unrealized_pnl=float(row["unrealized_pnl"]) if row["unrealized_pnl"] is not None else None,
                take_profit=float(row["take_profit"]) if row["take_profit"] is not None else None,
                stop_loss=float(row["stop_loss"]) if row["stop_loss"] is not None else None,
                protection_status=str(row["protection_status"]),
                source_of_truth=str(row["source_of_truth"]),
                recovered_from_exchange=bool(int(row["recovered_from_exchange"] or 0)),
                strategy_owner=str(row["strategy_owner"]) if row["strategy_owner"] is not None else None,
                updated_at_utc=row["updated_at_utc"],
            )
            for row in rows
        ]

    def _read_active_orders(
        self,
        connection: sqlite3.Connection,
        *,
        account_type: str,
    ) -> tuple[list[FuturesOpenOrder], int]:
        if not self._table_exists(connection, "futures_open_orders"):
            return ([], 0)

        placeholders = ",".join("?" for _ in OPEN_ORDER_STATUSES)
        params = [account_type, *OPEN_ORDER_STATUSES]
        count_row = connection.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM futures_open_orders
            WHERE account_type = ?
              AND LOWER(COALESCE(status, '')) IN ({placeholders})
            """,
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                account_type, symbol, side, order_id, order_link_id, order_type, time_in_force,
                price, qty, status, reduce_only, close_on_trigger, strategy_owner, updated_at_utc
            FROM futures_open_orders
            WHERE account_type = ?
              AND LOWER(COALESCE(status, '')) IN ({placeholders})
            ORDER BY updated_at_utc DESC, id DESC
            LIMIT ?
            """,
            (*params, ACTIVE_ORDERS_LIMIT),
        ).fetchall()
        orders = [
            FuturesOpenOrder(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]) if row["side"] is not None else None,
                order_id=str(row["order_id"]) if row["order_id"] is not None else None,
                order_link_id=str(row["order_link_id"]) if row["order_link_id"] is not None else None,
                order_type=str(row["order_type"]) if row["order_type"] is not None else None,
                time_in_force=str(row["time_in_force"]) if row["time_in_force"] is not None else None,
                price=float(row["price"]) if row["price"] is not None else None,
                qty=float(row["qty"]) if row["qty"] is not None else None,
                status=str(row["status"]),
                reduce_only=(None if row["reduce_only"] is None else bool(int(row["reduce_only"] or 0))),
                close_on_trigger=(
                    None if row["close_on_trigger"] is None else bool(int(row["close_on_trigger"] or 0))
                ),
                strategy_owner=str(row["strategy_owner"]) if row["strategy_owner"] is not None else None,
                updated_at_utc=row["updated_at_utc"],
            )
            for row in rows
        ]
        return (orders, int(count_row["cnt"] or 0) if count_row else 0)

    def _read_recent_fills(self, connection: sqlite3.Connection, *, account_type: str) -> tuple[list[FuturesFill], int]:
        if not self._table_exists(connection, "futures_fills"):
            return ([], 0)

        count_row = connection.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM futures_fills
            WHERE account_type = ?
            """,
            (account_type,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT
                account_type, symbol, side, exec_id, order_id, order_link_id, price, qty,
                exec_fee, fee_currency, is_maker, exec_time_ms, created_at_utc
            FROM futures_fills
            WHERE account_type = ?
            ORDER BY COALESCE(exec_time_ms, 0) DESC, id DESC
            LIMIT ?
            """,
            (account_type, RECENT_FILLS_LIMIT),
        ).fetchall()
        fills = [
            FuturesFill(
                account_type=str(row["account_type"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                exec_id=str(row["exec_id"]),
                order_id=str(row["order_id"]) if row["order_id"] is not None else None,
                order_link_id=str(row["order_link_id"]) if row["order_link_id"] is not None else None,
                price=float(row["price"] or 0.0),
                qty=float(row["qty"] or 0.0),
                exec_fee=float(row["exec_fee"]) if row["exec_fee"] is not None else None,
                fee_currency=str(row["fee_currency"]) if row["fee_currency"] is not None else None,
                is_maker=(None if row["is_maker"] is None else bool(int(row["is_maker"] or 0))),
                exec_time_ms=int(row["exec_time_ms"]) if row["exec_time_ms"] is not None else None,
                created_at_utc=row["created_at_utc"],
            )
            for row in rows
        ]
        return (fills, int(count_row["cnt"] or 0) if count_row else 0)

    def _resolve_db_path(self) -> Path:
        from botik_app_service.infra.legacy_helpers import load_config, resolve_db_path

        return resolve_db_path(self._repo_root, load_config(self._repo_root))

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
    def _empty_snapshot(*, account_type: str, source_mode: FuturesReadSourceMode) -> FuturesReadSnapshot:
        return FuturesReadSnapshot(
            source_mode=source_mode,
            summary=FuturesReadSummary(account_type=account_type),
        )
