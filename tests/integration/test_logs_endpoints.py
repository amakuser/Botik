import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.api.routes_logs import stream_log_channel
from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app
from botik_app_service.contracts.logs import LogEntry


def test_logs_channels_and_snapshots_are_bounded(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    settings = Settings(session_token="logs-token", artifacts_dir=artifacts_dir, log_channel_buffer_size=6, log_snapshot_limit=2)
    desktop_events = artifacts_dir / "structured" / "service-events.jsonl"
    desktop_events.parent.mkdir(parents=True, exist_ok=True)
    desktop_events.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": 1_700_000_000_000, "kind": "spawn_requested", "payload": {"target": "desktop-shell"}}),
                json.dumps({"timestamp": 1_700_000_001_000, "kind": "ready", "payload": {"target": "desktop-shell"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(settings)
    with TestClient(app) as client:
        for index in range(4):
            app.state.logs_manager.publish(
                LogEntry(channel="app", level="INFO", message=f"integration-app-{index}", source="integration-test")
            )
        time.sleep(0.2)

        channels_response = client.get("/logs/channels", headers={"x-botik-session-token": "logs-token"})
        assert channels_response.status_code == 200
        channels = channels_response.json()
        assert [channel["channel_id"] for channel in channels] == ["app", "jobs", "desktop"]
        assert channels[2]["available"] is True

        app_response = client.get("/logs/app", headers={"x-botik-session-token": "logs-token"})
        assert app_response.status_code == 200
        app_snapshot = app_response.json()
        assert app_snapshot["truncated"] is True
        assert len(app_snapshot["entries"]) == 2

        desktop_response = client.get("/logs/desktop", headers={"x-botik-session-token": "logs-token"})
        assert desktop_response.status_code == 200
        desktop_snapshot = desktop_response.json()
        assert len(desktop_snapshot["entries"]) == 2
        assert any("ready" in entry["message"] for entry in desktop_snapshot["entries"])


async def test_logs_stream_emits_live_app_entries():
    settings = Settings(session_token="logs-stream-token")
    app = create_app(settings)
    with TestClient(app) as client:
        async def receive():
            await asyncio.sleep(60)
            return {"type": "http.disconnect"}

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/logs/app/stream",
                "headers": [],
                "query_string": b"session_token=logs-stream-token",
                "app": app,
            },
            receive,
        )

        response = await stream_log_channel("app", request)
        next_chunk = asyncio.create_task(response.body_iterator.__anext__())
        await asyncio.sleep(0)
        app.state.logs_manager.publish(
            LogEntry(channel="app", level="INFO", message="streamed-app-entry", source="integration-test")
        )
        chunk = await asyncio.wait_for(next_chunk, timeout=2)
        payload = json.loads(chunk.split("data: ", 1)[1])

        assert response.status_code == 200
        assert payload["channel"] == "app"
        assert payload["entry"]["message"] == "streamed-app-entry"
