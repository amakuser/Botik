import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.spot_read.service import SpotReadService
from src.botik.storage.spot_store import (
    ensure_spot_schema,
    insert_spot_fill,
    insert_spot_position_intent,
    upsert_spot_balance,
    upsert_spot_holding,
    upsert_spot_order,
)


def _create_spot_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        ensure_spot_schema(connection)
        upsert_spot_balance(
            connection,
            account_type="UNIFIED",
            asset="BTC",
            free_qty=0.01,
            locked_qty=0.0,
            source_of_truth="fixture",
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        upsert_spot_balance(
            connection,
            account_type="UNIFIED",
            asset="USDT",
            free_qty=1200.0,
            locked_qty=100.0,
            source_of_truth="fixture",
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        upsert_spot_holding(
            connection,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            base_asset="BTC",
            free_qty=0.01,
            locked_qty=0.0,
            avg_entry_price=60000.0,
            hold_reason="strategy_entry",
            source_of_truth="fixture",
            recovered_from_exchange=False,
            strategy_owner="spot_spread",
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        upsert_spot_holding(
            connection,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            base_asset="ETH",
            free_qty=0.2,
            locked_qty=0.0,
            avg_entry_price=3000.0,
            hold_reason="unknown_recovered_from_exchange",
            source_of_truth="fixture",
            recovered_from_exchange=True,
            strategy_owner=None,
            updated_at_utc="2026-04-11T11:55:00Z",
        )
        upsert_spot_order(
            connection,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Buy",
            status="New",
            price=60000.0,
            qty=0.01,
            order_id="order-1",
            order_link_id="link-1",
            order_type="Limit",
            time_in_force="PostOnly",
            strategy_owner="spot_spread",
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        insert_spot_fill(
            connection,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Buy",
            exec_id="exec-1",
            order_id="order-1",
            order_link_id="link-1",
            price=60000.0,
            qty=0.01,
            fee=0.02,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1700000000123,
            created_at_utc="2026-04-11T12:00:00Z",
        )
        insert_spot_position_intent(
            connection,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Buy",
            intended_qty=0.01,
            intended_price=60000.0,
            strategy_owner="spot_spread",
            created_at_utc="2026-04-11T12:00:00Z",
        )
    finally:
        connection.close()


def test_spot_read_service_returns_fixture_backed_snapshot(tmp_path):
    fixture_db_path = tmp_path / "spot.fixture.sqlite3"
    _create_spot_fixture_db(fixture_db_path)

    service = SpotReadService(repo_root=REPO_ROOT, fixture_db_path=fixture_db_path)
    snapshot = service.snapshot()

    assert snapshot.source_mode == "fixture"
    assert snapshot.summary.account_type == "UNIFIED"
    assert snapshot.summary.balance_assets_count == 2
    assert snapshot.summary.holdings_count == 2
    assert snapshot.summary.recovered_holdings_count == 1
    assert snapshot.summary.strategy_owned_holdings_count == 1
    assert snapshot.summary.open_orders_count == 1
    assert snapshot.summary.recent_fills_count == 1
    assert snapshot.summary.pending_intents_count == 1
    assert snapshot.balances[0].asset == "USDT"
    assert {holding.symbol for holding in snapshot.holdings} == {"BTCUSDT", "ETHUSDT"}
    assert snapshot.active_orders[0].symbol == "BTCUSDT"
    assert snapshot.recent_fills[0].exec_id == "exec-1"
