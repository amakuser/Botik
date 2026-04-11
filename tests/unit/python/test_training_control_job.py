import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.jobs import JobDetails, JobState, StartJobRequest
from botik_app_service.jobs.training_control_job import _build_launch_spec, create_training_control_job_definition


def _job_details(job_id: str = "training-job-1") -> JobDetails:
    return JobDetails(
        job_id=job_id,
        job_type="training_control",
        state=JobState.QUEUED,
        progress=0.0,
        started_at=None,
        updated_at=datetime.now(timezone.utc),
        exit_code=None,
        last_error=None,
        log_stream_id="log-stream-1",
    )


def test_training_control_launch_spec_uses_fixture_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_db_path = tmp_path / "models.fixture.sqlite3"
    manifest_path = tmp_path / "active_models.fixture.yaml"
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    request = StartJobRequest.model_validate(
        {
            "job_type": "training_control",
            "payload": {
                "scope": "futures",
                "interval": "1m",
            },
        }
    )

    spec = _build_launch_spec(
        request,
        _job_details(),
        fixture_db_path=fixture_db_path,
        manifest_path=manifest_path,
        configured_mode="fixture",
    )

    assert "botik_app_service.runtime.training_control_worker" in spec.command
    assert "--mode" in spec.command
    assert spec.command[spec.command.index("--mode") + 1] == "fixture"
    assert "--fixture-db-path" in spec.command
    assert spec.command[spec.command.index("--fixture-db-path") + 1] == str(fixture_db_path)
    assert spec.control_file == tmp_path / "artifacts" / "state" / "training-control" / "training-job-1.stop"


def test_training_control_definition_defaults_to_compatibility_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    definition = create_training_control_job_definition()
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    request = StartJobRequest.model_validate(
        {
            "job_type": "training_control",
            "payload": {
                "scope": "futures",
                "interval": "1m",
            },
        }
    )
    details = _job_details("training-job-2")

    spec = definition.launcher(request, details)
    assert spec.control_file is not None
    assert spec.command[spec.command.index("--mode") + 1] == "compatibility"
