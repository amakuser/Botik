import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.telegram_ops.legacy_adapter import LegacyTelegramOpsAdapter
from botik_app_service.telegram_ops.service import TelegramOpsService


def _write_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "snapshot": {
                    "generated_at": "2026-04-11T12:00:00Z",
                    "source_mode": "fixture",
                    "summary": {
                        "bot_profile": "ops",
                        "token_profile_name": "TELEGRAM_BOT_TOKEN",
                        "token_configured": True,
                        "internal_bot_disabled": False,
                        "connectivity_state": "unknown",
                        "connectivity_detail": "Use connectivity check to verify Telegram Bot API reachability.",
                        "allowed_chat_count": 2,
                        "allowed_chats_masked": ["12***34", "56***78"],
                        "commands_count": 2,
                        "alerts_count": 1,
                        "errors_count": 1,
                        "last_successful_send": "fixture alert delivered",
                        "last_error": "fixture warning observed",
                        "startup_status": "configured",
                    },
                    "recent_commands": [
                        {
                            "ts": "2026-04-11T11:58:00Z",
                            "command": "/status",
                            "source": "telegram_bot",
                            "status": "ok",
                            "chat_id_masked": "12***34",
                            "username": "fixture_user",
                            "args": "",
                        }
                    ],
                    "recent_alerts": [
                        {
                            "ts": "2026-04-11T11:59:00Z",
                            "alert_type": "delivery",
                            "message": "fixture alert delivered",
                            "delivered": True,
                            "source": "telegram",
                            "status": "ok",
                        }
                    ],
                    "recent_errors": [
                        {
                            "ts": "2026-04-11T11:57:00Z",
                            "error": "fixture warning observed",
                            "source": "telegram",
                            "status": "warning",
                        }
                    ],
                    "truncated": {
                        "recent_commands": False,
                        "recent_alerts": False,
                        "recent_errors": False,
                    },
                },
                "connectivity_check_result": {
                    "checked_at": "2026-04-11T12:00:10Z",
                    "source_mode": "fixture",
                    "state": "healthy",
                    "detail": "fixture connectivity check passed",
                    "bot_username": "botik_fixture_bot",
                    "latency_ms": 42.0,
                    "error": None,
                },
            }
        ),
        encoding="utf-8",
    )


def _create_telegram_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE telegram_commands (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id TEXT,
              username TEXT,
              command TEXT,
              args TEXT,
              response_status TEXT,
              created_at_utc TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE telegram_alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              alert_type TEXT,
              message TEXT,
              delivered INTEGER,
              created_at_utc TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE app_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT,
              level TEXT,
              message TEXT,
              extra_json TEXT,
              created_at_utc TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO telegram_commands (chat_id, username, command, args, response_status, created_at_utc)
            VALUES ('12345678', 'fixture_user', '/status', '', 'ok', '2026-04-11T11:58:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO telegram_alerts (alert_type, message, delivered, created_at_utc)
            VALUES ('delivery', 'fixture alert delivered', 1, '2026-04-11T11:59:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO app_logs (channel, level, message, extra_json, created_at_utc)
            VALUES ('telegram', 'WARNING', 'fixture warning observed', '{"source":"telegram_bot"}', '2026-04-11T11:57:00Z')
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_telegram_ops_service_returns_fixture_backed_snapshot_and_check(tmp_path):
    fixture_path = tmp_path / "telegram.fixture.json"
    _write_fixture(fixture_path)

    service = TelegramOpsService(repo_root=REPO_ROOT, fixture_path=fixture_path)
    snapshot = service.snapshot()
    check = service.run_connectivity_check()

    assert snapshot.source_mode == "fixture"
    assert snapshot.summary.allowed_chat_count == 2
    assert snapshot.recent_commands[0].command == "/status"
    assert snapshot.recent_alerts[0].message == "fixture alert delivered"
    assert snapshot.recent_errors[0].error == "fixture warning observed"
    assert check.state == "healthy"
    assert check.bot_username == "botik_fixture_bot"


def test_legacy_telegram_adapter_reads_recent_rows_without_network(tmp_path, monkeypatch):
    fixture_db = tmp_path / "telegram.fixture.sqlite3"
    _create_telegram_fixture_db(fixture_db)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.delenv("BOTIK_DISABLE_INTERNAL_TELEGRAM", raising=False)

    adapter = LegacyTelegramOpsAdapter(repo_root=REPO_ROOT)
    monkeypatch.setattr(adapter, "_resolve_db_path", lambda: fixture_db)
    monkeypatch.setattr(adapter, "_load_runtime_inputs", lambda: ({"telegram": {"profile": "ops"}}, os.environ.copy()))

    snapshot = adapter.read_snapshot()
    check = adapter.run_connectivity_check()

    assert snapshot.source_mode == "compatibility"
    assert snapshot.summary.commands_count == 1
    assert snapshot.summary.alerts_count == 1
    assert snapshot.summary.errors_count == 1
    assert snapshot.summary.connectivity_state == "missing_token"
    assert snapshot.recent_commands[0].chat_id_masked == "12***78"
    assert check.state == "missing_token"
