import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.analytics_read.service import AnalyticsReadService


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
                ("BTCUSDT", "futures", 2.0, 1, "2026-04-08 09:00:00", "2026-04-08 10:00:00"),
                ("ETHUSDT", "futures", -1.0, 0, "2026-04-09 09:00:00", "2026-04-09 10:00:00"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO outcomes (
                signal_id, symbol, model_scope, net_pnl_quote, was_profitable, closed_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("sig-1", "SOLUSDT", "spot", 3.5, 1, "2026-04-10 11:00:00"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_analytics_service_returns_fixture_snapshot(tmp_path):
    fixture_db_path = tmp_path / "analytics.fixture.sqlite3"
    _create_analytics_fixture_db(fixture_db_path)

    service = AnalyticsReadService(repo_root=REPO_ROOT, fixture_db_path=fixture_db_path)
    snapshot = service.snapshot()

    assert snapshot.source_mode == "fixture"
    assert snapshot.summary.total_closed_trades == 3
    assert snapshot.summary.winning_trades == 2
    assert snapshot.summary.losing_trades == 1
    assert snapshot.summary.total_net_pnl == 4.5
    assert snapshot.summary.average_net_pnl == 1.5
    assert snapshot.equity_curve[-1].cumulative_pnl == 4.5
    assert snapshot.recent_closed_trades[0].symbol == "SOLUSDT"
