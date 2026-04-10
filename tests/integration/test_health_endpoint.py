import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_health_endpoint_returns_token_bound_payload():
    settings = Settings(session_token="test-token")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health", headers={"x-botik-session-token": "test-token"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == settings.service_name
        assert payload["session_id"] == "test-token"
