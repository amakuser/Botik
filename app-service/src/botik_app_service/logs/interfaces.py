from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from botik_app_service.contracts.logs import LogEntry, LogSourceKind

LogLineParser = Callable[[str], LogEntry | None]


@dataclass(frozen=True)
class FileLogSource:
    channel_id: str
    path: Path
    source_kind: LogSourceKind
    parser: LogLineParser
