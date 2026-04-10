import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.events import SystemEvent
from botik_app_service.jobs.event_publisher import EventPublisher


async def test_event_publisher_replays_recent_events():
    publisher = EventPublisher(buffer_size=4)
    await publisher.publish_system_event(SystemEvent(message="hello"))
    iterator = publisher.subscribe()
    payload = await anext(iterator)
    assert payload["kind"] == "system"
    assert payload["message"] == "hello"
    publisher.stop()
