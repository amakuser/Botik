from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from botik_app_service.contracts.reconciliation import ReconciliationSnapshot, ReconciliationState
from botik_app_service.reconciliation_read.interfaces import ReconciliationRawResult


def _staleness_threshold_hours() -> int:
    try:
        return int(os.environ.get("BOTIK_RECONCILIATION_STALE_HOURS", "24"))
    except (ValueError, TypeError):
        return 24


def derive_reconciliation_snapshot(
    result: ReconciliationRawResult,
    *,
    now: datetime | None = None,
    source_mode: Literal["resolved", "fixture"] = "resolved",
) -> ReconciliationSnapshot:
    """Pure derivation — no I/O. Accepts injected `now` for deterministic tests."""
    if now is None:
        now = datetime.now(timezone.utc)

    raw = result.raw
    threshold_hours = _staleness_threshold_hours()
    notes: list[str] = []

    # Case: table doesn't exist (paper-mode dev DB or first boot)
    if not raw.table_exists:
        notes.append("no reconciliation_runs table yet")
        return ReconciliationSnapshot(
            generated_at=now,
            source_mode=source_mode,
            state="unsupported",
            drift_count=0,
            staleness_threshold_hours=threshold_hours,
            notes=notes,
        )

    # Case: table exists but is empty
    if raw.latest_run is None:
        notes.append("reconciliation_runs table exists but no runs recorded")
        return ReconciliationSnapshot(
            generated_at=now,
            source_mode=source_mode,
            state="unsupported",
            drift_count=0,
            staleness_threshold_hours=threshold_hours,
            notes=notes,
        )

    run = raw.latest_run

    # Ensure started_at is tz-aware for arithmetic
    started_at = run.started_at_utc
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    finished_at = run.finished_at_utc
    if finished_at is not None and finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)

    age_seconds = (now - started_at).total_seconds()
    drift_count = raw.open_issue_count

    # Compute next_run_in_seconds
    next_run_in_seconds: int | None = None
    if result.interval_seconds is not None:
        remaining = result.interval_seconds - int(age_seconds)
        next_run_in_seconds = max(0, remaining)
    else:
        notes.append("reconciliation interval not configured — next_run_in_seconds unavailable")

    # Derive state (priority: failed > stale > degraded > healthy)
    state: ReconciliationState
    if run.status == "failed":
        state = "failed"
        notes.append(f"latest run failed (run_id={run.run_id})")
    elif age_seconds > threshold_hours * 3600:
        state = "stale"
        hours_old = age_seconds / 3600
        notes.append(f"latest run is {hours_old:.1f} hours old (threshold {threshold_hours}h)")
    elif drift_count > 0:
        state = "degraded"
        notes.append(f"{drift_count} open drift issue{'s' if drift_count != 1 else ''}")
    else:
        state = "healthy"

    return ReconciliationSnapshot(
        generated_at=now,
        source_mode=source_mode,
        state=state,
        last_run_at=started_at,
        last_run_finished_at=finished_at,
        last_run_status=run.status,
        last_run_age_seconds=age_seconds,
        next_run_in_seconds=next_run_in_seconds,
        drift_count=drift_count,
        staleness_threshold_hours=threshold_hours,
        notes=notes,
    )
