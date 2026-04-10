import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.logs import LogEntry
from botik_app_service.logs.manager import LogsManager


def test_logs_manager_snapshot_is_bounded_and_truncated():
    manager = LogsManager(buffer_size=5, snapshot_limit=2)

    manager.publish(LogEntry(channel="app", level="INFO", message="entry-1", source="test"))
    manager.publish(LogEntry(channel="app", level="INFO", message="entry-2", source="test"))
    manager.publish(LogEntry(channel="app", level="INFO", message="entry-3", source="test"))

    snapshot = manager.snapshot("app")
    assert [entry.message for entry in snapshot.entries] == ["entry-2", "entry-3"]
    assert snapshot.truncated is True


def test_logs_manager_channel_list_is_limited_to_first_slice_defaults():
    manager = LogsManager(buffer_size=5, snapshot_limit=2)

    assert [channel.channel_id for channel in manager.list_channels()] == ["app", "jobs", "desktop"]


def test_log_capture_handler_writes_into_app_channel():
    manager = LogsManager(buffer_size=5, snapshot_limit=5)
    handler = manager.create_capture_handler()

    import logging

    logger = logging.getLogger("botik_app_service.test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        logger.info("captured-from-handler")
    finally:
        logger.removeHandler(handler)

    snapshot = manager.snapshot("app")
    assert any(entry.message == "captured-from-handler" for entry in snapshot.entries)
