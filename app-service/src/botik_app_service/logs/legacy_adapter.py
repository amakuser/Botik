from datetime import datetime, timezone

from botik_app_service.contracts.logs import LogEntry
from botik_app_service.logs.interfaces import FileLogSource


def parse_legacy_runtime_line(line: str) -> LogEntry | None:
    stripped = line.strip()
    if not stripped:
        return None

    return LogEntry(
        timestamp=datetime.now(timezone.utc),
        channel="legacy-runtime",
        level="INFO",
        message=stripped,
        source="legacy-runtime",
    )


def build_legacy_runtime_source(log_path):
    return FileLogSource(
        channel_id="legacy-runtime",
        path=log_path,
        source_kind="compatibility",
        parser=parse_legacy_runtime_line,
    )
