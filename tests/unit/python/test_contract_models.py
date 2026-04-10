import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.jobs import StartJobRequest
from botik_app_service.contracts.bootstrap import BootstrapPayload
from botik_app_service.contracts.errors import ErrorEnvelope
from botik_app_service.contracts.health import HealthResponse
from botik_app_service.contracts.logs import LogChannelSnapshot, LogEntry


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
                "routes": ["/", "/jobs", "/logs"],
            },
            "routes": ["/", "/jobs", "/logs"],
        }
    )
    assert payload.session.session_id == "abc"

    backfill_request = StartJobRequest.model_validate(
        {
            "job_type": "data_backfill",
            "payload": {
                "symbol": "BTCUSDT",
                "category": "spot",
                "intervals": ["1m"],
            },
        }
    )
    assert backfill_request.payload_dict()["intervals"] == ("1m",)

    snapshot = LogChannelSnapshot.model_validate(
        {
            "channel": "app",
            "entries": [
                {
                    "channel": "app",
                    "level": "INFO",
                    "message": "hello",
                    "source": "botik_app_service",
                }
            ],
            "truncated": False,
        }
    )
    assert isinstance(snapshot.entries[0], LogEntry)
