from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.storage.spot_store import list_spot_holdings, upsert_spot_holding
from src.botik.storage.sqlite_store import get_connection


class _SpotExecutorStub:
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "coin": [
                            {"coin": "BTC", "walletBalance": "0.15", "free": "0.12"},
                            {"coin": "USDT", "walletBalance": "1000", "free": "1000"},
                        ]
                    }
                ]
            },
        }

    async def get_open_orders(self) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_execution_list(self, symbol: str, limit: int = 100) -> dict:
        return {"retCode": 0, "result": {"list": []}}


def test_spot_reconciliation_imports_recovered_holdings(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_recon.db"
    conn = get_connection(db_path)
    try:
        service = ExchangeReconciliationService(
            conn=conn,
            executor=_SpotExecutorStub(),
            market_category="spot",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary = __import__("asyncio").run(service.run(trigger_source="test"))
        assert summary["status"] == "success"
        holdings = list_spot_holdings(conn, account_type="UNIFIED")
        btc = next((row for row in holdings if row["base_asset"] == "BTC"), None)
        assert btc is not None
        assert btc["hold_reason"] == "unknown_recovered_from_exchange"
        assert btc["recovered_from_exchange"] is True
        assert btc["auto_sell_allowed"] is False

        issue = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='spot_asset_recovered_from_exchange'
              AND domain='spot'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert issue is not None
        assert int(issue[0]) >= 1
    finally:
        conn.close()


def test_spot_reconciliation_marks_local_holding_stale_when_missing_on_exchange(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_recon_stale.db"
    conn = get_connection(db_path)
    try:
        upsert_spot_holding(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            base_asset="ETH",
            free_qty=0.5,
            locked_qty=0.0,
            avg_entry_price=2200.0,
            hold_reason="manual_import",
            source_of_truth="local_manual",
            recovered_from_exchange=False,
            strategy_owner="manual",
            auto_sell_allowed=False,
        )
        service = ExchangeReconciliationService(
            conn=conn,
            executor=_SpotExecutorStub(),
            market_category="spot",
            account_type="UNIFIED",
            managed_symbols=["ETHUSDT"],
        )
        summary = __import__("asyncio").run(service.run(trigger_source="test"))
        assert summary["status"] == "success"

        row = conn.execute(
            "SELECT hold_reason FROM spot_holdings WHERE account_type='UNIFIED' AND symbol='ETHUSDT'"
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "stale_hold"

        issue = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='local_holding_missing_on_exchange'
              AND domain='spot'
              AND symbol='ETHUSDT'
            """
        ).fetchone()
        assert issue is not None
        assert int(issue[0]) >= 1
    finally:
        conn.close()
