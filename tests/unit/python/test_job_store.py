import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.jobs import JobDetails, JobState
from botik_app_service.jobs.store import JobStore


def test_job_store_create_update_list():
    store = JobStore()
    details = JobDetails(
        job_id="job-1",
        job_type="foundation.noop",
        state=JobState.QUEUED,
        progress=0.0,
        started_at=None,
        updated_at=datetime.now(timezone.utc),
    )
    store.create(details)
    updated = store.update("job-1", progress=0.5)
    assert updated.progress == 0.5
    assert store.get("job-1") is not None
    assert len(store.list()) == 1
