from __future__ import annotations

from pathlib import Path

from botik_app_service.contracts.diagnostics import (
    DiagnosticsConfigEntry,
    DiagnosticsPathEntry,
    DiagnosticsSnapshot,
    DiagnosticsSummary,
)
from botik_app_service.diagnostics_compat.adapter import DiagnosticsCompatibilityAdapter
from botik_app_service.infra.config import Settings


class DiagnosticsCompatibilityService:
    def __init__(
        self,
        *,
        repo_root: Path,
        settings: Settings,
        adapter: DiagnosticsCompatibilityAdapter | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._settings = settings
        self._adapter = adapter or DiagnosticsCompatibilityAdapter(repo_root=repo_root)

    def snapshot(self) -> DiagnosticsSnapshot:
        routes = ["/", "/jobs", "/logs", "/runtime", "/spot", "/futures", "/telegram", "/analytics", "/models", "/diagnostics"]
        paths = self._build_paths()
        warnings = self._build_warnings(paths)
        summary = DiagnosticsSummary(
            app_name=self._settings.app_name,
            version=self._settings.version,
            app_service_base_url=f"http://{self._settings.host}:{self._settings.port}",
            desktop_mode=self._settings.desktop_mode,
            runtime_control_mode=self._settings.runtime_control_mode,
            routes_count=len(routes),
            fixture_overrides_count=sum(1 for entry in paths if entry.source == "fixture"),
            missing_paths_count=sum(1 for entry in paths if not entry.exists),
            warnings_count=len(warnings),
        )
        return DiagnosticsSnapshot(
            summary=summary,
            config=self._build_config(),
            paths=paths,
            warnings=warnings,
        )

    def _build_config(self) -> list[DiagnosticsConfigEntry]:
        return [
            DiagnosticsConfigEntry(key="service_name", label="Service Name", value=self._settings.service_name),
            DiagnosticsConfigEntry(key="frontend_url", label="Frontend URL", value=self._settings.frontend_url),
            DiagnosticsConfigEntry(key="session_token", label="Session Token", value=self._mask_value(self._settings.session_token), masked=True),
            DiagnosticsConfigEntry(key="desktop_mode", label="Desktop Mode", value=str(self._settings.desktop_mode).lower()),
            DiagnosticsConfigEntry(key="runtime_control_mode", label="Runtime Control Mode", value=self._settings.runtime_control_mode),
            DiagnosticsConfigEntry(
                key="runtime_status_stale_seconds",
                label="Runtime Status Stale Seconds",
                value=str(self._settings.runtime_status_heartbeat_stale_seconds),
            ),
            DiagnosticsConfigEntry(key="spot_account_type", label="Spot Account Type", value=self._settings.spot_read_account_type),
            DiagnosticsConfigEntry(key="futures_account_type", label="Futures Account Type", value=self._settings.futures_read_account_type),
        ]

    def _build_paths(self) -> list[DiagnosticsPathEntry]:
        legacy_paths = self._adapter.resolve_legacy_paths()
        artifacts_root = (self._settings.artifacts_dir or (self._repo_root / ".artifacts" / "local")).resolve()
        diagnostics_paths: list[tuple[str, str, Path, str]] = [
            ("repo_root", "Repo Root", self._repo_root, "resolved"),
            ("config_yaml", "Config YAML", legacy_paths["config_yaml"], "compatibility"),
            ("env_file", "Environment File", legacy_paths["env_file"], "compatibility"),
            ("legacy_db", "Legacy Runtime DB", legacy_paths["legacy_db"], "compatibility"),
            ("legacy_log", "Legacy Runtime Log", self._settings.legacy_runtime_log_path or legacy_paths["legacy_log"], "compatibility"),
            ("models_manifest", "Models Manifest", self._settings.models_read_manifest_path or legacy_paths["active_models_manifest"], "compatibility"),
            ("artifacts_root", "Artifacts Root", artifacts_root, "resolved"),
            ("runtime_control_state_dir", "Runtime Control State", artifacts_root / "state" / "runtime-control", "resolved"),
            ("training_control_state_dir", "Training Control State", artifacts_root / "state" / "training-control", "resolved"),
        ]

        fixture_paths: list[tuple[str, str, Path | None]] = [
            ("runtime_status_fixture", "Runtime Status Fixture", self._settings.runtime_status_fixture_path),
            ("spot_read_fixture_db", "Spot Read Fixture DB", self._settings.spot_read_fixture_db_path),
            ("futures_read_fixture_db", "Futures Read Fixture DB", self._settings.futures_read_fixture_db_path),
            ("analytics_read_fixture_db", "Analytics Read Fixture DB", self._settings.analytics_read_fixture_db_path),
            ("models_read_fixture_db", "Models Read Fixture DB", self._settings.models_read_fixture_db_path),
            ("models_read_manifest_path", "Models Read Manifest Override", self._settings.models_read_manifest_path),
            ("telegram_ops_fixture", "Telegram Ops Fixture", self._settings.telegram_ops_fixture_path),
        ]
        for key, label, path in fixture_paths:
            if path is not None:
                diagnostics_paths.append((key, label, path, "fixture"))

        return [self._to_path_entry(key=key, label=label, path=path, source=source) for key, label, path, source in diagnostics_paths]

    @staticmethod
    def _to_path_entry(*, key: str, label: str, path: Path, source: str) -> DiagnosticsPathEntry:
        resolved = Path(path)
        exists = resolved.exists()
        if exists and resolved.is_dir():
            kind = "directory"
        elif exists and resolved.is_file():
            kind = "file"
        else:
            kind = "missing"
        return DiagnosticsPathEntry(
            key=key,
            label=label,
            path=str(resolved),
            source=source,
            exists=exists,
            kind=kind,
        )

    def _build_warnings(self, paths: list[DiagnosticsPathEntry]) -> list[str]:
        warnings: list[str] = []
        by_key = {entry.key: entry for entry in paths}
        if not by_key["legacy_db"].exists:
            warnings.append("Legacy compatibility DB path is missing.")
        if not by_key["models_manifest"].exists:
            warnings.append("Models manifest path is missing.")
        if self._settings.artifacts_dir is None:
            warnings.append("Artifacts root is not explicitly configured; using the local default.")
        if self._settings.runtime_control_mode == "fixture":
            warnings.append("Runtime control is currently configured in fixture mode.")
        return warnings

    @staticmethod
    def _mask_value(value: str) -> str:
        text = value.strip()
        if len(text) <= 6:
            return "*" * len(text)
        return f"{text[:3]}***{text[-3:]}"
