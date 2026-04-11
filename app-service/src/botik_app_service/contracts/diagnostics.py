from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


DiagnosticsSourceMode = Literal["resolved"]
DiagnosticsPathKind = Literal["file", "directory", "missing"]


class DiagnosticsSummary(BaseModel):
    app_name: str
    version: str
    app_service_base_url: str
    desktop_mode: bool
    runtime_control_mode: str
    routes_count: int = 0
    fixture_overrides_count: int = 0
    missing_paths_count: int = 0
    warnings_count: int = 0


class DiagnosticsConfigEntry(BaseModel):
    key: str
    label: str
    value: str
    masked: bool = False


class DiagnosticsPathEntry(BaseModel):
    key: str
    label: str
    path: str
    source: str
    exists: bool
    kind: DiagnosticsPathKind


class DiagnosticsSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: DiagnosticsSourceMode = "resolved"
    summary: DiagnosticsSummary
    config: list[DiagnosticsConfigEntry] = Field(default_factory=list)
    paths: list[DiagnosticsPathEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
