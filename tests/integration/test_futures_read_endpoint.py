import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app
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


def test_futures_endpoint_returns_fixture_snapshot(tmp_path):
    fixture_db_path = tmp_path / "futures.fixture.sqlite3"
    _create_futures_fixture_db(fixture_db_path)

    settings = Settings(session_token="futures-token", futures_read_fixture_db_path=fixture_db_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/futures", headers={"x-botik-session-token": "futures-token"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_mode"] == "fixture"
        assert payload["summary"]["account_type"] == "UNIFIED"
        assert payload["summary"]["positions_count"] == 1
        assert payload["summary"]["protected_positions_count"] == 1
        assert payload["summary"]["open_orders_count"] == 1
        assert payload["summary"]["recent_fills_count"] == 1
        assert payload["positions"][0]["symbol"] == "ETHUSDT"
        assert payload["active_orders"][0]["status"] == "New"
        assert payload["recent_fills"][0]["exec_id"] == "fut-exec-1"
