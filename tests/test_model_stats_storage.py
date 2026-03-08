from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, insert_model_stats


def test_insert_model_stats_row(tmp_path: Path) -> None:
    db_path = tmp_path / "botik.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)
        insert_model_stats(
            conn,
            model_id="model-1",
            ts_ms=1_700_000_000_000,
            net_edge_mean=4.25,
            win_rate=0.55,
            fill_rate=0.72,
        )
        row = conn.execute(
            """
            SELECT model_id, ts_ms, net_edge_mean, win_rate, fill_rate
            FROM model_stats
            ORDER BY ts_ms DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "model-1"
        assert int(row[1]) == 1_700_000_000_000
        assert float(row[2]) == 4.25
        assert float(row[3]) == 0.55
        assert float(row[4]) == 0.72
    finally:
        conn.close()
