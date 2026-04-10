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

    settings = Settings(session_token="runtime-token", runtime_status_fixture_path=fixture_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/runtime-status", headers={"x-botik-session-token": "runtime-token"})

        assert response.status_code == 200
        payload = response.json()
        assert [runtime["runtime_id"] for runtime in payload["runtimes"]] == ["spot", "futures"]
        assert payload["runtimes"][0]["state"] == "offline"
        assert payload["runtimes"][1]["state"] == "offline"
