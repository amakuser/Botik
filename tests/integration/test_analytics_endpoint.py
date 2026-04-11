import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def _create_analytics_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE futures_paper_trades (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                model_scope TEXT,
                net_pnl REAL,
                was_profitable INTEGER,
                opened_at_utc TEXT,
                closed_at_utc TEXT
            );
            CREATE TABLE outcomes (
                signal_id TEXT PRIMARY KEY,
                symbol TEXT,
                model_scope TEXT,
                net_pnl_quote REAL,
                was_profitable INTEGER,
                closed_at_utc TEXT
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO futures_paper_trades (
                symbol, model_scope, net_pnl, was_profitable, opened_at_utc, closed_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("BTCUSDT", "futures", 12.5, 1, "2026-04-08 09:00:00", "2026-04-08 10:00:00"),
                ("ETHUSDT", "futures", -3.0, 0, "2026-04-09 09:00:00", "2026-04-09 10:00:00"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO outcomes (
                signal_id, symbol, model_scope, net_pnl_quote, was_profitable, closed_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("sig-1", "SOLUSDT", "spot", 5.0, 1, "2026-04-10 11:00:00"),
                ("sig-2", "XRPUSDT", "spot", 1.5, 1, "2026-04-11 12:00:00"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_analytics_endpoint_returns_fixture_snapshot(tmp_path):
    fixture_db_path = tmp_path / "analytics.fixture.sqlite3"
    _create_analytics_fixture_db(fixture_db_path)

    settings = Settings(session_token="analytics-token", analytics_read_fixture_db_path=fixture_db_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/analytics", headers={"x-botik-session-token": "analytics-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_mode"] == "fixture"
    assert payload["summary"]["total_closed_trades"] == 4
    assert payload["summary"]["winning_trades"] == 3
    assert payload["summary"]["losing_trades"] == 1
    assert payload["summary"]["total_net_pnl"] == 16.0
    assert payload["summary"]["average_net_pnl"] == 4.0
    assert payload["equity_curve"][-1]["cumulative_pnl"] == 16.0
    assert payload["recent_closed_trades"][0]["symbol"] == "XRPUSDT"
