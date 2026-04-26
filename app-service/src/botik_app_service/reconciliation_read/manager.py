from __future__ import annotations

from pathlib import Path

from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.reconciliation_read.legacy_adapter import LegacyReconciliationReadAdapter


class ReconciliationReadService:
    def __init__(
        self,
        *,
        repo_root: Path,
        adapter: LegacyReconciliationReadAdapter | None = None,
    ) -> None:
        self._adapter = adapter or LegacyReconciliationReadAdapter(repo_root=repo_root)

    def snapshot(self) -> ReconciliationSnapshot:
        return self._adapter.read_snapshot()
