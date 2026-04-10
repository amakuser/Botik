import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.jobs import JobDetails, JobState, StartJobRequest
from botik_app_service.jobs.data_backfill_job import JOB_TYPE, create_data_backfill_job_definition


def test_data_backfill_job_definition_builds_worker_launch_spec_with_fixed_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(tmp_path / "suite-artifacts"))
    definition = create_data_backfill_job_definition()
    details = JobDetails(
        job_id="job-backfill",
        job_type=JOB_TYPE,
        state=JobState.QUEUED,
        progress=0.0,
        started_at=None,
        updated_at=datetime.now(timezone.utc),
        exit_code=None,
        last_error=None,
        log_stream_id="stream-backfill",
    )
    request = StartJobRequest(
        job_type=JOB_TYPE,
        payload={
            "symbol": "BTCUSDT",
            "category": "spot",
            "intervals": ["1m"],
        },
    )

    launch_spec = definition.launcher(request, details)

    assert definition.job_type == JOB_TYPE
    assert launch_spec.command[0] == sys.executable
    assert "botik_app_service.runtime.data_backfill_worker" in launch_spec.command
    assert "--intervals" in launch_spec.command
    assert "1m" in launch_spec.command
    assert "--db-url" in launch_spec.command
    assert launch_spec.env is not None
    assert launch_spec.env["DB_URL"].endswith("/state/data_backfill.sqlite3")
    assert "PYTHONPATH" in launch_spec.env
