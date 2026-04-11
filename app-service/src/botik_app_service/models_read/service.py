from __future__ import annotations

from pathlib import Path

from botik_app_service.contracts.models import ModelsReadSnapshot
from botik_app_service.models_read.legacy_adapter import LegacyModelsReadAdapter


class ModelsReadService:
    def __init__(
        self,
        *,
        repo_root: Path,
        fixture_db_path: Path | None = None,
        manifest_path: Path | None = None,
        adapter: LegacyModelsReadAdapter | None = None,
    ) -> None:
        self._fixture_db_path = fixture_db_path
        self._manifest_path = manifest_path
        self._adapter = adapter or LegacyModelsReadAdapter(repo_root=repo_root)

    def snapshot(self) -> ModelsReadSnapshot:
        resolved_manifest_path = self._manifest_path
        if resolved_manifest_path is None and self._fixture_db_path is not None:
            candidate = self._fixture_db_path.with_name("active_models.fixture.yaml")
            if candidate.exists():
                resolved_manifest_path = candidate
        if self._fixture_db_path is not None:
            return self._adapter.read_snapshot(
                db_path=self._fixture_db_path,
                manifest_path=resolved_manifest_path,
                source_mode="fixture",
            )
        return self._adapter.read_snapshot(manifest_path=resolved_manifest_path, source_mode="compatibility")
