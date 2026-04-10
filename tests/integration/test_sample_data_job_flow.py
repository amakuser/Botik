import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def wait_for_terminal_state(client: TestClient, job_id: str, token: str, timeout_seconds: float = 10.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/jobs/{job_id}", headers={"x-botik-session-token": token})
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["state"] in {"completed", "failed", "cancelled"}:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id} to finish. Last payload: {last_payload}")


def test_sample_data_job_completes_with_progress():
    settings = Settings(session_token="flow-token")
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "flow-token"},
            json={"job_type": "sample_data_import", "payload": {"sleep_ms": 25}},
        )
        assert start.status_code == 200
        payload = start.json()

        completed = wait_for_terminal_state(client, payload["job_id"], "flow-token")
        assert completed["state"] == "completed"
        assert completed["progress"] == 1.0

        listed = client.get("/jobs", headers={"x-botik-session-token": "flow-token"})
        assert listed.status_code == 200
        assert any(item["job_id"] == payload["job_id"] for item in listed.json())
