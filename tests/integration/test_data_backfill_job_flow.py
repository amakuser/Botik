import sqlite3
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def wait_for_terminal_state(client: TestClient, job_id: str, token: str, timeout_seconds: float = 15.0) -> dict:
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


def wait_for_running_state(client: TestClient, job_id: str, token: str, timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/jobs/{job_id}", headers={"x-botik-session-token": token})
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["state"] == "running":
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id} to start running. Last payload: {last_payload}")


def test_data_backfill_job_completes_and_writes_to_slice_db(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "integration-artifacts"
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(artifacts_dir))
    legacy_db = REPO_ROOT / "data" / "botik.db"
    legacy_before = legacy_db.stat().st_mtime_ns if legacy_db.exists() else None

    settings = Settings(session_token="backfill-token")
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "backfill-token"},
            json={
                "job_type": "data_backfill",
                "payload": {
                    "symbol": "BTCUSDT",
                    "category": "spot",
                    "intervals": ["1m"],
                },
            },
        )
        assert start.status_code == 200
        payload = start.json()

        completed = wait_for_terminal_state(client, payload["job_id"], "backfill-token")
        assert completed["state"] == "completed"
        assert completed["progress"] == 1.0

    db_path = artifacts_dir / "state" / "data_backfill.sqlite3"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        candle_count = conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE symbol=? AND category=? AND interval=?",
            ("BTCUSDT", "spot", "1"),
        ).fetchone()[0]
        registry_row = conn.execute(
            "SELECT candle_count FROM symbol_registry WHERE symbol=? AND category=? AND interval=?",
            ("BTCUSDT", "spot", "1"),
        ).fetchone()
    assert candle_count == 12
    assert registry_row is not None
    assert registry_row[0] == 12

    legacy_after = legacy_db.stat().st_mtime_ns if legacy_db.exists() else None
    assert legacy_after == legacy_before


def test_data_backfill_job_can_be_cancelled(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "cancel-artifacts"
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(artifacts_dir))

    settings = Settings(session_token="cancel-token")
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "cancel-token"},
            json={
                "job_type": "data_backfill",
                "payload": {
                    "symbol": "BTCUSDT",
                    "category": "spot",
                    "intervals": ["1m"],
                },
            },
        )
        assert start.status_code == 200
        payload = start.json()
        wait_for_running_state(client, payload["job_id"], "cancel-token")

        stop = client.post(
            f"/jobs/{payload['job_id']}/stop",
            headers={"x-botik-session-token": "cancel-token"},
            json={"reason": "test-cancel"},
        )
        assert stop.status_code == 200
        cancelled = wait_for_terminal_state(client, payload["job_id"], "cancel-token")
        assert cancelled["state"] == "cancelled"
