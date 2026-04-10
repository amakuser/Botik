import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_runtime_status_endpoint_returns_fixture_snapshot(tmp_path):
    fixture_path = tmp_path / "runtime-status.fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-11T10:00:00Z",
                "runtimes": [
                    {
                        "runtime_id": "spot",
                        "label": "Spot Runtime",
                        "state": "running",
                        "pids": [1234],
                        "pid_count": 1,
                        "last_heartbeat_at": "2026-04-11T09:59:55Z",
                        "last_heartbeat_age_seconds": 5,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "process present with recent heartbeat activity",
                        "source_mode": "fixture",
                    },
                    {
                        "runtime_id": "futures",
                        "label": "Futures Runtime",
                        "state": "degraded",
                        "pids": [4567],
                        "pid_count": 1,
                        "last_heartbeat_at": "2026-04-11T09:55:00Z",
                        "last_heartbeat_age_seconds": 300,
                        "last_error": "stale heartbeat",
                        "last_error_at": "2026-04-11T09:58:00Z",
                        "status_reason": "process present but heartbeat is stale",
                        "source_mode": "fixture",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(session_token="runtime-token", runtime_status_fixture_path=fixture_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/runtime-status", headers={"x-botik-session-token": "runtime-token"})

        assert response.status_code == 200
        payload = response.json()
        assert [runtime["runtime_id"] for runtime in payload["runtimes"]] == ["spot", "futures"]
        assert payload["runtimes"][0]["state"] == "running"
        assert payload["runtimes"][1]["state"] == "degraded"
