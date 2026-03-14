from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import (
    build_dashboard_release_home_sections,
    format_dashboard_release_panel,
    load_dashboard_release_manifest,
)


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
    assert data["shell_name"] == "Dashboard Shell"
    assert data["shell_version_source"] == "VERSION"
    assert data["shell_build_source"] == "version.txt"


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


def test_build_dashboard_release_home_sections_formats_structured_lines() -> None:
    sections = build_dashboard_release_home_sections(
        {
            "manifest_status": "loaded",
            "loaded_at": "2026-03-14 20:00:00",
            "shell_name": "Dashboard Shell",
            "shell_version": "0.0.8",
            "shell_build_sha": "abc1234",
            "shell_version_source": "VERSION",
            "shell_build_source": "version.txt",
            "workspace_pack_version": "0.0.8",
            "spot_runtime_version": "1.0.0",
            "futures_training_engine_version": "0.1.1",
            "telegram_bot_module_version": "1.1.0",
            "db_schema_version": "1.0.0",
            "active_spot_model_version": "spot-model-a",
            "active_futures_model_version": "fut-model-b",
            "active_config_profile": "config.yaml",
            "release_source": "external_manifest",
            "workspace_manifest_status": "loaded",
            "active_models_manifest_status": "loaded",
            "manifest_path": "dashboard_release_manifest.yaml",
            "workspace_manifest_path": "dashboard_workspace_manifest.yaml",
            "active_models_manifest_path": "active_models.yaml",
            "workspace_order_line": "Dashboard Home / Spot Workspace / Futures Workspace",
        }
    )
    assert "release=loaded" in sections["status_line"]
    assert "Dashboard Shell 0.0.8" in sections["shell_line"]
    assert "workspace_pack=0.0.8" in sections["components_line"]
    assert "spot_model=spot-model-a" in sections["models_line"]
    assert "active_models=active_models.yaml" in sections["manifests_line"]
    assert "Futures Workspace" in sections["workspace_line"]


def test_format_dashboard_release_panel_contains_required_lines() -> None:
    panel = format_dashboard_release_panel(
        {
            "manifest_status": "loaded",
            "loaded_at": "2026-03-11 20:00:00",
            "shell_name": "Dashboard Shell",
            "shell_version": "0.0.2",
            "shell_build_sha": "abc1234",
            "shell_version_source": "VERSION",
            "shell_build_source": "version.txt",
            "workspace_pack_version": "0.0.2",
            "spot_runtime_version": "1.0.0",
            "futures_training_engine_version": "0.1.0",
            "telegram_bot_module_version": "1.0.0",
            "active_spot_model_version": "spot-model-a",
            "active_futures_model_version": "fut-model-b",
            "db_schema_version": "1.0.0",
            "active_config_profile": "config.yaml",
            "release_source": "external_manifest",
            "workspace_manifest_status": "loaded",
            "active_models_manifest_status": "loaded",
            "manifest_path": "dashboard_release_manifest.yaml",
            "workspace_manifest_path": "dashboard_workspace_manifest.yaml",
            "active_models_manifest_path": "active_models.yaml",
            "workspace_order_line": "Dashboard Home / Spot Workspace",
        }
    )
    assert "Release Manifest Status: loaded" in panel
    assert "Dashboard Shell 0.0.2 | build=abc1234" in panel
    assert "workspace_pack=0.0.2" in panel
    assert "spot_model=spot-model-a" in panel
    assert "release=dashboard_release_manifest.yaml" in panel
