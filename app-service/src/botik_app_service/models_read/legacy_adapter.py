from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from botik_app_service.contracts.models import (
    ModelRegistryEntry,
    ModelsReadSnapshot,
    ModelsReadSourceMode,
    ModelsReadTruncation,
    ModelsScopeStatus,
    ModelsSummary,
    PipelineState,
    TrainingRunSummary,
)

REGISTRY_LIMIT = 8
RECENT_RUNS_LIMIT = 6
READY_STATUSES = {"active", "ready", "trained", "completed"}
ACTIVE_SENTINELS = {"", "unknown", "none", "null"}


def _derive_pipeline_state(latest_run_status: str, ready_scopes: int) -> PipelineState:
    """Map raw training run status + ready_scopes to a normalized PipelineState.

    Mapping:
      'running'                              -> 'training'
      'completed' AND ready_scopes > 0       -> 'serving'
      'completed' AND ready_scopes == 0      -> 'idle'
      'failed'                               -> 'error'
      'not available' (sentinel: no runs)    -> 'idle'  (system at rest)
      anything else / null                   -> 'unknown'
    """
    status = (latest_run_status or "").strip().lower()
    if status == "running":
        return "training"
    if status == "completed":
        return "serving" if ready_scopes > 0 else "idle"
    if status == "failed":
        return "error"
    if status == "not available":
        return "idle"
    return "unknown"


class LegacyModelsReadAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(
        self,
        *,
        db_path: Path | None = None,
        manifest_path: Path | None = None,
        source_mode: ModelsReadSourceMode,
    ) -> ModelsReadSnapshot:
        pointer = self._read_manifest(manifest_path or self._resolve_manifest_path())
        resolved_db_path = db_path or self._resolve_db_path()
        if not resolved_db_path.exists():
            return self._empty_snapshot(source_mode=source_mode, pointer=pointer)

        try:
            with sqlite3.connect(f"file:{resolved_db_path}?mode=ro", uri=True, timeout=2) as connection:
                connection.row_factory = sqlite3.Row
                return self._build_snapshot(connection, pointer=pointer, source_mode=source_mode)
        except sqlite3.Error:
            return self._empty_snapshot(source_mode=source_mode, pointer=pointer)

    def _build_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        pointer: dict[str, str],
        source_mode: ModelsReadSourceMode,
    ) -> ModelsReadSnapshot:
        registry_entries, latest_registry_by_scope, total_models, registry_truncated = self._read_registry_entries(
            connection,
            pointer=pointer,
        )
        recent_runs, latest_run_by_scope, total_runs, runs_truncated = self._read_recent_training_runs(connection)
        scopes = [
            self._build_scope_status(
                scope="spot",
                pointer=pointer,
                latest_registry=latest_registry_by_scope.get("spot"),
                latest_run=latest_run_by_scope.get("spot"),
            ),
            self._build_scope_status(
                scope="futures",
                pointer=pointer,
                latest_registry=latest_registry_by_scope.get("futures"),
                latest_run=latest_run_by_scope.get("futures"),
            ),
        ]
        latest_run = recent_runs[0] if recent_runs else None
        active_declared_count = sum(
            1
            for key in ("active_spot_model", "active_futures_model")
            if str(pointer.get(key) or "").strip().lower() not in ACTIVE_SENTINELS
        )
        ready_scopes = sum(1 for scope in scopes if scope.ready)
        raw_status = latest_run.status if latest_run else "not available"
        summary = ModelsSummary(
            total_models=total_models,
            active_declared_count=active_declared_count,
            ready_scopes=ready_scopes,
            recent_training_runs_count=total_runs,
            latest_run_scope=latest_run.scope if latest_run else "not available",
            latest_run_status=raw_status,
            latest_run_mode=latest_run.mode if latest_run else "not available",
            manifest_status=str(pointer.get("manifest_status") or "missing"),
            db_available=True,
            pipeline_state=_derive_pipeline_state(raw_status, ready_scopes),
        )
        return ModelsReadSnapshot(
            source_mode=source_mode,
            summary=summary,
            scopes=scopes,
            registry_entries=registry_entries,
            recent_training_runs=recent_runs,
            truncated=ModelsReadTruncation(
                registry_entries=registry_truncated,
                recent_training_runs=runs_truncated,
            ),
        )

    def _read_registry_entries(
        self,
        connection: sqlite3.Connection,
        *,
        pointer: dict[str, str],
    ) -> tuple[list[ModelRegistryEntry], dict[str, ModelRegistryEntry], int, bool]:
        if not self._table_exists(connection, "model_registry"):
            return [], {}, 0, False

        total_models = int(
            connection.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0] or 0
        )
        rows = connection.execute(
            """
            SELECT
                COALESCE(model_id, '') AS model_id,
                COALESCE(path_or_payload, '') AS path_or_payload,
                COALESCE(metrics_json, '{}') AS metrics_json,
                COALESCE(created_at_utc, '') AS created_at_utc
            FROM model_registry
            ORDER BY COALESCE(created_at_utc, '') DESC, id DESC
            LIMIT ?
            """,
            (REGISTRY_LIMIT + 1,),
        ).fetchall()
        truncated = len(rows) > REGISTRY_LIMIT
        limited_rows = rows[:REGISTRY_LIMIT]
        latest_by_scope: dict[str, ModelRegistryEntry] = {}
        entries: list[ModelRegistryEntry] = []
        for row in limited_rows:
            model_id = str(row["model_id"] or "").strip()
            metrics = self._parse_json_dict(row["metrics_json"])
            scope = self._infer_scope(model_id=model_id, metrics=metrics)
            entry = ModelRegistryEntry(
                model_id=model_id,
                scope=scope,
                status=str(metrics.get("status") or "candidate"),
                quality_score=self._safe_float(metrics.get("quality_score")),
                policy=str(metrics.get("policy") or "unknown"),
                source_mode=str(metrics.get("source_mode") or metrics.get("source") or "unknown"),
                artifact_name=Path(str(row["path_or_payload"] or "")).name,
                created_at_utc=str(row["created_at_utc"] or "not available") or "not available",
                is_declared_active=model_id in {
                    str(pointer.get("active_spot_model") or "").strip(),
                    str(pointer.get("active_futures_model") or "").strip(),
                },
            )
            entries.append(entry)
            if scope in {"spot", "futures"} and scope not in latest_by_scope:
                latest_by_scope[scope] = entry
        return entries, latest_by_scope, total_models, truncated

    def _read_recent_training_runs(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[list[TrainingRunSummary], dict[str, TrainingRunSummary], int, bool]:
        if not self._table_exists(connection, "ml_training_runs"):
            return [], {}, 0, False

        total_runs = int(
            connection.execute("SELECT COUNT(*) FROM ml_training_runs").fetchone()[0] or 0
        )
        rows = connection.execute(
            """
            SELECT
                COALESCE(run_id, '') AS run_id,
                COALESCE(model_scope, '') AS model_scope,
                COALESCE(model_version, '') AS model_version,
                COALESCE(mode, '') AS mode,
                COALESCE(status, '') AS status,
                COALESCE(is_trained, 0) AS is_trained,
                COALESCE(started_at_utc, '') AS started_at_utc,
                COALESCE(finished_at_utc, '') AS finished_at_utc
            FROM ml_training_runs
            ORDER BY COALESCE(started_at_utc, '') DESC, COALESCE(finished_at_utc, '') DESC, run_id DESC
            LIMIT ?
            """,
            (RECENT_RUNS_LIMIT + 1,),
        ).fetchall()
        truncated = len(rows) > RECENT_RUNS_LIMIT
        latest_by_scope: dict[str, TrainingRunSummary] = {}
        runs: list[TrainingRunSummary] = []
        for row in rows[:RECENT_RUNS_LIMIT]:
            scope = self._infer_scope(model_id=str(row["model_version"] or ""), explicit_scope=row["model_scope"])
            run = TrainingRunSummary(
                run_id=str(row["run_id"] or ""),
                scope=scope,
                model_version=str(row["model_version"] or ""),
                mode=str(row["mode"] or ""),
                status=str(row["status"] or ""),
                is_trained=bool(int(row["is_trained"] or 0)),
                started_at_utc=str(row["started_at_utc"] or "not available") or "not available",
                finished_at_utc=str(row["finished_at_utc"] or ""),
            )
            runs.append(run)
            if scope in {"spot", "futures"} and scope not in latest_by_scope:
                latest_by_scope[scope] = run
        return runs, latest_by_scope, total_runs, truncated

    def _build_scope_status(
        self,
        *,
        scope: str,
        pointer: dict[str, str],
        latest_registry: ModelRegistryEntry | None,
        latest_run: TrainingRunSummary | None,
    ) -> ModelsScopeStatus:
        active_model = str(pointer.get(f"active_{scope}_model") or "unknown").strip() or "unknown"
        checkpoint_name = Path(str(pointer.get(f"{scope}_checkpoint_path") or "")).name
        ready = False
        reason = "No active model declaration or recent training run."
        if active_model.lower() not in ACTIVE_SENTINELS:
            ready = True
            reason = "Active model declared in active_models.yaml."
        elif latest_run and (latest_run.is_trained or latest_run.status.strip().lower() in READY_STATUSES):
            ready = True
            reason = "Latest training run finished in a ready state."
        elif latest_registry and latest_registry.status.strip().lower() in READY_STATUSES:
            ready = True
            reason = "Latest registry entry is marked ready."
        elif latest_run and latest_run.status:
            reason = f"Latest training run is {latest_run.status}."

        return ModelsScopeStatus(
            scope="spot" if scope == "spot" else "futures",
            active_model=active_model,
            checkpoint_name=checkpoint_name,
            latest_registry_model=latest_registry.model_id if latest_registry else "not available",
            latest_registry_status=latest_registry.status if latest_registry else "not available",
            latest_registry_created_at=latest_registry.created_at_utc if latest_registry else "not available",
            latest_training_model_version=latest_run.model_version if latest_run else "not available",
            latest_training_status=latest_run.status if latest_run else "not available",
            latest_training_mode=latest_run.mode if latest_run else "not available",
            latest_training_started_at=latest_run.started_at_utc if latest_run else "not available",
            ready=ready,
            status_reason=reason,
        )

    def _read_manifest(self, path: Path) -> dict[str, str]:
        payload = {
            "manifest_status": "missing",
            "manifest_path": str(path),
            "loaded_at": "-",
            "active_spot_model": "unknown",
            "active_futures_model": "unknown",
            "spot_checkpoint_path": "",
            "futures_checkpoint_path": "",
        }
        if not path.exists():
            return payload
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                payload["manifest_status"] = "failed"
                return payload
            payload["manifest_status"] = "loaded"
            payload["active_spot_model"] = str(raw.get("active_spot_model") or "unknown").strip() or "unknown"
            payload["active_futures_model"] = str(raw.get("active_futures_model") or "unknown").strip() or "unknown"
            payload["spot_checkpoint_path"] = str(raw.get("spot_checkpoint_path") or "").strip()
            payload["futures_checkpoint_path"] = str(raw.get("futures_checkpoint_path") or "").strip()
            payload["loaded_at"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            return payload
        except Exception:
            payload["manifest_status"] = "failed"
            return payload

    def _resolve_db_path(self) -> Path:
        from botik_app_service.infra.legacy_helpers import load_config, resolve_db_path

        return resolve_db_path(self._repo_root, load_config(self._repo_root))

    def _resolve_manifest_path(self) -> Path:
        return self._repo_root / "active_models.yaml"

    @staticmethod
    def _infer_scope(
        *,
        model_id: str,
        metrics: dict[str, Any] | None = None,
        explicit_scope: Any | None = None,
    ) -> str:
        pieces = [
            str(explicit_scope or ""),
            str((metrics or {}).get("model_scope") or ""),
            str((metrics or {}).get("instrument") or ""),
            str(model_id or ""),
        ]
        hint = " ".join(piece.strip().lower() for piece in pieces if piece)
        if "future" in hint or "linear" in hint:
            return "futures"
        if "spot" in hint:
            return "spot"
        return "unknown"

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _parse_json_dict(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if raw in (None, ""):
            return {}
        try:
            value = json.loads(str(raw))
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value in (None, "") else float(value)
        except Exception:
            return None

    @staticmethod
    def _empty_snapshot(
        *,
        source_mode: ModelsReadSourceMode,
        pointer: dict[str, str],
    ) -> ModelsReadSnapshot:
        scopes = [
            ModelsScopeStatus(
                scope="spot",
                active_model=str(pointer.get("active_spot_model") or "unknown"),
                checkpoint_name=Path(str(pointer.get("spot_checkpoint_path") or "")).name,
                ready=str(pointer.get("active_spot_model") or "").strip().lower() not in ACTIVE_SENTINELS,
                status_reason="No readable model registry database found.",
            ),
            ModelsScopeStatus(
                scope="futures",
                active_model=str(pointer.get("active_futures_model") or "unknown"),
                checkpoint_name=Path(str(pointer.get("futures_checkpoint_path") or "")).name,
                ready=str(pointer.get("active_futures_model") or "").strip().lower() not in ACTIVE_SENTINELS,
                status_reason="No readable model registry database found.",
            ),
        ]
        ready_scopes = sum(1 for scope in scopes if scope.ready)
        return ModelsReadSnapshot(
            source_mode=source_mode,
            summary=ModelsSummary(
                active_declared_count=sum(
                    1
                    for key in ("active_spot_model", "active_futures_model")
                    if str(pointer.get(key) or "").strip().lower() not in ACTIVE_SENTINELS
                ),
                ready_scopes=ready_scopes,
                manifest_status=str(pointer.get("manifest_status") or "missing"),
                db_available=False,
                pipeline_state=_derive_pipeline_state("not available", ready_scopes),
            ),
            scopes=scopes,
        )
