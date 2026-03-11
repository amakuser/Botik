from __future__ import annotations

from src.botik.gui.app import load_telegram_workspace_read_model


def test_telegram_workspace_read_model_collects_operational_status_and_actions() -> None:
    model = load_telegram_workspace_read_model(
        raw_cfg={
            "telegram": {
                "profile": "ops-primary",
                "token_env": "TG_BOT_TOKEN",
                "chat_id_env": "TG_ALLOWED_CHATS",
            }
        },
        env_data={
            "TG_BOT_TOKEN": "secret-token-value",
            "TG_ALLOWED_CHATS": "123456789, 987654321",
        },
        release_manifest={"telegram_bot_module_version": "1.1.0"},
        thread_running=True,
        missing_token_reported=False,
        runtime_capabilities={"reconciliation": "supported", "protection": "supported"},
        recent_commands=[
            {"ts": "2026-03-11 20:00:00", "command": "/status", "source": "telegram_bot", "status": "ok"},
        ],
        recent_alerts=[
            {"ts": "2026-03-11 20:00:02", "message": "status response sent", "source": "telegram_bot", "status": "ok"},
        ],
        recent_errors=[],
    )

    assert model["telegram_enabled"] == "yes"
    assert model["bot_connected"] == "connected"
    assert model["bot_profile"] == "ops-primary"
    assert model["token_profile_name"] == "TG_BOT_TOKEN"
    assert model["token_configured"] == "yes"
    assert int(model["allowed_chat_count"]) == 2
    assert model["module_version"] == "1.1.0"
    assert model["recent_commands_rows"][0][2] == "/status"
    assert model["recent_alerts_rows"][0][2] == "status response sent"
    assert "/status" in list(model["available_commands"])
    assert "/starttrading" in list(model["available_commands"])
    assert "/spot_status" not in list(model["available_commands"])
    actions = [str(x).lower() for x in list(model.get("actions") or [])]
    assert "test send" in actions
    assert "reload telegram status" in actions
    assert all("start futures trading" not in action for action in actions)


def test_telegram_workspace_read_model_safe_fallback_when_not_configured() -> None:
    model = load_telegram_workspace_read_model(
        raw_cfg={},
        env_data={},
        release_manifest={},
        thread_running=False,
        missing_token_reported=True,
        runtime_capabilities={"reconciliation": "unsupported", "protection": "unsupported"},
    )

    assert model["telegram_enabled"] == "no"
    assert model["token_configured"] == "no"
    assert model["bot_connected"] == "disabled"
    assert int(model["allowed_chat_count"]) == 0
    assert model["allowed_chats_masked"] == "not configured"
    assert model["module_version"] == "unknown"
    assert model["last_error"] == "configuration_missing_token"
    assert "not configured" in str(model["access_line"])
    assert "reconciliation=unsupported" in str(model["capability_line"])


def test_telegram_workspace_read_model_uses_log_fallback_for_errors() -> None:
    model = load_telegram_workspace_read_model(
        raw_cfg={},
        env_data={"TELEGRAM_BOT_TOKEN": "configured"},
        release_manifest={},
        thread_running=False,
        recent_commands=[],
        recent_alerts=[],
        recent_errors=[],
        log_lines=[
            "[telegram-dashboard] control bot started",
            "[telegram-dashboard] ERROR failed to connect",
        ],
    )
    assert int(model["recent_errors_count"]) >= 1
    assert "failed to connect" in str(model["recent_errors_rows"][0][2]).lower()


def test_telegram_workspace_read_model_does_not_expose_spot_or_training_fields() -> None:
    model = load_telegram_workspace_read_model(raw_cfg={}, env_data={}, release_manifest={})
    assert "holdings_count" not in model
    assert "spot_workspace_holdings_rows" not in model
    assert "training_runtime_status" not in model
    assert "futures_training_checkpoints_rows" not in model
