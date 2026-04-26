"""HomeSummaryService — pure composition over existing read services.

Reads data from in-process services via injected snapshots.
Applies derivation rules for global.state, health_score, etc.
Caches result for 1 second to avoid redundant snapshot calls.
"""
from __future__ import annotations

from datetime import datetime, timezone

from botik_app_service.contracts.db_health import DbHealthSnapshot
from botik_app_service.contracts.futures import FuturesPosition, FuturesReadSnapshot
from botik_app_service.contracts.home_summary import (
    ActiveModel,
    ActivityEntry,
    ConnectionsBlock,
    GlobalBlock,
    HomeSummary,
    LastTrainingRun,
    MLBlock,
    PositionEntry,
    PrimaryAction,
    ReconciliationBlock,
    RiskBlock,
    RiskByState,
    TodayPnL,
    TradingBlock,
    TradingRuntimeBlock,
)
from botik_app_service.contracts.jobs import JobSummary
from botik_app_service.contracts.models import ModelsReadSnapshot
from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.contracts.runtime_status import RuntimeStatusSnapshot
from botik_app_service.home.interfaces import HomeSummaryInputs

_TTL_SECONDS = 1.0

# Job states that map to severity levels
_FAILED_STATES = {"failed", "error"}
_WARN_STATES = {"cancelled", "orphaned"}


class HomeSummaryService:
    def __init__(
        self,
        runtime_status_service,
        futures_read_service,
        models_read_service,
        reconciliation_read_service,
        db_health_service,
        job_manager,
    ) -> None:
        self._runtime_svc = runtime_status_service
        self._futures_svc = futures_read_service
        self._models_svc = models_read_service
        self._reconciliation_svc = reconciliation_read_service
        self._db_health_svc = db_health_service
        self._job_manager = job_manager
        self._cached: tuple[datetime, HomeSummary] | None = None

    def get_summary(self, now: datetime | None = None) -> HomeSummary:
        resolved_now = now or datetime.now(timezone.utc)
        if self._cached is not None:
            cached_at, cached_snap = self._cached
            if (resolved_now - cached_at).total_seconds() < _TTL_SECONDS:
                return cached_snap

        inputs = self._collect_inputs()
        snap = _build_summary(inputs, generated_at=resolved_now)
        self._cached = (resolved_now, snap)
        return snap

    def _collect_inputs(self) -> HomeSummaryInputs:
        runtime: RuntimeStatusSnapshot = self._runtime_svc.snapshot()
        futures: FuturesReadSnapshot = self._futures_svc.snapshot()
        models: ModelsReadSnapshot = self._models_svc.snapshot()
        reconciliation: ReconciliationSnapshot = self._reconciliation_svc.snapshot()
        db_health: DbHealthSnapshot = self._db_health_svc.snapshot()
        jobs: list[JobSummary] = self._job_manager.list_summaries()
        return HomeSummaryInputs(
            runtime=runtime,
            futures=futures,
            models=models,
            reconciliation=reconciliation,
            db_health=db_health,
            jobs=jobs,
        )


# ---------------------------------------------------------------------------
# Pure derivation functions — all testable without the service wrapper
# ---------------------------------------------------------------------------

def _build_summary(inputs: HomeSummaryInputs, generated_at: datetime) -> HomeSummary:
    trading = _build_trading(inputs.runtime, inputs.futures)
    risk = _build_risk(inputs.futures)
    reconciliation = _build_reconciliation(inputs.reconciliation)
    ml = _build_ml(inputs.models)
    connections = _build_connections(inputs.db_health)
    activity = _build_activity(inputs.jobs)

    global_block = _derive_global(risk, reconciliation, trading, ml)

    return HomeSummary.model_construct(
        **{
            "generated_at": generated_at,
            "global": global_block,
            "trading": trading,
            "risk": risk,
            "reconciliation": reconciliation,
            "ml": ml,
            "connections": connections,
            "activity": activity,
        }
    )


def _build_trading(runtime: RuntimeStatusSnapshot, futures: FuturesReadSnapshot) -> TradingBlock:
    spot_block = TradingRuntimeBlock(state="unknown", lag_seconds=None)
    futures_block = TradingRuntimeBlock(state="unknown", lag_seconds=None)

    for rt in runtime.runtimes:
        block = TradingRuntimeBlock(
            state=rt.state,
            lag_seconds=rt.last_heartbeat_age_seconds,
        )
        if rt.runtime_id == "spot":
            spot_block = block
        elif rt.runtime_id == "futures":
            futures_block = block

    today_pnl: TodayPnL | None = None
    pnl_value = futures.summary.unrealized_pnl_total
    if pnl_value is not None:
        if pnl_value > 0:
            trend = "up"
        elif pnl_value < 0:
            trend = "down"
        else:
            trend = "flat"
        today_pnl = TodayPnL(value=pnl_value, currency="USDT", trend=trend)

    return TradingBlock(
        spot=spot_block,
        futures=futures_block,
        today_pnl=today_pnl,
        today_pnl_series=None,
    )


def _build_risk(futures: FuturesReadSnapshot) -> RiskBlock:
    positions = futures.positions
    total = len(positions)

    by_state = RiskByState()
    counts: dict[str, int] = {}
    for pos in positions:
        status = pos.protection_status
        counts[status] = counts.get(status, 0) + 1

    by_state = RiskByState(
        protected=counts.get("protected", 0),
        pending=counts.get("pending", 0),
        unprotected=counts.get("unprotected", 0),
        repairing=counts.get("repairing", 0),
        failed=counts.get("failed", 0),
    )

    capped = positions[:8]
    entries = [
        PositionEntry(
            id=f"{p.symbol}-{p.side}",
            symbol=p.symbol,
            side=p.side,
            protection_state=p.protection_status,
        )
        for p in capped
    ]

    return RiskBlock(positions_total=total, by_state=by_state, positions=entries)


def _build_reconciliation(snap: ReconciliationSnapshot) -> ReconciliationBlock:
    return ReconciliationBlock(
        state=snap.state,
        last_run_at=snap.last_run_at,
        last_run_age_seconds=snap.last_run_age_seconds,
        next_run_in_seconds=snap.next_run_in_seconds,
        drift_count=snap.drift_count,
    )


def _build_ml(snap: ModelsReadSnapshot) -> MLBlock:
    pipeline_state = snap.summary.pipeline_state

    active_model: ActiveModel | None = None
    if snap.summary.active_declared_count > 0:
        # Find the first registry entry declared as active
        for entry in snap.registry_entries:
            if entry.is_declared_active:
                trained_at: datetime | None = None
                # created_at_utc is a string in the contract — parse if non-empty
                raw_ts = entry.created_at_utc
                if raw_ts and raw_ts not in ("not available", ""):
                    try:
                        from datetime import datetime as _dt
                        trained_at = _dt.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except ValueError:
                        trained_at = None
                active_model = ActiveModel(
                    version=entry.model_id,
                    accuracy=entry.quality_score,
                    trained_at=trained_at,
                )
                break

    last_training_run: LastTrainingRun | None = None
    if snap.recent_training_runs:
        run = snap.recent_training_runs[0]
        ended_at: datetime | None = None
        raw_finished = run.finished_at_utc
        if raw_finished and raw_finished not in ("not available", ""):
            try:
                from datetime import datetime as _dt
                ended_at = _dt.fromisoformat(raw_finished.replace("Z", "+00:00"))
            except ValueError:
                ended_at = None
        last_training_run = LastTrainingRun(
            scope=str(run.scope),
            ended_at=ended_at,
            status=run.status,
        )

    return MLBlock(
        pipeline_state=pipeline_state,
        active_model=active_model,
        last_training_run=last_training_run,
    )


def _build_connections(db_health: DbHealthSnapshot) -> ConnectionsBlock:
    return ConnectionsBlock(
        bybit=None,
        telegram=None,
        database=db_health.state,
    )


def _build_activity(jobs: list[JobSummary]) -> list[ActivityEntry]:
    # Sort by updated_at descending, take latest 12
    sorted_jobs = sorted(jobs, key=lambda j: j.updated_at, reverse=True)[:12]
    entries: list[ActivityEntry] = []
    for job in sorted_jobs:
        state_str = job.state.value if hasattr(job.state, "value") else str(job.state)
        summary = f"{job.job_type} {state_str}"

        if state_str in _FAILED_STATES:
            severity = "err"
        elif state_str in _WARN_STATES:
            severity = "warn"
        else:
            severity = "info"

        entries.append(ActivityEntry(ts=job.updated_at, summary=summary, severity=severity))
    return entries


def _derive_global(
    risk: RiskBlock,
    reconciliation: ReconciliationBlock,
    trading: TradingBlock,
    ml: MLBlock,
) -> GlobalBlock:
    # --- Detect conditions ---
    has_unprotected_positions = (
        risk.by_state.unprotected > 0 or risk.by_state.failed > 0
    )
    reconciliation_failed = reconciliation.state == "failed"

    runtime_degraded = (
        trading.spot.state == "degraded" or trading.futures.state == "degraded"
    )
    reconciliation_stale = reconciliation.state == "stale"
    ml_error = ml.pipeline_state == "error"

    # --- Determine state ---
    critical_conditions: list[bool] = [has_unprotected_positions, reconciliation_failed]
    warning_conditions: list[bool] = [runtime_degraded, reconciliation_stale, ml_error]

    critical_count = sum(critical_conditions)
    warning_count = sum(warning_conditions)

    if critical_count > 0:
        state = "critical"
    elif warning_count > 0:
        state = "warning"
    else:
        state = "healthy"

    # --- Health score ---
    score = 100 - critical_count * 30 - warning_count * 15
    score = max(0, min(100, score))

    # --- Critical reason ---
    critical_reason: str | None = None
    if state == "critical":
        reasons: list[str] = []
        if has_unprotected_positions:
            unprotected_total = risk.by_state.unprotected + risk.by_state.failed
            reasons.append(f"{unprotected_total} positions без защиты")
        if reconciliation_failed:
            reasons.append("Reconciliation failed")
        critical_reason = "; ".join(reasons)

    # --- Primary action ---
    primary_action: PrimaryAction | None = None
    if state == "critical":
        if has_unprotected_positions:
            primary_action = PrimaryAction(label="Pause Trading", kind="pause-trading")
        else:
            primary_action = PrimaryAction(label="Open Diagnostics", kind="open-diagnostics")

    return GlobalBlock(
        state=state,
        health_score=score,
        critical_reason=critical_reason,
        primary_action=primary_action,
    )
