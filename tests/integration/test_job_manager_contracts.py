import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_job_manager_start_and_stop_roundtrip():
    settings = Settings(session_token="jobs-token")
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "jobs-token"},
            json={"job_type": "sample_data_import", "payload": {"sleep_ms": 150}},
        )
        assert start.status_code == 200
        started = start.json()
        assert started["job_type"] == "sample_data_import"
        assert started["state"] in {"running", "starting", "queued"}

        stop = client.post(
            f"/jobs/{started['job_id']}/stop",
            headers={"x-botik-session-token": "jobs-token"},
            json={"reason": "test"},
        )
        assert stop.status_code == 200
        stopped = stop.json()
        assert stopped["state"] == "cancelled"
