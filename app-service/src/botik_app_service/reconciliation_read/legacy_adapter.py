from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.infra.legacy_helpers import load_config, resolve_db_path
from botik_app_service.reconciliation_read.interfaces import (
    RawReconciliationRead,
    RawReconciliationRun,
    ReconciliationRawResult,
)
from botik_app_service.reconciliation_read.service import derive_reconciliation_snapshot


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class LegacyReconciliationReadAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(self, *, db_path: Path | None = None) -> ReconciliationSnapshot:
        resolved_db_path = db_path or self._resolve_db_path()
        cfg = load_config(self._repo_root)
        interval_seconds = self._read_interval(cfg)
        raw = self._read_raw(resolved_db_path)
        result = ReconciliationRawResult(raw=raw, interval_seconds=interval_seconds)
        return derive_reconciliation_snapshot(result, source_mode="resolved")

    def _resolve_db_path(self) -> Path:
        cfg = load_config(self._repo_root)
        return resolve_db_path(self._repo_root, cfg)

    @staticmethod
    def _read_interval(cfg: dict) -> int | None:
        try:
            value = cfg.get("strategy", {}).get("reconciliation_interval_sec")
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _read_raw(db_path: Path) -> RawReconciliationRead:
        if not db_path.exists():
            return RawReconciliationRead(latest_run=None, open_issue_count=0, table_exists=False)

        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2) as conn:
                conn.row_factory = sqlite3.Row

                # Check if table exists
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reconciliation_runs' LIMIT 1"
                ).fetchone()
                if row is None:
                    return RawReconciliationRead(latest_run=None, open_issue_count=0, table_exists=False)

                # Read latest run
                run_row = conn.execute(
                    """
                    SELECT reconciliation_run_id, trigger_source, status,
                           started_at_utc, finished_at_utc
                    FROM reconciliation_runs
                    ORDER BY started_at_utc DESC, reconciliation_run_id DESC
                    LIMIT 1
                    """
                ).fetchone()

                latest_run: RawReconciliationRun | None = None
                if run_row is not None:
                    latest_run = RawReconciliationRun(
                        run_id=str(run_row["reconciliation_run_id"] or ""),
                        trigger_source=str(run_row["trigger_source"] or ""),
                        status=str(run_row["status"] or ""),
                        started_at_utc=_parse_utc(run_row["started_at_utc"]) or datetime.now(timezone.utc),
                        finished_at_utc=_parse_utc(run_row["finished_at_utc"]),
                    )

                # Count open issues (table may or may not exist)
                open_count = 0
                issues_row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reconciliation_issues' LIMIT 1"
                ).fetchone()
                if issues_row is not None:
                    count_row = conn.execute(
                        "SELECT COUNT(*) FROM reconciliation_issues WHERE status='open'"
                    ).fetchone()
                    open_count = int(count_row[0] or 0)

                return RawReconciliationRead(
                    latest_run=latest_run,
                    open_issue_count=open_count,
                    table_exists=True,
                )
        except sqlite3.Error:
            # DB is unreadable — treat as unsupported rather than crashing
            return RawReconciliationRead(latest_run=None, open_issue_count=0, table_exists=False)
