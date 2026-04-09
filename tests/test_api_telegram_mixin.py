from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.gui.api_db_mixin import DbMixin
from src.botik.gui.api_telegram_mixin import TelegramMixin


class _AliveThread:
    def is_alive(self) -> bool:
        return True


class _StubTelegramApi(DbMixin, TelegramMixin):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._app_version = "v-test"
        self._buf_lock = threading.Lock()
        self._log_buffer = []
        self._init_telegram()
        self._telegram_thread = _AliveThread()

    def _start_telegram_control_if_configured(self) -> None:
        return

    def _add_log(self, msg: str, channel: str = "sys") -> None:
        return

    def _running_modes(self) -> list[str]:
        return []

    def _trading_state(self) -> str:
        return "stopped"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "telegram.db"
    db = Database(f"sqlite:///{db_path}")
    with db.connect() as conn:
        run_migrations(conn)
    return db_path


def _patch_telegram_env(db_path: Path):
    import src.botik.gui.api_telegram_mixin as m

    def _fake_load():
        return {}

    def _fake_resolve(_raw_cfg):
        return db_path

    def _fake_env():
        return {
            "TELEGRAM_BOT_TOKEN": "configured-token",
            "TELEGRAM_CHAT_ID": "12345,67890",
        }

    return (
        patch.object(m, "_load_yaml", _fake_load),
        patch.object(m, "_resolve_db_path", _fake_resolve),
        patch.object(m, "_read_env_map", _fake_env),
    )


def test_get_telegram_workspace_returns_health_and_recent_activity(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO telegram_commands (chat_id, username, command, args, response_status, created_at_utc) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("12345", "farik", "/status", "", "ok", "2026-04-09 11:00:00"),
    )
    conn.execute(
        "INSERT INTO telegram_alerts (alert_type, message, delivered, created_at_utc) VALUES (?, ?, ?, ?)",
        ("startup", "telegram control bot started", 1, "2026-04-09 11:00:01"),
    )
    conn.execute(
        "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
        ("telegram", "ERROR", "telegram handshake failed once", "2026-04-09 11:00:02"),
    )
    conn.commit()
    conn.close()

    api = _StubTelegramApi(db_path)

    p1, p2, p3 = _patch_telegram_env(db_path)
    with p1, p2, p3:
        with patch.object(
            api,
            "_sync_telegram_health",
            return_value={
                "handshake": "ok",
                "ping_ms": 18.2,
                "bot_username": "botik_ops_bot",
                "checked_at_utc": "2026-04-09 11:00:05",
                "error": None,
            },
        ):
            payload = json.loads(api.get_telegram_workspace(10, True))

    assert payload["state"] == "running"
    assert payload["allowed_chats_count"] == 2
    assert payload["bot_username"] == "botik_ops_bot"
    assert payload["ping_ms"] == 18.2
    assert payload["recent_commands"][0]["command"] == "/status"
    assert payload["recent_alerts"][0]["alert_type"] == "startup"
    assert "handshake failed" in payload["recent_errors"][0]["message"]


def test_record_telegram_command_persists_to_db(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    api = _StubTelegramApi(db_path)

    p1, p2, p3 = _patch_telegram_env(db_path)
    with p1, p2, p3:
        api._record_telegram_command(
            command="/balance",
            source="telegram_gui",
            status="received",
            chat_id="12345",
            username="farik",
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT chat_id, username, command, response_status FROM telegram_commands ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row == ("12345", "farik", "/balance", "received")
