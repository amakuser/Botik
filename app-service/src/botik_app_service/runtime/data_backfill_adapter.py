from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.botik.marketdata.ohlcv_worker import OHLCVWorker

EXTERNAL_TO_LEGACY_INTERVAL = {
    "1m": "1",
}
LEGACY_TO_EXTERNAL_INTERVAL = {value: key for key, value in EXTERNAL_TO_LEGACY_INTERVAL.items()}


def to_legacy_interval(interval: str) -> str:
    return EXTERNAL_TO_LEGACY_INTERVAL.get(interval, interval)


def to_external_interval(interval: str) -> str:
    return LEGACY_TO_EXTERNAL_INTERVAL.get(interval, interval)


@dataclass(slots=True)
class FixtureStream:
    symbol: str
    category: str
    interval: str
    batches: list[list[list[Any]]]


class FixtureBackfillOHLCVWorker(OHLCVWorker):
    def __init__(
        self,
        fixture_path: Path,
        on_batch: Callable[[str, str, str, int, int, int], None] | None = None,
    ) -> None:
        super().__init__()
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        self._streams = {
            (item["symbol"].upper(), item["category"].lower(), item["interval"]): FixtureStream(
                symbol=item["symbol"].upper(),
                category=item["category"].lower(),
                interval=item["interval"],
                batches=item["batches"],
            )
            for item in payload["streams"]
        }
        self._cursor: dict[tuple[str, str, str], int] = {}
        self._rows_written: dict[tuple[str, str, str], int] = {}
        self._on_batch = on_batch

    async def _fetch_kline(
        self,
        symbol: str,
        category: str,
        interval: str,
        limit: int = 1000,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[list[Any]]:
        stream_key = (symbol.upper(), category.lower(), to_external_interval(interval))
        stream = self._streams.get(stream_key)
        if stream is None:
            return []

        current_index = self._cursor.get(stream_key, 0)
        if current_index > 0:
            return []

        aggregated: list[list[Any]] = []
        rows_written = 0
        for index, batch in enumerate(stream.batches, start=1):
            aggregated.extend(batch)
            rows_written += len(batch)
            if self._on_batch is not None:
                self._on_batch(
                    stream.symbol,
                    stream.category,
                    stream.interval,
                    index,
                    len(stream.batches),
                    rows_written,
                )
        self._cursor[stream_key] = len(stream.batches)
        self._rows_written[stream_key] = rows_written
        return aggregated[:limit]
