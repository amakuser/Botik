from __future__ import annotations

from pathlib import Path

from botik_app_service.analytics_read.legacy_adapter import LegacyAnalyticsReadAdapter
from botik_app_service.contracts.analytics import AnalyticsReadSnapshot


class AnalyticsReadService:
    def __init__(
        self,
        *,
        repo_root: Path,
        fixture_db_path: Path | None = None,
        adapter: LegacyAnalyticsReadAdapter | None = None,
    ) -> None:
        self._fixture_db_path = fixture_db_path
        self._adapter = adapter or LegacyAnalyticsReadAdapter(repo_root=repo_root)

    def snapshot(self) -> AnalyticsReadSnapshot:
        if self._fixture_db_path is not None:
            return self._adapter.read_snapshot(db_path=self._fixture_db_path, source_mode="fixture")
        return self._adapter.read_snapshot(source_mode="compatibility")
