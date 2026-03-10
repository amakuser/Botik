from __future__ import annotations

import asyncio
from pathlib import Path

from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.storage.sqlite_store import get_connection


class _TelemetryExecutorStub:
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        return {
            "retCode": 0,
            "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000", "free": "1000"}]}]},
        }

    async def get_open_orders(self) -> dict:
        return {"retCode": 0, "result": {"list": []}}

    async def get_execution_list(self, symbol: str, limit: int = 100) -> dict:
        if str(symbol).upper() != "BTCUSDT":
            return {"retCode": 0, "result": {"list": []}}
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "execId": "trade-exec-1",
                        "orderId": "oid-1",
                        "orderLinkId": "ol-1",
                        "execPrice": "62000",
                        "execQty": "0.001",
                        "execFee": "0.02",
                        "feeCurrency": "USDT",
                        "execTime": "1700000001000",
                        "execType": "Trade",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "execId": "funding-exec-1",
                        "orderId": "",
                        "orderLinkId": "",
                        "execPrice": "0",
                        "execQty": "0",
                        "execFee": "-0.05",
                        "feeCurrency": "USDT",
                        "execTime": "1700000002000",
                        "execType": "Funding",
                        "positionIdx": 1,
                        "fundingRate": "0.0001",
                    },
                ]
            },
        }

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
                        "avgPrice": "61800",
                        "markPrice": "62000",
                        "liqPrice": "58500",
                        "unrealisedPnl": "2.3",
                        "cumRealisedPnl": "0.0",
                        "takeProfit": "62600",
                        "stopLoss": "61200",
                        "trailingStop": "0",
                        "positionMMByMp": "0.012",
                    }
                ]
            },
        }


def test_reconciliation_writes_funding_and_liq_telemetry(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_telemetry.db"
    conn = get_connection(db_path)
    try:
        service = ExchangeReconciliationService(
            conn=conn,
            executor=_TelemetryExecutorStub(),
            market_category="linear",
            account_type="UNIFIED",
            managed_symbols=["BTCUSDT"],
        )
        summary1 = asyncio.run(service.run(trigger_source="test"))
        assert summary1["status"] == "success"
        assert int(summary1.get("funding_events_seen", 0)) == 1
        assert int(summary1.get("liq_risk_snapshots", 0)) >= 1

        funding_row = conn.execute(
            """
            SELECT symbol, funding_rate, funding_fee, funding_time_ms
            FROM futures_funding_events
            WHERE symbol='BTCUSDT'
            ORDER BY funding_time_ms DESC
            LIMIT 1
            """
        ).fetchone()
        assert funding_row is not None
        assert str(funding_row[0]) == "BTCUSDT"
        assert float(funding_row[2]) == -0.05

        liq_row = conn.execute(
            """
            SELECT symbol, distance_to_liq_bps
            FROM futures_liquidation_risk_snapshots
            WHERE symbol='BTCUSDT'
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        assert liq_row is not None
        assert str(liq_row[0]) == "BTCUSDT"
        assert float(liq_row[1]) > 0

        # Re-running with same payload should not duplicate funding events.
        summary2 = asyncio.run(service.run(trigger_source="test"))
        assert summary2["status"] == "success"
        assert int(summary2.get("funding_events_seen", 0)) == 0

        funding_count = conn.execute("SELECT COUNT(*) FROM futures_funding_events WHERE symbol='BTCUSDT'").fetchone()
        assert funding_count is not None
        assert int(funding_count[0]) == 1
    finally:
        conn.close()

