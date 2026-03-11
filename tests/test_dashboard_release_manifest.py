from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import format_dashboard_release_panel, load_dashboard_release_manifest


def test_dashboard_release_manifest_file_exists_in_project_root() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "dashboard_release_manifest.yaml"
    assert manifest_path.exists() is True


def test_load_dashboard_release_manifest_reads_component_versions(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dashboard_release_manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "product: botik_dashboard",
                "components:",
                "  workspace_pack: 0.9.1",
                "  spot_runtime: 2.1.0",
                "  futures_training_engine: 1.4.0",
                "  telegram_bot_module: 1.7.0",
                "  db_schema: 3.2.1",
                "  active_spot_model: spot-x",
                "  active_futures_model: fut-y",
                "release:",
                "  active_config_profile: profile-live.yaml",
            ]
        ),
        encoding="utf-8",
    )
    data = load_dashboard_release_manifest(manifest_path)
    assert data["manifest_status"] == "loaded"
    assert data["workspace_pack_version"] == "0.9.1"
    assert data["spot_runtime_version"] == "2.1.0"
    assert data["futures_training_engine_version"] == "1.4.0"
    assert data["telegram_bot_module_version"] == "1.7.0"
    assert data["db_schema_version"] == "3.2.1"
    assert data["active_spot_model_version"] == "spot-x"
    assert data["active_futures_model_version"] == "fut-y"
    assert data["active_config_profile"] == "profile-live.yaml"


def test_load_dashboard_release_manifest_safe_fallbacks_when_missing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dashboard_release_manifest.yaml"
    manifest_path.write_text("manifest_version: 1\nproduct: botik_dashboard\n", encoding="utf-8")
    data = load_dashboard_release_manifest(manifest_path)
    assert data["manifest_status"] == "loaded"
    assert data["workspace_pack_version"] == "unknown"
    assert data["spot_runtime_version"] == "unknown"
    assert data["active_config_profile"] == "unknown"


def test_load_dashboard_release_manifest_returns_missing_status_when_file_absent(tmp_path: Path) -> None:
    data = load_dashboard_release_manifest(tmp_path / "absent_dashboard_release_manifest.yaml")
    assert data["manifest_status"] == "missing"
    assert data["workspace_pack_version"] == "unknown"
    assert data["active_config_profile"] == "unknown"


def test_format_dashboard_release_panel_contains_required_lines() -> None:
    panel = format_dashboard_release_panel(
        {
            "manifest_status": "loaded",
            "loaded_at": "2026-03-11 20:00:00",
            "shell_version": "0.0.2",
            "shell_build_sha": "abc1234",
            "workspace_pack_version": "0.0.2",
            "spot_runtime_version": "1.0.0",
            "futures_training_engine_version": "0.1.0",
            "telegram_bot_module_version": "1.0.0",
            "active_spot_model_version": "spot-model-a",
            "active_futures_model_version": "fut-model-b",
            "db_schema_version": "1.0.0",
            "active_config_profile": "config.yaml",
        }
    )
    assert "Dashboard Shell Version: 0.0.2" in panel
    assert "Shell Build SHA: abc1234" in panel
    assert "Workspace Pack Version: 0.0.2" in panel
    assert "Active Config Profile: config.yaml" in panel
