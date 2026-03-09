from __future__ import annotations

from pathlib import Path

from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.storage.sqlite_store import get_connection


class _FuturesExecutorStub:
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        return {
            "retCode": 0,
            "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "500", "free": "500"}]}]},
        }

    async def get_open_orders(self) -> dict:
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Sell",
                        "orderId": "oid-1",
                        "orderLinkId": "ol-1",
                        "orderStatus": "New",
                        "orderType": "Limit",
                        "timeInForce": "PostOnly",
                        "price": "64000",
                        "qty": "0.001",
                        "reduceOnly": True,
                        "closeOnTrigger": False,
                    }
                ]
            },
        }

    async def get_execution_list(self, symbol: str, limit: int = 100) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_positions(self, symbol: str | None = None) -> dict:
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "positionIdx": 1,
                        "tradeMode": "cross",
                        "leverage": "5",
                        "size": "0.01",
                        "avgPrice": "63000",
                        "markPrice": "62800",
                        "liqPrice": "52000",
                        "unrealisedPnl": "-2.1",
                        "cumRealisedPnl": "0.0",
                        "takeProfit": "0",
                        "stopLoss": "0",
                        "trailingStop": "0",
                        "positionStatus": "Normal",
                    }
                ]
            },
        }


def test_futures_reconciliation_imports_orphaned_position_and_flags_unprotected(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_recon.db"
    conn = get_connection(db_path)
    try:
        service = ExchangeReconciliationService(
            conn=conn,
            executor=_FuturesExecutorStub(),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary = __import__("asyncio").run(service.run(trigger_source="test"))
        assert summary["status"] == "success"
        pos = conn.execute(
            """
            SELECT qty, protection_status, recovered_from_exchange, stop_loss, take_profit
            FROM futures_positions
            WHERE account_type='UNIFIED' AND symbol='BTCUSDT' AND side='Buy' AND position_idx=1
            """
        ).fetchone()
        assert pos is not None
        assert float(pos[0]) > 0
        assert str(pos[1]) == "unprotected"
        assert int(pos[2]) == 1
        assert pos[3] is None
        assert pos[4] is None

        issue_orphan = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='orphaned_exchange_position'
              AND domain='futures'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert issue_orphan is not None
        assert int(issue_orphan[0]) >= 1

        issue_unprotected = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='unprotected_position'
              AND domain='futures'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert issue_unprotected is not None
        assert int(issue_unprotected[0]) >= 1

        issue_order = conn.execute(
            """
            SELECT COUNT(*)
            FROM reconciliation_issues
            WHERE issue_type='orphaned_exchange_order'
              AND domain='futures'
              AND symbol='BTCUSDT'
            """
        ).fetchone()
        assert issue_order is not None
        assert int(issue_order[0]) >= 1
    finally:
        conn.close()
