from __future__ import annotations

import json
from pathlib import Path

from botik_app_service.contracts.telegram import TelegramConnectivityCheckResult, TelegramOpsSnapshot
from botik_app_service.telegram_ops.legacy_adapter import LegacyTelegramOpsAdapter


class TelegramOpsService:
    def __init__(
        self,
        *,
        repo_root: Path,
        fixture_path: Path | None = None,
        adapter: LegacyTelegramOpsAdapter | None = None,
    ) -> None:
        self._fixture_path = fixture_path
        self._adapter = adapter or LegacyTelegramOpsAdapter(repo_root=repo_root)

    def snapshot(self) -> TelegramOpsSnapshot:
        if self._fixture_path is not None:
            payload = self._load_fixture_payload()
            return TelegramOpsSnapshot.model_validate(payload["snapshot"])
        return self._adapter.read_snapshot()

    def run_connectivity_check(self) -> TelegramConnectivityCheckResult:
        if self._fixture_path is not None:
            payload = self._load_fixture_payload()
            return TelegramConnectivityCheckResult.model_validate(payload["connectivity_check_result"])
        return self._adapter.run_connectivity_check()

    def _load_fixture_payload(self) -> dict[str, object]:
        if self._fixture_path is None:
            raise RuntimeError("telegram fixture path is not configured")
        return json.loads(self._fixture_path.read_text(encoding="utf-8-sig"))
