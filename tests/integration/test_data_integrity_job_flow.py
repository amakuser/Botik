import time
from pathlib import Path
import sys

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def wait_for_terminal_state(client: TestClient, job_id: str, token: str, timeout_seconds: float = 20.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/jobs/{job_id}", headers={"x-botik-session-token": token})
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["state"] in {"completed", "failed", "cancelled"}:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id}. Last payload: {last_payload}")


def test_data_integrity_job_validates_slice_owned_backfill_db(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "integrity-artifacts"
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(artifacts_dir))
    legacy_db = REPO_ROOT / "data" / "botik.db"
    legacy_before = legacy_db.stat().st_mtime_ns if legacy_db.exists() else None

    settings = Settings(session_token="integrity-token")
    app = create_app(settings)
    with TestClient(app) as client:
        backfill = client.post(
            "/jobs",
            headers={"x-botik-session-token": "integrity-token"},
            json={
                "job_type": "data_backfill",
                "payload": {
                    "symbol": "BTCUSDT",
                    "category": "spot",
                    "intervals": ["1m"],
                },
            },
        )
        assert backfill.status_code == 200
        backfill_completed = wait_for_terminal_state(client, backfill.json()["job_id"], "integrity-token")
        assert backfill_completed["state"] == "completed"

        integrity = client.post(
            "/jobs",
            headers={"x-botik-session-token": "integrity-token"},
            json={
                "job_type": "data_integrity",
                "payload": {
                    "symbol": "BTCUSDT",
                    "category": "spot",
                    "intervals": ["1m"],
                },
            },
        )
        assert integrity.status_code == 200
        integrity_completed = wait_for_terminal_state(client, integrity.json()["job_id"], "integrity-token")
        assert integrity_completed["state"] == "completed"
        assert integrity_completed["progress"] == 1.0

    legacy_after = legacy_db.stat().st_mtime_ns if legacy_db.exists() else None
    assert legacy_after == legacy_before
