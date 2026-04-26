from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ModelsReadSourceMode = Literal["fixture", "compatibility"]
ModelScope = Literal["spot", "futures", "unknown"]

# Normalized pipeline state derived from ml_training_runs.status + ready_scopes.
# Kept separate from latest_run_status (raw) to allow both to coexist.
PipelineState = Literal["idle", "training", "serving", "error", "unknown"]


class ModelsSummary(BaseModel):
    total_models: int = 0
    active_declared_count: int = 0
    ready_scopes: int = 0
    recent_training_runs_count: int = 0
    latest_run_scope: str = "not available"
    latest_run_status: str = "not available"
    latest_run_mode: str = "not available"
    manifest_status: str = "missing"
    db_available: bool = False
    # Normalized pipeline state — additive field, default keeps backward compat.
    pipeline_state: PipelineState = "unknown"


class ModelsScopeStatus(BaseModel):
    scope: Literal["spot", "futures"]
    active_model: str = "unknown"
    checkpoint_name: str = ""
    latest_registry_model: str = "not available"
    latest_registry_status: str = "not available"
    latest_registry_created_at: str = "not available"
    latest_training_model_version: str = "not available"
    latest_training_status: str = "not available"
    latest_training_mode: str = "not available"
    latest_training_started_at: str = "not available"
    ready: bool = False
    status_reason: str = "No active model declaration or recent training run."


class ModelRegistryEntry(BaseModel):
    model_id: str
    scope: ModelScope = "unknown"
    status: str = "candidate"
    quality_score: float | None = None
    policy: str = "unknown"
    source_mode: str = "unknown"
    artifact_name: str = ""
    created_at_utc: str = "not available"
    is_declared_active: bool = False


class TrainingRunSummary(BaseModel):
    run_id: str
    scope: ModelScope = "unknown"
    model_version: str = ""
    mode: str = ""
    status: str = ""
    is_trained: bool = False
    started_at_utc: str = "not available"
    finished_at_utc: str = ""


class ModelsReadTruncation(BaseModel):
    registry_entries: bool = False
    recent_training_runs: bool = False


class ModelsReadSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: ModelsReadSourceMode
    summary: ModelsSummary = Field(default_factory=ModelsSummary)
    scopes: list[ModelsScopeStatus] = Field(default_factory=list)
    registry_entries: list[ModelRegistryEntry] = Field(default_factory=list)
    recent_training_runs: list[TrainingRunSummary] = Field(default_factory=list)
    truncated: ModelsReadTruncation = Field(default_factory=ModelsReadTruncation)
