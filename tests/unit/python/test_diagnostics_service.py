import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.diagnostics_compat.service import DiagnosticsCompatibilityService
from botik_app_service.infra.config import Settings


class StubDiagnosticsAdapter:
    def __init__(self, paths: dict[str, Path]) -> None:
        self._paths = paths

    def resolve_legacy_paths(self) -> dict[str, Path]:
        return self._paths


def test_diagnostics_service_returns_bounded_snapshot(tmp_path: Path):
    artifacts_dir = tmp_path / "artifacts"
    runtime_control_dir = artifacts_dir / "state" / "runtime-control"
    training_control_dir = artifacts_dir / "state" / "training-control"
    runtime_control_dir.mkdir(parents=True)
    training_control_dir.mkdir(parents=True)

    config_yaml = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"
    legacy_log = tmp_path / "botik.log"
    runtime_fixture = tmp_path / "runtime-status.fixture.json"
    spot_fixture = tmp_path / "spot.fixture.sqlite3"
    futures_fixture = tmp_path / "futures.fixture.sqlite3"
    analytics_fixture = tmp_path / "analytics.fixture.sqlite3"
    models_fixture = tmp_path / "models.fixture.sqlite3"
    manifest_fixture = tmp_path / "active_models.fixture.yaml"
    telegram_fixture = tmp_path / "telegram.fixture.json"

    for path in (
        config_yaml,
        env_file,
        legacy_log,
        runtime_fixture,
        spot_fixture,
        futures_fixture,
        analytics_fixture,
        models_fixture,
        manifest_fixture,
        telegram_fixture,
    ):
        path.write_text("fixture\n", encoding="utf-8")

    adapter = StubDiagnosticsAdapter(
        {
            "config_yaml": config_yaml,
            "env_file": env_file,
            "legacy_db": tmp_path / "missing-legacy.sqlite3",
            "legacy_log": legacy_log,
            "active_models_manifest": tmp_path / "missing-active-models.yaml",
        }
    )
    settings = Settings(
        session_token="botik-dev-token",
        artifacts_dir=artifacts_dir,
        runtime_control_mode="fixture",
        runtime_status_fixture_path=runtime_fixture,
        spot_read_fixture_db_path=spot_fixture,
        futures_read_fixture_db_path=futures_fixture,
        analytics_read_fixture_db_path=analytics_fixture,
        models_read_fixture_db_path=models_fixture,
        models_read_manifest_path=manifest_fixture,
        telegram_ops_fixture_path=telegram_fixture,
    )

    snapshot = DiagnosticsCompatibilityService(
        repo_root=REPO_ROOT,
        settings=settings,
        adapter=adapter,
    ).snapshot()

    assert snapshot.source_mode == "resolved"
    assert snapshot.summary.routes_count == 10
    assert snapshot.summary.fixture_overrides_count == 7
    assert snapshot.summary.missing_paths_count == 1
    assert snapshot.summary.warnings_count == 2
    assert snapshot.config[2].value == "bot***ken"
    assert snapshot.paths[0].key == "repo_root"
    assert any(entry.key == "runtime_status_fixture" and entry.source == "fixture" for entry in snapshot.paths)
    assert "Legacy compatibility DB path is missing." in snapshot.warnings
    assert "Runtime control is currently configured in fixture mode." in snapshot.warnings
