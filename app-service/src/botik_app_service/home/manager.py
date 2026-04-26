"""Construction helper for HomeSummaryService.

Mirrors the pattern used by reconciliation_read/manager.py —
accepts all dependency services and returns a ready HomeSummaryService instance.
"""
from __future__ import annotations

from botik_app_service.home.service import HomeSummaryService


def build_home_summary_service(
    *,
    runtime_status_service,
    futures_read_service,
    models_read_service,
    reconciliation_read_service,
    db_health_service,
    job_manager,
) -> HomeSummaryService:
    return HomeSummaryService(
        runtime_status_service=runtime_status_service,
        futures_read_service=futures_read_service,
        models_read_service=models_read_service,
        reconciliation_read_service=reconciliation_read_service,
        db_health_service=db_health_service,
        job_manager=job_manager,
    )
