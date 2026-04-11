import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app
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


def test_spot_endpoint_returns_fixture_snapshot(tmp_path):
    fixture_db_path = tmp_path / "spot.fixture.sqlite3"
    _create_spot_fixture_db(fixture_db_path)

    settings = Settings(session_token="spot-token", spot_read_fixture_db_path=fixture_db_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/spot", headers={"x-botik-session-token": "spot-token"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_mode"] == "fixture"
        assert payload["summary"]["account_type"] == "UNIFIED"
        assert payload["summary"]["holdings_count"] == 1
        assert payload["summary"]["open_orders_count"] == 1
        assert payload["summary"]["recent_fills_count"] == 1
        assert payload["summary"]["pending_intents_count"] == 1
        assert payload["balances"][0]["asset"] == "USDT"
        assert payload["holdings"][0]["symbol"] == "BTCUSDT"
        assert payload["active_orders"][0]["status"] == "New"
        assert payload["recent_fills"][0]["exec_id"] == "exec-1"
