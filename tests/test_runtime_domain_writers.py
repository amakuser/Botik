from __future__ import annotations

import logging
from pathlib import Path

from src.botik.main import (
    write_runtime_fill_legacy_and_domain,
    write_runtime_order_legacy_and_domain,
    write_spot_exit_decision_safe,
    write_spot_position_intent_safe,
)
from src.botik.storage.sqlite_store import get_connection


def test_runtime_domain_writers_write_legacy_and_domain_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_domain_writers.db"
    conn = get_connection(db_path)
    log = logging.getLogger("test.runtime_domain_writers")
    try:
        write_runtime_order_legacy_and_domain(
            conn,
            market_category="spot",
            symbol="BTCUSDT",
            side="Buy",
            order_link_id="spot-entry-1",
            price=60000.0,
            qty=0.001,
            status="New",
            created_at_utc="2026-03-10T10:00:00Z",
            log=log,
            exchange_order_id="spot-order-1",
            order_type="Limit",
            time_in_force="PostOnly",
            strategy_owner="TestStrategy",
            filled_qty=0.0,
        )
        legacy_spot_order = conn.execute(
            "SELECT order_link_id, symbol, side FROM orders WHERE order_link_id='spot-entry-1'"
        ).fetchone()
        domain_spot_order = conn.execute(
            "SELECT order_link_id, symbol, side FROM spot_orders WHERE order_link_id='spot-entry-1'"
        ).fetchone()
        assert legacy_spot_order is not None
        assert domain_spot_order is not None

        write_runtime_fill_legacy_and_domain(
            conn,
            market_category="spot",
            symbol="BTCUSDT",
            side="Buy",
            exec_id="spot-exec-1",
            price=60000.0,
            qty=0.001,
            filled_at_utc="2026-03-10T10:00:01Z",
            log=log,
            order_link_id="spot-entry-1",
            exchange_order_id="spot-order-1",
            fee=0.01,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1,
        )
        legacy_spot_fill = conn.execute(
            "SELECT order_link_id, symbol FROM fills WHERE order_link_id='spot-entry-1'"
        ).fetchone()
        domain_spot_fill = conn.execute(
            "SELECT exec_id, symbol FROM spot_fills WHERE exec_id='spot-exec-1'"
        ).fetchone()
        assert legacy_spot_fill is not None
        assert domain_spot_fill is not None

        write_spot_position_intent_safe(
            conn,
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
            price=60000.0,
            order_link_id="spot-entry-intent-1",
            strategy_owner="TestStrategy",
            profile_id="default",
            signal_id="sig-spot-1",
            log=log,
        )
        spot_intent = conn.execute(
            "SELECT intent_id, symbol FROM spot_position_intents WHERE intent_id='sp-intent-spot-entry-intent-1'"
        ).fetchone()
        assert spot_intent is not None

        write_spot_exit_decision_safe(
            conn,
            symbol="BTCUSDT",
            decision_type="forced_exit_submitted",
            reason="stop_loss",
            pnl_pct=-0.02,
            payload={"test": True},
            applied=True,
            log=log,
        )
        spot_exit_decision = conn.execute(
            "SELECT decision_type, symbol, applied FROM spot_exit_decisions WHERE symbol='BTCUSDT' ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
        assert spot_exit_decision is not None
        assert str(spot_exit_decision[0]) == "forced_exit_submitted"
        assert int(spot_exit_decision[2]) == 1

        write_runtime_order_legacy_and_domain(
            conn,
            market_category="linear",
            symbol="ETHUSDT",
            side="Sell",
            order_link_id="fut-entry-1",
            price=3200.0,
            qty=0.01,
            status="New",
            created_at_utc="2026-03-10T10:01:00Z",
            log=log,
            exchange_order_id="fut-order-1",
            order_type="Limit",
            time_in_force="IOC",
            strategy_owner="TestStrategy",
            filled_qty=0.0,
        )
        legacy_fut_order = conn.execute(
            "SELECT order_link_id, symbol, side FROM orders WHERE order_link_id='fut-entry-1'"
        ).fetchone()
        domain_fut_order = conn.execute(
            "SELECT order_link_id, symbol, side FROM futures_open_orders WHERE order_link_id='fut-entry-1'"
        ).fetchone()
        assert legacy_fut_order is not None
        assert domain_fut_order is not None

        write_runtime_fill_legacy_and_domain(
            conn,
            market_category="linear",
            symbol="ETHUSDT",
            side="Sell",
            exec_id="fut-exec-1",
            price=3200.0,
            qty=0.01,
            filled_at_utc="2026-03-10T10:01:01Z",
            log=log,
            order_link_id="fut-entry-1",
            exchange_order_id="fut-order-1",
            fee=0.02,
            fee_currency="USDT",
            is_maker=False,
            exec_time_ms=2,
        )
        legacy_fut_fill = conn.execute(
            "SELECT order_link_id, symbol FROM fills WHERE order_link_id='fut-entry-1'"
        ).fetchone()
        domain_fut_fill = conn.execute(
            "SELECT exec_id, symbol FROM futures_fills WHERE exec_id='fut-exec-1'"
        ).fetchone()
        assert legacy_fut_fill is not None
        assert domain_fut_fill is not None
    finally:
        conn.close()
