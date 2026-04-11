import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.diagnostics_compat.service import DiagnosticsCompatibilityService
from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


class StubDiagnosticsAdapter:
    def __init__(self, paths: dict[str, Path]) -> None:
        self._paths = paths

    def resolve_legacy_paths(self) -> dict[str, Path]:
        return self._paths


def test_diagnostics_endpoint_returns_bounded_snapshot(tmp_path: Path):
    artifacts_dir = tmp_path / "artifacts"
    runtime_control_dir = artifacts_dir / "state" / "runtime-control"
    training_control_dir = artifacts_dir / "state" / "training-control"
    runtime_control_dir.mkdir(parents=True)
    training_control_dir.mkdir(parents=True)

    config_yaml = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"
    legacy_log = tmp_path / "botik.log"
    models_manifest = tmp_path / "active_models.fixture.yaml"
    runtime_fixture = tmp_path / "runtime-status.fixture.json"
    spot_fixture = tmp_path / "spot.fixture.sqlite3"
    futures_fixture = tmp_path / "futures.fixture.sqlite3"
    analytics_fixture = tmp_path / "analytics.fixture.sqlite3"
    models_fixture = tmp_path / "models.fixture.sqlite3"
    telegram_fixture = tmp_path / "telegram.fixture.json"

    for path in (
        config_yaml,
        env_file,
        legacy_log,
        models_manifest,
        runtime_fixture,
        spot_fixture,
        futures_fixture,
        analytics_fixture,
        models_fixture,
        telegram_fixture,
    ):
        path.write_text("fixture\n", encoding="utf-8")

    settings = Settings(
        session_token="diagnostics-token",
        artifacts_dir=artifacts_dir,
        runtime_control_mode="fixture",
        runtime_status_fixture_path=runtime_fixture,
        spot_read_fixture_db_path=spot_fixture,
        futures_read_fixture_db_path=futures_fixture,
        analytics_read_fixture_db_path=analytics_fixture,
        models_read_fixture_db_path=models_fixture,
        models_read_manifest_path=models_manifest,
        telegram_ops_fixture_path=telegram_fixture,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        app.state.diagnostics_service = DiagnosticsCompatibilityService(
            repo_root=REPO_ROOT,
            settings=settings,
            adapter=StubDiagnosticsAdapter(
                {
                    "config_yaml": config_yaml,
                    "env_file": env_file,
                    "legacy_db": tmp_path / "missing-legacy.sqlite3",
                    "legacy_log": legacy_log,
                    "active_models_manifest": models_manifest,
                }
            ),
        )

        response = client.get("/diagnostics", headers={"x-botik-session-token": "diagnostics-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_mode"] == "resolved"
    assert payload["summary"]["routes_count"] == 10
    assert payload["summary"]["fixture_overrides_count"] == 7
    assert payload["summary"]["runtime_control_mode"] == "fixture"
    assert payload["config"][2]["masked"] is True
    assert any(entry["key"] == "runtime_status_fixture" and entry["source"] == "fixture" for entry in payload["paths"])
    assert "Runtime control is currently configured in fixture mode." in payload["warnings"]
