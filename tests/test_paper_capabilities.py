from __future__ import annotations

import asyncio

from src.botik.execution.paper import PaperTradingClient
from src.botik.main import executor_supports_capability, verify_futures_protection_from_exchange
from src.botik.state.state import TradingState


def test_paper_capabilities_are_explicit_and_not_falsely_protected() -> None:
    client = PaperTradingClient(state=TradingState(), fill_on_cross=True, category="linear")

    assert executor_supports_capability(client, "reconciliation", market_category="linear") is False
    assert executor_supports_capability(client, "protection", market_category="linear") is False

    wallet_resp = asyncio.run(client.get_wallet_balance(account_type="UNIFIED"))
    assert wallet_resp.get("retCode") == 0

    stop_resp = asyncio.run(
        client.set_trading_stop(
            symbol="BTCUSDT",
            position_idx=0,
            stop_loss=62000.0,
            take_profit=65000.0,
            trailing_stop=None,
        )
    )
    assert stop_resp.get("retCode") != 0

    pos_resp = asyncio.run(client.get_positions(symbol="BTCUSDT"))
    assert pos_resp.get("retCode") != 0

    status, payload = asyncio.run(
        verify_futures_protection_from_exchange(
            client,
            symbol="BTCUSDT",
            side="Buy",
            position_idx=0,
        )
    )
    assert status == "failed"
    assert str(payload.get("verify_reason") or "").startswith("positions_api_")

    order_resp = asyncio.run(
        client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            qty="0.001",
            price="0",
            order_link_id="paper-market-1",
            time_in_force="IOC",
            order_type="Market",
        )
    )
    assert order_resp.get("retCode") == 0
