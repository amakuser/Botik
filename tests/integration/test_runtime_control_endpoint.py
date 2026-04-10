import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_runtime_control_start_and_stop_uses_fixture_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", f"{REPO_ROOT / 'app-service' / 'src'};{REPO_ROOT}")
    fixture_path = tmp_path / "runtime-status.fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-11T10:00:00Z",
                "runtimes": [
                    {
                        "runtime_id": "spot",
                        "label": "Spot Runtime",
                        "state": "offline",
                        "pids": [],
                        "pid_count": 0,
                        "last_heartbeat_at": None,
                        "last_heartbeat_age_seconds": None,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "no matching runtime process detected",
                        "source_mode": "fixture",
                    },
                    {
                        "runtime_id": "futures",
                        "label": "Futures Runtime",
                        "state": "offline",
                        "pids": [],
                        "pid_count": 0,
                        "last_heartbeat_at": None,
                        "last_heartbeat_age_seconds": None,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "no matching runtime process detected",
                        "source_mode": "fixture",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        session_token="runtime-token",
        runtime_status_fixture_path=fixture_path,
        runtime_control_mode="fixture",
        artifacts_dir=tmp_path,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        before = client.get("/runtime-status", headers={"x-botik-session-token": "runtime-token"})
        assert before.status_code == 200
        assert before.json()["runtimes"][0]["state"] == "offline"

        start = client.post("/runtime-control/spot/start", headers={"x-botik-session-token": "runtime-token"})
        assert start.status_code == 200
        assert start.json()["runtime_id"] == "spot"
        assert start.json()["state"] == "running"
        assert start.json()["source_mode"] == "fixture"

        after_start = client.get("/runtime-status", headers={"x-botik-session-token": "runtime-token"})
        assert after_start.status_code == 200
        runtimes = {runtime["runtime_id"]: runtime for runtime in after_start.json()["runtimes"]}
        assert runtimes["spot"]["state"] == "running"
        assert runtimes["spot"]["pid_count"] == 1
        assert runtimes["futures"]["state"] == "offline"

        stop = client.post("/runtime-control/spot/stop", headers={"x-botik-session-token": "runtime-token"})
        assert stop.status_code == 200
        assert stop.json()["runtime_id"] == "spot"
        assert stop.json()["state"] == "offline"

        after_stop = client.get("/runtime-status", headers={"x-botik-session-token": "runtime-token"})
        assert after_stop.status_code == 200
        runtimes = {runtime["runtime_id"]: runtime for runtime in after_stop.json()["runtimes"]}
        assert runtimes["spot"]["state"] == "offline"
