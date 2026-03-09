from __future__ import annotations

from pathlib import Path

from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.storage.futures_store import upsert_futures_position
from src.botik.storage.sqlite_store import get_connection


class _LinearEmptyExecutorStub:
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        return {"retCode": 0, "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000"}]}]}}

    async def get_open_orders(self) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_execution_list(self, symbol: str, limit: int = 100) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_positions(self, symbol: str | None = None) -> dict:
        return {"retCode": 0, "result": {"list": []}}


def test_reconciliation_flags_local_position_missing_on_exchange(tmp_path: Path) -> None:
    db_path = tmp_path / "conflict_reconciliation.db"
    conn = get_connection(db_path)
    try:
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
            mark_price=62900.0,
            liq_price=52000.0,
            unrealized_pnl=-1.0,
            realized_pnl=0.0,
            take_profit=64000.0,
            stop_loss=62500.0,
            trailing_stop=None,
            protection_status="protected",
            strategy_owner="runtime",
            source_of_truth="local",
            recovered_from_exchange=False,
        )
        service = ExchangeReconciliationService(
            conn=conn,
            executor=_LinearEmptyExecutorStub(),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary = __import__("asyncio").run(service.run(trigger_source="test"))
        assert summary["status"] == "success"
        issue = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='local_position_missing_on_exchange'
              AND domain='futures'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert issue is not None
        assert int(issue[0]) >= 1
    finally:
        conn.close()
