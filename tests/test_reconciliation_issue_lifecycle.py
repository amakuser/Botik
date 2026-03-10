from __future__ import annotations

import asyncio
from pathlib import Path

from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.main import get_reconciliation_entry_block_reason
from src.botik.storage.futures_store import upsert_futures_position
from src.botik.storage.sqlite_store import get_connection


class _LinearReconExecutor:
    def __init__(self, *, positions: list[dict] | None = None, open_orders: list[dict] | None = None) -> None:
        self._positions = list(positions or [])
        self._open_orders = list(open_orders or [])

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        return {"retCode": 0, "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000"}]}]}}

    async def get_open_orders(self) -> dict:
        return {"retCode": 0, "result": {"list": list(self._open_orders)}}

    async def get_execution_list(self, symbol: str, limit: int = 100) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_positions(self, symbol: str | None = None) -> dict:
        items = list(self._positions)
        if symbol:
            symbol_u = str(symbol).upper().strip()
            items = [row for row in items if str(row.get("symbol") or "").upper().strip() == symbol_u]
        return {"retCode": 0, "result": {"list": items}}


def _seed_local_position(conn) -> None:
    upsert_futures_position(
        conn,
        account_type="UNIFIED",
        symbol="BTCUSDT",
        side="Buy",
        position_idx=0,
        margin_mode="cross",
        leverage=5.0,
        qty=0.01,
        entry_price=63000.0,
        mark_price=63100.0,
        liq_price=52000.0,
        unrealized_pnl=1.0,
        realized_pnl=0.0,
        take_profit=64000.0,
        stop_loss=62500.0,
        trailing_stop=None,
        protection_status="protected",
        strategy_owner="runtime",
        source_of_truth="runtime",
        recovered_from_exchange=False,
    )


def _exchange_position_row() -> dict:
    return {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "positionIdx": 0,
        "tradeMode": "cross",
        "leverage": "5",
        "size": "0.01",
        "avgPrice": "63000",
        "markPrice": "63100",
        "liqPrice": "52000",
        "unrealisedPnl": "1.0",
        "cumRealisedPnl": "0.0",
        "takeProfit": "64000",
        "stopLoss": "62500",
        "trailingStop": "0",
    }


def test_reconciliation_issue_lifecycle_resolves_and_unlocks_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "reconciliation_issue_lifecycle.db"
    conn = get_connection(db_path)
    try:
        _seed_local_position(conn)
        service_missing = ExchangeReconciliationService(
            conn=conn,
            executor=_LinearReconExecutor(positions=[]),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary_1 = asyncio.run(service_missing.run(trigger_source="test-missing"))
        assert summary_1["status"] == "success"
        assert summary_1["issues_created"] >= 1

        issue_open = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='local_position_missing_on_exchange'
              AND domain='futures'
              AND symbol='BTCUSDT'
              AND LOWER(COALESCE(status, '')) IN ('open', 'active')
            """
        ).fetchone()
        assert issue_open is not None
        assert int(issue_open[0]) >= 1
        assert get_reconciliation_entry_block_reason(conn, symbol="BTCUSDT") is not None

        service_matched = ExchangeReconciliationService(
            conn=conn,
            executor=_LinearReconExecutor(positions=[_exchange_position_row()]),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary_2 = asyncio.run(service_matched.run(trigger_source="test-resolve"))
        assert summary_2["status"] == "success"
        assert int(summary_2.get("issues_resolved") or 0) >= 1
        assert int(summary_2.get("locks_released") or 0) >= 1

        issue_resolved = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='local_position_missing_on_exchange'
              AND domain='futures'
              AND symbol='BTCUSDT'
              AND LOWER(COALESCE(status, '')) IN ('resolved', 'closed')
            """
        ).fetchone()
        assert issue_resolved is not None
        assert int(issue_resolved[0]) >= 1
        assert get_reconciliation_entry_block_reason(conn, symbol="BTCUSDT") is None

        resolved_evt = conn.execute(
            """
            SELECT COUNT(*)
            FROM events_audit
            WHERE event_type='reconciliation_issue_resolved'
              AND domain='futures'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert resolved_evt is not None
        assert int(resolved_evt[0]) >= 1
    finally:
        conn.close()


def test_reconciliation_does_not_false_unlock_when_conflict_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "reconciliation_issue_false_unlock.db"
    conn = get_connection(db_path)
    try:
        _seed_local_position(conn)
        service_missing = ExchangeReconciliationService(
            conn=conn,
            executor=_LinearReconExecutor(positions=[]),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary_1 = asyncio.run(service_missing.run(trigger_source="test-missing-1"))
        assert summary_1["status"] == "success"
        assert get_reconciliation_entry_block_reason(conn, symbol="BTCUSDT") is not None

        summary_2 = asyncio.run(service_missing.run(trigger_source="test-missing-2"))
        assert summary_2["status"] == "success"
        assert int(summary_2.get("issues_resolved") or 0) == 0
        assert get_reconciliation_entry_block_reason(conn, symbol="BTCUSDT") is not None

        open_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='local_position_missing_on_exchange'
              AND domain='futures'
              AND symbol='BTCUSDT'
              AND LOWER(COALESCE(status, '')) IN ('open', 'active')
            """
        ).fetchone()
        assert open_count is not None
        assert int(open_count[0]) >= 1

        resolved_evt = conn.execute(
            """
            SELECT COUNT(*)
            FROM events_audit
            WHERE event_type='reconciliation_issue_resolved'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert resolved_evt is not None
        assert int(resolved_evt[0]) == 0
    finally:
        conn.close()
