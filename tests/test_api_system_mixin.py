from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from pathlib import Path
from unittest.mock import patch

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.gui.api_db_mixin import DbMixin
from src.botik.gui.api_system_mixin import SystemMixin


class _StubSystemApi(DbMixin, SystemMixin):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._buf_lock = threading.Lock()
        self._log_buffer = deque(maxlen=50)

    def _add_buffer_log(self, ts: str, channel: str, message: str) -> None:
        with self._buf_lock:
            self._log_buffer.append({"ts": ts, "ch": channel, "msg": message})


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "system.db"
    db = Database(f"sqlite:///{db_path}")
    with db.connect() as conn:
        run_migrations(conn)
    return db_path


def _patch_db_path(db_path: Path):
    import src.botik.gui.api_system_mixin as m

    def _fake_load():
        return {}

    def _fake_resolve(_raw_cfg):
        return db_path

    return (
        patch.object(m, "_load_yaml", _fake_load),
        patch.object(m, "_resolve_db_path", _fake_resolve),
    )


def test_get_log_channels_keeps_spot_and_futures_separate(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
        ("spot", "INFO", "spot-only event", "2026-04-09 10:00:00"),
    )
    conn.execute(
        "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
        ("futures", "INFO", "futures-only event", "2026-04-09 10:01:00"),
    )
    conn.execute(
        "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
        ("telegram", "ERROR", "telegram failed", "2026-04-09 10:02:00"),
    )
    conn.commit()
    conn.close()

    api = _StubSystemApi(db_path)
    api._add_buffer_log("10:03:00", "sys", "dashboard started")

    p1, p2 = _patch_db_path(db_path)
    with p1, p2:
        payload = json.loads(api.get_log_channels(20))

    assert [row["message"] for row in payload["spot"]] == ["spot-only event"]
    assert [row["message"] for row in payload["futures"]] == ["futures-only event"]
    assert payload["telegram"][0]["message"] == "telegram failed"
    assert any(row["message"] == "dashboard started" for row in payload["sys"])
