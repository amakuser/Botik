"""Unit tests for HomeSummaryService and derivation logic.

All tests use real Pydantic model construction for fixtures.
No real SQLite, no real services — stubs return prepared snapshots.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.db_health import DbHealthSnapshot
from botik_app_service.contracts.futures import (
    FuturesPosition,
    FuturesReadSnapshot,
    FuturesReadSummary,
    FuturesReadTruncation,
)
from botik_app_service.contracts.jobs import JobState, JobSummary
from botik_app_service.contracts.models import (
    ModelRegistryEntry,
    ModelsReadSnapshot,
    ModelsSummary,
    TrainingRunSummary,
)
from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.contracts.runtime_status import (
    RuntimeStatus,
    RuntimeStatusSnapshot,
)
from botik_app_service.home.service import HomeSummaryService, _build_summary
from botik_app_service.home.interfaces import HomeSummaryInputs

# ---------------------------------------------------------------------------
# Shared fixture time
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------

def _make_runtime_snapshot(
    spot_state: str = "running",
    futures_state: str = "running",
    spot_lag: float | None = 5.0,
    futures_lag: float | None = 5.0,
) -> RuntimeStatusSnapshot:
    return RuntimeStatusSnapshot(
        generated_at=_NOW,
        runtimes=[
            RuntimeStatus(
                runtime_id="spot",
                label="Spot Runtime",
                state=spot_state,
                pid_count=1,
                last_heartbeat_age_seconds=spot_lag,
                status_reason="ok",
                source_mode="fixture",
            ),
            RuntimeStatus(
                runtime_id="futures",
                label="Futures Runtime",
                state=futures_state,
                pid_count=1,
                last_heartbeat_age_seconds=futures_lag,
                status_reason="ok",
                source_mode="fixture",
            ),
        ],
    )


def _make_futures_snapshot(
    positions: list[FuturesPosition] | None = None,
    unrealized_pnl: float = 0.0,
) -> FuturesReadSnapshot:
    pos = positions or []
    return FuturesReadSnapshot(
        generated_at=_NOW,
        source_mode="fixture",
        summary=FuturesReadSummary(
            account_type="UNIFIED",
            positions_count=len(pos),
            protected_positions_count=sum(1 for p in pos if p.protection_status == "protected"),
            unrealized_pnl_total=unrealized_pnl,
        ),
        positions=pos,
        truncated=FuturesReadTruncation(),
    )


def _make_position(symbol: str = "BTCUSDT", side: str = "long", protection_status: str = "protected") -> FuturesPosition:
    return FuturesPosition(
        account_type="UNIFIED",
        symbol=symbol,
        side=side,
        position_idx=0,
        protection_status=protection_status,
        source_of_truth="db",
    )


def _make_models_snapshot(
    pipeline_state: str = "serving",
    active_declared_count: int = 1,
    recent_runs: list[TrainingRunSummary] | None = None,
    registry_entries: list[ModelRegistryEntry] | None = None,
) -> ModelsReadSnapshot:
    return ModelsReadSnapshot(
        generated_at=_NOW,
        source_mode="fixture",
        summary=ModelsSummary(
            pipeline_state=pipeline_state,
            active_declared_count=active_declared_count,
        ),
        recent_training_runs=recent_runs or [],
        registry_entries=registry_entries or [],
    )


def _make_reconciliation_snapshot(state: str = "healthy", drift_count: int = 0) -> ReconciliationSnapshot:
    return ReconciliationSnapshot(
        generated_at=_NOW,
        source_mode="fixture",
        state=state,
        drift_count=drift_count,
        last_run_at=_NOW,
        last_run_age_seconds=3600.0,
        next_run_in_seconds=3600,
    )


def _make_db_health_snapshot(state: str = "ok") -> DbHealthSnapshot:
    return DbHealthSnapshot(
        generated_at=_NOW,
        state=state,
        last_check_at=_NOW,
        latency_ms=1.0,
        db_path="/tmp/test.db",
        slow_threshold_ms=200,
    )


def _make_jobs(n: int = 3, state: str = "completed") -> list[JobSummary]:
    return [
        JobSummary(
            job_id=f"job-{i}",
            job_type="sample_data",
            state=JobState(state),
            updated_at=_NOW,
        )
        for i in range(n)
    ]


def _make_inputs(
    runtime: RuntimeStatusSnapshot | None = None,
    futures: FuturesReadSnapshot | None = None,
    models: ModelsReadSnapshot | None = None,
    reconciliation: ReconciliationSnapshot | None = None,
    db_health: DbHealthSnapshot | None = None,
    jobs: list[JobSummary] | None = None,
) -> HomeSummaryInputs:
    return HomeSummaryInputs(
        runtime=runtime or _make_runtime_snapshot(),
        futures=futures or _make_futures_snapshot(),
        models=models or _make_models_snapshot(),
        reconciliation=reconciliation or _make_reconciliation_snapshot(),
        db_health=db_health or _make_db_health_snapshot(),
        jobs=jobs if jobs is not None else _make_jobs(),
    )


# ---------------------------------------------------------------------------
# Stub service implementations
# ---------------------------------------------------------------------------

class _StubRuntimeSvc:
    def __init__(self, snap: RuntimeStatusSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> RuntimeStatusSnapshot:
        return self._snap


class _StubFuturesSvc:
    def __init__(self, snap: FuturesReadSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> FuturesReadSnapshot:
        return self._snap


class _StubModelsSvc:
    def __init__(self, snap: ModelsReadSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> ModelsReadSnapshot:
        return self._snap


class _StubReconciliationSvc:
    def __init__(self, snap: ReconciliationSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> ReconciliationSnapshot:
        return self._snap


class _StubDbHealthSvc:
    def __init__(self, snap: DbHealthSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> DbHealthSnapshot:
        return self._snap


class _StubJobManager:
    def __init__(self, jobs: list[JobSummary]) -> None:
        self._jobs = jobs

    def list_summaries(self) -> list[JobSummary]:
        return self._jobs


def _make_service(inputs: HomeSummaryInputs) -> HomeSummaryService:
    return HomeSummaryService(
        runtime_status_service=_StubRuntimeSvc(inputs.runtime),
        futures_read_service=_StubFuturesSvc(inputs.futures),
        models_read_service=_StubModelsSvc(inputs.models),
        reconciliation_read_service=_StubReconciliationSvc(inputs.reconciliation),
        db_health_service=_StubDbHealthSvc(inputs.db_health),
        job_manager=_StubJobManager(inputs.jobs),
    )


# ---------------------------------------------------------------------------
# Test 1: all healthy → state="healthy", score=100
# ---------------------------------------------------------------------------

def test_all_healthy_yields_healthy_state():
    inputs = _make_inputs()
    summary = _build_summary(inputs, generated_at=_NOW)

    global_block = summary.global_
    assert global_block.state == "healthy"
    assert global_block.health_score == 100
    assert global_block.critical_reason is None
    assert global_block.primary_action is None


# ---------------------------------------------------------------------------
# Test 2: unprotected position → critical, pause-trading
# ---------------------------------------------------------------------------

def test_unprotected_position_yields_critical():
    positions = [_make_position(protection_status="unprotected")]
    futures = _make_futures_snapshot(positions=positions)
    inputs = _make_inputs(futures=futures)
    summary = _build_summary(inputs, generated_at=_NOW)

    g = summary.global_
    assert g.state == "critical"
    assert g.health_score <= 70  # 100 - 30 = 70
    assert g.critical_reason is not None
    assert "position" in g.critical_reason.lower() or "без защиты" in g.critical_reason
    assert g.primary_action is not None
    assert g.primary_action.kind == "pause-trading"


# ---------------------------------------------------------------------------
# Test 3: reconciliation failed → critical, open-diagnostics (no unprotected)
# ---------------------------------------------------------------------------

def test_reconciliation_failed_yields_critical():
    reconciliation = _make_reconciliation_snapshot(state="failed")
    inputs = _make_inputs(reconciliation=reconciliation)
    summary = _build_summary(inputs, generated_at=_NOW)

    g = summary.global_
    assert g.state == "critical"
    assert g.primary_action is not None
    assert g.primary_action.kind == "open-diagnostics"
    assert g.critical_reason is not None
    assert "Reconciliation" in g.critical_reason


# ---------------------------------------------------------------------------
# Test 4: reconciliation stale → warning, score=85
# ---------------------------------------------------------------------------

def test_reconciliation_stale_yields_warning():
    reconciliation = _make_reconciliation_snapshot(state="stale")
    inputs = _make_inputs(reconciliation=reconciliation)
    summary = _build_summary(inputs, generated_at=_NOW)

    g = summary.global_
    assert g.state == "warning"
    assert g.health_score == 85
    assert g.primary_action is None


# ---------------------------------------------------------------------------
# Test 5: ml pipeline_state="error" → warning, score=85
# ---------------------------------------------------------------------------

def test_ml_error_yields_warning():
    models = _make_models_snapshot(pipeline_state="error")
    inputs = _make_inputs(models=models)
    summary = _build_summary(inputs, generated_at=_NOW)

    g = summary.global_
    assert g.state == "warning"
    assert g.health_score == 85


# ---------------------------------------------------------------------------
# Test 6: bybit and telegram always null
# ---------------------------------------------------------------------------

def test_bybit_and_telegram_remain_null():
    inputs = _make_inputs()
    summary = _build_summary(inputs, generated_at=_NOW)

    assert summary.connections.bybit is None
    assert summary.connections.telegram is None


# ---------------------------------------------------------------------------
# Test 7: health_score clamped at bounds
# ---------------------------------------------------------------------------

def test_health_score_bounds():
    # Multiple critical + warning conditions: score must never go negative.
    # 2 critical (unprotected + reconciliation_failed) = -60
    # 2 warning  (degraded runtime + ml_error)         = -30
    # total = 100 - 60 - 30 = 10  (not clamped here but bounded from below)
    positions = [
        _make_position(symbol="BTCUSDT", protection_status="unprotected"),
        _make_position(symbol="ETHUSDT", protection_status="failed"),
    ]
    futures = _make_futures_snapshot(positions=positions)
    reconciliation = _make_reconciliation_snapshot(state="failed")
    models = _make_models_snapshot(pipeline_state="error")
    runtime = _make_runtime_snapshot(spot_state="degraded")

    inputs = _make_inputs(
        futures=futures,
        reconciliation=reconciliation,
        models=models,
        runtime=runtime,
    )
    summary = _build_summary(inputs, generated_at=_NOW)

    # score is a non-negative integer
    assert summary.global_.health_score >= 0
    assert summary.global_.health_score == 10  # 100 - 2*30 - 2*15

    # Pure healthy → 100
    healthy_inputs = _make_inputs()
    healthy_summary = _build_summary(healthy_inputs, generated_at=_NOW)
    assert healthy_summary.global_.health_score == 100


# ---------------------------------------------------------------------------
# Test 8: positions capped at 8, but positions_total reflects all
# ---------------------------------------------------------------------------

def test_positions_capped_at_8():
    positions = [
        _make_position(symbol=f"TOKEN{i}USDT", protection_status="protected")
        for i in range(12)
    ]
    futures = _make_futures_snapshot(positions=positions)
    inputs = _make_inputs(futures=futures)
    summary = _build_summary(inputs, generated_at=_NOW)

    assert len(summary.risk.positions) == 8
    assert summary.risk.positions_total == 12


# ---------------------------------------------------------------------------
# Test 9: activity capped at 12
# ---------------------------------------------------------------------------

def test_activity_capped_at_12():
    jobs = _make_jobs(n=20)
    inputs = _make_inputs(jobs=jobs)
    summary = _build_summary(inputs, generated_at=_NOW)

    assert len(summary.activity) == 12


# ---------------------------------------------------------------------------
# Bonus: JSON serialisation uses "global" key (not "global_")
# ---------------------------------------------------------------------------

def test_json_output_uses_global_alias():
    inputs = _make_inputs()
    summary = _build_summary(inputs, generated_at=_NOW)
    data = summary.model_dump(by_alias=True)

    assert "global" in data
    assert "global_" not in data


# ---------------------------------------------------------------------------
# Bonus: service-level caching returns same object within TTL
# ---------------------------------------------------------------------------

def test_cache_returns_same_within_ttl():
    inputs = _make_inputs()
    service = _make_service(inputs)

    first = service.get_summary(now=_NOW)
    second = service.get_summary(now=_NOW)  # same now → within TTL
    assert first is second


def test_cache_refreshes_after_ttl():
    from datetime import timedelta
    inputs = _make_inputs()
    service = _make_service(inputs)

    first = service.get_summary(now=_NOW)
    later = _NOW + timedelta(seconds=2)
    second = service.get_summary(now=later)
    assert first is not second
