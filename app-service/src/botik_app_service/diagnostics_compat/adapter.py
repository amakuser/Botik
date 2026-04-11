from __future__ import annotations

from pathlib import Path


class DiagnosticsCompatibilityAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def resolve_legacy_paths(self) -> dict[str, Path]:
        from src.botik.gui.api_helpers import CONFIG_PATH, ENV_PATH, ACTIVE_MODELS_PATH, _load_yaml, _resolve_botik_log_path, _resolve_db_path

        raw_cfg = _load_yaml()
        return {
            "config_yaml": Path(CONFIG_PATH),
            "env_file": Path(ENV_PATH),
            "legacy_db": Path(_resolve_db_path(raw_cfg)),
            "legacy_log": Path(_resolve_botik_log_path(raw_cfg)),
            "active_models_manifest": Path(ACTIVE_MODELS_PATH),
        }

    @property
    def repo_root(self) -> Path:
        return self._repo_root
