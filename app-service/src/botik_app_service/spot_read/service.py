from __future__ import annotations

from pathlib import Path

from botik_app_service.contracts.spot import SpotReadSnapshot
from botik_app_service.spot_read.legacy_adapter import LegacySpotReadAdapter


class SpotReadService:
    def __init__(
        self,
        *,
        repo_root: Path,
        account_type: str = "UNIFIED",
        fixture_db_path: Path | None = None,
        adapter: LegacySpotReadAdapter | None = None,
    ) -> None:
        self._account_type = account_type
        self._fixture_db_path = fixture_db_path
        self._adapter = adapter or LegacySpotReadAdapter(repo_root=repo_root)

    def snapshot(self) -> SpotReadSnapshot:
        if self._fixture_db_path is not None:
            return self._adapter.read_snapshot(
                account_type=self._account_type,
                db_path=self._fixture_db_path,
                source_mode="fixture",
            )
        return self._adapter.read_snapshot(account_type=self._account_type, source_mode="compatibility")
