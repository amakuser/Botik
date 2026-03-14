from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import (
    BotikGui,
    format_dashboard_release_panel,
    load_active_models_pointer,
    load_dashboard_release_manifest,
    load_dashboard_workspace_manifest,
    load_futures_training_workspace_read_model,
    resolve_dashboard_workspace_tabs,
)


def test_workspace_manifest_file_exists_in_project_root() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "dashboard_workspace_manifest.yaml"
    assert manifest_path.exists() is True


def test_active_models_manifest_file_exists_in_project_root() -> None:
    manifest_path = Path(__file__).resolve().parent.parent / "active_models.yaml"
    assert manifest_path.exists() is True


def test_load_dashboard_workspace_manifest_reads_order_and_visibility(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dashboard_workspace_manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "workspaces:",
                "  - key: logs",
                "    label: Logs First",
                "    enabled: true",
                "    visible: true",
                "    order: 1",
                "  - key: home",
                "    label: Dashboard Home",
                "    enabled: true",
                "    visible: true",
                "    order: 2",
                "  - key: telegram",
                "    label: Telegram Hidden",
                "    enabled: true",
                "    visible: false",
                "    order: 3",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_dashboard_workspace_manifest(manifest_path)
    assert loaded["manifest_status"] == "loaded"
    tabs = resolve_dashboard_workspace_tabs(loaded)
    assert tabs[0] == ("logs", "Logs First")
    assert ("telegram", "Telegram Hidden") not in tabs
    assert any(key == "home" for key, _ in tabs)


def test_resolve_dashboard_workspace_tabs_normalizes_legacy_keys_and_labels() -> None:
    tabs = resolve_dashboard_workspace_tabs(
        {
            "workspaces": [
                {"key": "futures_training", "label": "Futures Training Workspace", "enabled": True, "visible": True, "order": 2},
                {"key": "models", "label": "Models", "enabled": True, "visible": True, "order": 3},
            ]
        }
    )
    assert tabs == [
        ("home", "Dashboard Home"),
        ("futures", "Futures Workspace"),
        ("model_registry", "Model Registry Workspace"),
    ]


def test_load_dashboard_workspace_manifest_safe_fallbacks(tmp_path: Path) -> None:
    missing = load_dashboard_workspace_manifest(tmp_path / "absent_workspace_manifest.yaml")
    assert missing["manifest_status"] == "defaulted"
    missing_tabs = resolve_dashboard_workspace_tabs(missing)
    assert missing_tabs[0][0] == "home"

    malformed_path = tmp_path / "broken_workspace_manifest.yaml"
    malformed_path.write_text("workspaces: [", encoding="utf-8")
    malformed = load_dashboard_workspace_manifest(malformed_path)
    assert malformed["manifest_status"] == "failed"
    malformed_tabs = resolve_dashboard_workspace_tabs(malformed)
    assert malformed_tabs[0][0] == "home"


def test_load_active_models_pointer_reads_values(tmp_path: Path) -> None:
    pointer = tmp_path / "active_models.yaml"
    pointer.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "active_spot_model: spot-v3",
                "active_futures_model: fut-v9",
                "spot_checkpoint_path: data/models/spot-v3.pkl",
                "futures_checkpoint_path: data/models/fut-v9.pkl",
            ]
        ),
        encoding="utf-8",
    )
    data = load_active_models_pointer(pointer)
    assert data["manifest_status"] == "loaded"
    assert data["active_spot_model"] == "spot-v3"
    assert data["active_futures_model"] == "fut-v9"


def test_load_active_models_pointer_safe_fallbacks(tmp_path: Path) -> None:
    missing = load_active_models_pointer(tmp_path / "absent_active_models.yaml")
    assert missing["manifest_status"] == "missing"
    assert missing["active_spot_model"] == "unknown"

    malformed_path = tmp_path / "broken_active_models.yaml"
    malformed_path.write_text("active_spot_model: [", encoding="utf-8")
    malformed = load_active_models_pointer(malformed_path)
    assert malformed["manifest_status"] == "failed"
    assert malformed["active_spot_model"] == "unknown"


def test_release_manifest_overrides_active_models_from_external_pointer(tmp_path: Path) -> None:
    release_path = tmp_path / "dashboard_release_manifest.yaml"
    release_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "product: botik_dashboard",
                "components:",
                "  workspace_pack: 0.0.9",
                "  active_spot_model: unknown",
                "  active_futures_model: unknown",
                "release:",
                "  active_config_profile: profile-live.yaml",
            ]
        ),
        encoding="utf-8",
    )
    pointer_path = tmp_path / "active_models.yaml"
    pointer_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "active_spot_model: spot-model-external",
                "active_futures_model: futures-model-external",
            ]
        ),
        encoding="utf-8",
    )
    workspace_path = tmp_path / "dashboard_workspace_manifest.yaml"
    workspace_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "workspaces:",
                "  - key: home",
                "    label: Dashboard Home",
                "    enabled: true",
                "    visible: true",
                "    order: 1",
            ]
        ),
        encoding="utf-8",
    )
    data = load_dashboard_release_manifest(
        release_path,
        workspace_manifest_path=workspace_path,
        active_models_path=pointer_path,
    )
    assert data["manifest_status"] == "loaded"
    assert data["active_models_manifest_status"] == "loaded"
    assert data["workspace_manifest_status"] == "loaded"
    assert data["active_spot_model_version"] == "spot-model-external"
    assert data["active_futures_model_version"] == "futures-model-external"
    panel = format_dashboard_release_panel(data)
    assert "workspace_manifest=loaded" in panel
    assert "active_models_manifest=loaded" in panel
    assert "spot-model-external" in panel


def test_apply_workspace_manifest_to_notebook_uses_external_order_visibility() -> None:
    class _NotebookStub:
        def __init__(self) -> None:
            self._tabs = ["old-1", "old-2"]
            self.added: list[tuple[object, str]] = []
            self.forgotten: list[str] = []

        def tabs(self) -> list[str]:
            return list(self._tabs)

        def forget(self, tab_id: str) -> None:
            self.forgotten.append(tab_id)
            if tab_id in self._tabs:
                self._tabs.remove(tab_id)

        def add(self, frame: object, *, text: str) -> None:
            self.added.append((frame, text))
            self._tabs.append(f"new-{len(self.added)}")

    gui = BotikGui.__new__(BotikGui)
    gui.notebook = _NotebookStub()
    gui.home_tab = object()
    gui.control_tab = object()
    gui.futures_tab = object()
    gui.model_registry_tab = object()
    gui.telegram_tab = object()
    gui.logs_tab = object()
    gui.statistics_tab = object()
    gui.settings_tab = object()

    manifest_data = {
        "workspaces": [
            {"key": "logs", "label": "Logs First", "enabled": True, "visible": True, "order": 1},
            {"key": "home", "label": "Dashboard Home", "enabled": True, "visible": True, "order": 2},
            {"key": "telegram", "label": "Telegram Hidden", "enabled": True, "visible": False, "order": 3},
            {"key": "spot", "label": "Spot Workspace", "enabled": True, "visible": True, "order": 4},
        ]
    }

    gui._apply_workspace_manifest_to_notebook(manifest_data)
    labels = [label for _, label in gui.notebook.added]
    assert gui.notebook.forgotten == ["old-1", "old-2"]
    assert labels == ["Logs First", "Dashboard Home", "Spot Workspace"]


def test_external_active_models_pointer_wires_into_futures_training_read_model(tmp_path: Path) -> None:
    release_path = tmp_path / "dashboard_release_manifest.yaml"
    release_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "product: botik_dashboard",
                "components:",
                "  futures_training_engine: 0.1.1",
                "  active_futures_model: unknown",
                "release:",
                "  active_config_profile: config.yaml",
            ]
        ),
        encoding="utf-8",
    )
    pointer_path = tmp_path / "active_models.yaml"
    pointer_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "active_spot_model: spot-42",
                "active_futures_model: fut-77",
            ]
        ),
        encoding="utf-8",
    )
    workspace_path = tmp_path / "dashboard_workspace_manifest.yaml"
    workspace_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "workspaces:",
                "  - key: home",
                "    label: Dashboard Home",
                "    enabled: true",
                "    visible: true",
                "    order: 1",
            ]
        ),
        encoding="utf-8",
    )
    release_data = load_dashboard_release_manifest(
        release_path,
        workspace_manifest_path=workspace_path,
        active_models_path=pointer_path,
    )
    read_model = load_futures_training_workspace_read_model(
        db_path=tmp_path / "absent.db",
        release_manifest=release_data,
    )
    assert release_data["active_futures_model_version"] == "fut-77"
    assert read_model["active_futures_model_version"] == "fut-77"
