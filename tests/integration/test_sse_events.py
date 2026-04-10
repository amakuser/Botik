import asyncio
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.events import SystemEvent
from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


def test_events_endpoint_streams_heartbeat():
    settings = Settings(session_token="events-token", sse_heartbeat_interval_seconds=60.0)
    app = create_app(settings)
    with TestClient(app) as client:
        asyncio.run(app.state.event_publisher.publish_system_event(SystemEvent(message="smoke")))
        app.state.event_publisher.stop()
        with client.stream("GET", "/events", headers={"x-botik-session-token": "events-token"}) as response:
            chunks = []
            for chunk in response.iter_lines():
                if chunk:
                    chunks.append(chunk)
                if any("event: system" in item for item in chunks) and any("data: " in item for item in chunks):
                    break

        payload_text = "\n".join(chunks)
        assert "event: system" in payload_text
        data_line = next(line for line in payload_text.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line[len("data: "):])
        assert payload["kind"] == "system"
