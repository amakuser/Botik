import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.runtime.data_integrity_worker import validate_data_integrity


def test_validate_data_integrity_accepts_consistent_backfill_db(tmp_path):
    db_path = tmp_path / "data_backfill.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE symbol_registry (
                symbol TEXT NOT NULL,
                category TEXT NOT NULL,
                interval TEXT NOT NULL,
                candle_count INTEGER NOT NULL,
                last_candle_ms INTEGER,
                last_backfill_at TEXT,
                ws_active INTEGER NOT NULL DEFAULT 0,
                data_status TEXT NOT NULL DEFAULT 'ready',
                added_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (symbol, category, interval)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                category TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                turnover REAL,
                created_at_utc TEXT NOT NULL,
                UNIQUE(symbol, category, interval, open_time_ms)
            )
            """
        )
        candles = [
            ("BTCUSDT", "spot", "1", 1_710_000_000_000),
            ("BTCUSDT", "spot", "1", 1_710_000_060_000),
            ("BTCUSDT", "spot", "1", 1_710_000_120_000),
        ]
        for symbol, category, interval, open_time_ms in candles:
            connection.execute(
                """
                INSERT INTO price_history (
                    symbol, category, interval, open_time_ms, open, high, low, close, volume, turnover, created_at_utc
                ) VALUES (?, ?, ?, ?, 1, 1, 1, 1, 1, 1, '2026-04-11T10:00:00Z')
                """,
                (symbol, category, interval, open_time_ms),
            )
        connection.execute(
            """
            INSERT INTO symbol_registry (
                symbol, category, interval, candle_count, last_candle_ms, last_backfill_at, ws_active, data_status, added_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, '2026-04-11T10:00:00Z', 0, 'ready', '2026-04-11T10:00:00Z', '2026-04-11T10:00:00Z')
            """,
            ("BTCUSDT", "spot", "1", len(candles), candles[-1][3]),
        )
        connection.commit()

    summary = validate_data_integrity(db_path, symbol="BTCUSDT", category="spot", interval="1")
    assert summary["history_count"] == 3
    assert summary["registry_count"] == 3
    assert summary["duplicate_count"] == 0
