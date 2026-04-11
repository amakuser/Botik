import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.futures_read.service import FuturesReadService
from src.botik.storage.futures_store import (
    ensure_futures_schema,
    insert_futures_fill,
    upsert_futures_open_order,
    upsert_futures_position,
)


def _create_futures_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        ensure_futures_schema(connection)
        upsert_futures_position(
            connection,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=1,
            margin_mode="cross",
            leverage=5.0,
            qty=0.02,
            entry_price=3000.0,
            mark_price=3010.5,
            liq_price=2500.0,
            unrealized_pnl=42.125,
            realized_pnl=None,
            take_profit=3050.0,
            stop_loss=2950.0,
            trailing_stop=None,
            protection_status="protected",
            strategy_owner="futures_spike_reversal",
            source_of_truth="fixture",
            recovered_from_exchange=False,
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        upsert_futures_position(
            connection,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Sell",
            position_idx=2,
            margin_mode="isolated",
            leverage=3.0,
            qty=0.01,
            entry_price=65000.0,
            mark_price=65100.0,
            liq_price=70000.0,
            unrealized_pnl=-10.5,
            realized_pnl=None,
            take_profit=64000.0,
            stop_loss=65500.0,
            trailing_stop=None,
            protection_status="repairing",
            strategy_owner=None,
            source_of_truth="fixture",
            recovered_from_exchange=True,
            updated_at_utc="2026-04-11T11:58:00Z",
        )
        upsert_futures_open_order(
            connection,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            status="New",
            order_id="fut-order-1",
            order_link_id="fut-link-1",
            side="Sell",
            order_type="Limit",
            time_in_force="GTC",
            price=3050.0,
            qty=0.02,
            reduce_only=True,
            close_on_trigger=False,
            strategy_owner="futures_spike_reversal",
            updated_at_utc="2026-04-11T12:00:00Z",
        )
        insert_futures_fill(
            connection,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            exec_id="fut-exec-1",
            order_id="fut-order-1",
            order_link_id="fut-link-1",
            price=3001.0,
            qty=0.02,
            exec_fee=0.15,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1700000000123,
            created_at_utc="2026-04-11T12:00:00Z",
        )
    finally:
        connection.close()


def test_futures_read_service_returns_fixture_backed_snapshot(tmp_path):
    fixture_db_path = tmp_path / "futures.fixture.sqlite3"
    _create_futures_fixture_db(fixture_db_path)

    service = FuturesReadService(repo_root=REPO_ROOT, fixture_db_path=fixture_db_path)
    snapshot = service.snapshot()

    assert snapshot.source_mode == "fixture"
    assert snapshot.summary.account_type == "UNIFIED"
    assert snapshot.summary.positions_count == 2
    assert snapshot.summary.protected_positions_count == 1
    assert snapshot.summary.attention_positions_count == 1
    assert snapshot.summary.recovered_positions_count == 1
    assert snapshot.summary.open_orders_count == 1
    assert snapshot.summary.recent_fills_count == 1
    assert round(snapshot.summary.unrealized_pnl_total, 3) == 31.625
    assert {position.symbol for position in snapshot.positions} == {"ETHUSDT", "BTCUSDT"}
    assert snapshot.active_orders[0].symbol == "ETHUSDT"
    assert snapshot.recent_fills[0].exec_id == "fut-exec-1"
