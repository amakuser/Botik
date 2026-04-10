import asyncio
from pathlib import Path
from typing import Callable

from botik_app_service.contracts.logs import LogEntry


class FileTail:
    def __init__(
        self,
        *,
        path: Path,
        parser: Callable[[str], LogEntry | None],
        on_entry: Callable[[LogEntry], None],
        on_available: Callable[[bool], None],
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._path = path
        self._parser = parser
        self._on_entry = on_entry
        self._on_available = on_available
        self._poll_interval_seconds = poll_interval_seconds

    async def run(self) -> None:
        offset = 0
        while True:
            if not self._path.exists():
                self._on_available(False)
                offset = 0
                await asyncio.sleep(self._poll_interval_seconds)
                continue

            self._on_available(True)
            file_size = self._path.stat().st_size
            if file_size < offset:
                offset = 0

            with self._path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline()
                    if line == "":
                        offset = handle.tell()
                        break

                    parsed = self._parser(line.rstrip("\r\n"))
                    if parsed is not None:
                        self._on_entry(parsed)

            await asyncio.sleep(self._poll_interval_seconds)
