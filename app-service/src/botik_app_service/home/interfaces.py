"""Internal domain types for HomeSummaryService.

These are intermediate representations used only within the home module.
Public contract lives in contracts/home_summary.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from botik_app_service.contracts.db_health import DbHealthSnapshot
from botik_app_service.contracts.futures import FuturesReadSnapshot
from botik_app_service.contracts.models import ModelsReadSnapshot
from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.contracts.runtime_status import RuntimeStatusSnapshot
from botik_app_service.contracts.jobs import JobSummary


@dataclass(frozen=True)
class HomeSummaryInputs:
    """Bundle of all source snapshots needed to build HomeSummary."""

    runtime: RuntimeStatusSnapshot
    futures: FuturesReadSnapshot
    models: ModelsReadSnapshot
    reconciliation: ReconciliationSnapshot
    db_health: DbHealthSnapshot
    jobs: list[JobSummary] = field(default_factory=list)
