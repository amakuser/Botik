from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawReconciliationRun:
    run_id: str
    trigger_source: str
    status: str  # "success" | "failed"
    started_at_utc: datetime
    finished_at_utc: datetime | None


@dataclass
class RawReconciliationRead:
    """Raw data returned by the adapter — no derivation yet."""
    latest_run: RawReconciliationRun | None
    open_issue_count: int
    table_exists: bool


@dataclass
class ReconciliationRawResult:
    """Everything the service needs to produce a snapshot."""
    raw: RawReconciliationRead
    interval_seconds: int | None  # from config; None if not configured
