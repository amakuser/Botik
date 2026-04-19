from __future__ import annotations

from pathlib import Path


class DiagnosticsCompatibilityAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def resolve_legacy_paths(self) -> dict[str, Path]:
        from botik_app_service.infra.legacy_helpers import (
            active_models_path,
            config_path,
            env_path,
            load_config,
            resolve_db_path,
            resolve_log_path,
        )

        cfg = load_config(self._repo_root)
        return {
            "config_yaml": config_path(self._repo_root),
            "env_file": env_path(self._repo_root),
            "legacy_db": resolve_db_path(self._repo_root, cfg),
            "legacy_log": resolve_log_path(self._repo_root, cfg),
            "active_models_manifest": active_models_path(self._repo_root),
        }

    @property
    def repo_root(self) -> Path:
        return self._repo_root
