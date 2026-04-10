import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.bootstrap import BootstrapPayload
from botik_app_service.contracts.errors import ErrorEnvelope
from botik_app_service.contracts.health import HealthResponse


def test_contract_models_roundtrip():
    health = HealthResponse(status="ok", service="svc", version="1", session_id="abc")
    assert health.model_dump()["status"] == "ok"

    error = ErrorEnvelope(code="boom", message="failed")
    assert error.model_dump()["code"] == "boom"

    payload = BootstrapPayload.model_validate(
        {
            "app_name": "Botik Foundation",
            "version": "1",
            "session": {
                "session_id": "abc",
                "transport_base_url": "http://127.0.0.1:8765",
                "events_url": "http://127.0.0.1:8765/events",
            },
            "capabilities": {
                "desktop": True,
                "jobs": True,
                "routes": ["/", "/jobs"],
            },
            "routes": ["/", "/jobs"],
        }
    )
    assert payload.session.session_id == "abc"
