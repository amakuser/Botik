from __future__ import annotations

from src.botik.gui.app import build_dashboard_settings_workspace_sections


REMOVED_FIELDS = {
    "target_profit",
    "safety_buffer",
    "stop_loss_pct",
    "take_profit_pct",
    "hold_timeout_sec",
    "min_active_position_usdt",
    "symbols",
    "strategy.runtime_strategy",
    "bybit.market_category",
}


def test_build_dashboard_settings_workspace_sections_formats_technical_diagnostics() -> None:
    sections = build_dashboard_settings_workspace_sections(
        launcher_mode="packaged",
        packaged_executable=r"C:\\Botik\\botik.exe",
        python_path=r"C:\\Python\\python.exe",
        config_path=r"C:\\Botik\\config.live.yaml",
        raw_cfg={
            "execution": {"mode": "live"},
            "start_paused": False,
            "bybit": {
                "host": "api.bybit.com",
                "ws_public_host": "stream.bybit.com",
            },
            "strategy": {
                "take_profit_pct": 0.01,
                "stop_loss_pct": 0.005,
            },
        },
        env_data={
            "TELEGRAM_BOT_TOKEN": "secret",
            "BYBIT_API_KEY": "key",
            "BYBIT_API_SECRET_KEY": "secret-key",
            "BYBIT_RSA_PRIVATE_KEY_PATH": "keys/bybit.pem",
        },
        release_manifest={
            "shell_version": "0.0.14",
            "shell_build_sha": "abc1234",
            "active_config_profile": "config.live.yaml",
        },
    )

    assert "launcher=packaged" in sections["diagnostics_line"]
    assert "runtime=botik.exe" in sections["diagnostics_line"]
    assert "config=config.live.yaml" in sections["diagnostics_line"]
    assert "shell=0.0.14" in sections["diagnostics_line"]
    assert "execution.mode=live" in sections["profile_line"]
    assert "start_paused=no" in sections["profile_line"]
    assert "bybit.host=api.bybit.com" in sections["profile_line"]
    assert "workspace_manifest=dashboard_workspace_manifest.yaml" in sections["paths_line"]
    assert "telegram_token=configured" in sections["secrets_line"]
    assert "bybit_api_key=configured" in sections["secrets_line"]
    assert sections["editable_fields"] == [
        "execution.mode",
        "start_paused",
        "bybit.host",
        "ws_public_host",
    ]
    assert REMOVED_FIELDS.isdisjoint(set(sections["editable_fields"]))
    assert "Instrument policy and trading knobs live" in sections["notice_line"]



def test_build_dashboard_settings_workspace_sections_safe_fallbacks() -> None:
    sections = build_dashboard_settings_workspace_sections(
        launcher_mode="source",
        packaged_executable="",
        python_path=r"C:\\Python\\python.exe",
        config_path="",
        raw_cfg={},
        env_data={},
        release_manifest={},
    )

    assert "launcher=source" in sections["diagnostics_line"]
    assert "runtime=python.exe" in sections["diagnostics_line"]
    assert "config=config.yaml" in sections["diagnostics_line"]
    assert "execution.mode=paper" in sections["profile_line"]
    assert "start_paused=yes" in sections["profile_line"]
    assert "bybit.host=unknown" in sections["profile_line"]
    assert "telegram_token=missing" in sections["secrets_line"]
    assert "active_models=active_models.yaml" in sections["paths_line"]
