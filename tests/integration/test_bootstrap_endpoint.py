import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_bootstrap_returns_loopback_session_info():
    settings = Settings(host="127.0.0.1", port=8765, session_token="bootstrap-token")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/bootstrap", headers={"x-botik-session-token": "bootstrap-token"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["app_name"] == settings.app_name
        assert payload["session"]["session_id"] == "bootstrap-token"
        assert payload["session"]["transport_base_url"] == "http://127.0.0.1:8765"
        assert payload["capabilities"]["jobs"] is True
        assert "/jobs" in payload["routes"]
