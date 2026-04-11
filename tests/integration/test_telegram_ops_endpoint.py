import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


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


def test_telegram_endpoint_returns_fixture_snapshot_and_check(tmp_path):
    fixture_path = tmp_path / "telegram.fixture.json"
    _write_fixture(fixture_path)

    settings = Settings(session_token="telegram-token", telegram_ops_fixture_path=fixture_path)
    app = create_app(settings)
    with TestClient(app) as client:
        snapshot_response = client.get("/telegram", headers={"x-botik-session-token": "telegram-token"})
        check_response = client.post("/telegram/connectivity-check", headers={"x-botik-session-token": "telegram-token"})

        assert snapshot_response.status_code == 200
        snapshot = snapshot_response.json()
        assert snapshot["source_mode"] == "fixture"
        assert snapshot["summary"]["allowed_chat_count"] == 2
        assert snapshot["summary"]["commands_count"] == 2
        assert snapshot["recent_commands"][0]["command"] == "/status"

        assert check_response.status_code == 200
        check_payload = check_response.json()
        assert check_payload["state"] == "healthy"
        assert check_payload["bot_username"] == "botik_fixture_bot"
