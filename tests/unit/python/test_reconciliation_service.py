"""Unit tests for reconciliation_read service (pure derivation) and legacy adapter."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.reconciliation_read.interfaces import (
    RawReconciliationRead,
    RawReconciliationRun,
    ReconciliationRawResult,
)
from botik_app_service.reconciliation_read.service import derive_reconciliation_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)


def _run(
    status: str = "success",
    hours_ago: float = 1.0,
    run_id: str = "run-1",
) -> RawReconciliationRun:
    started = datetime(2026, 4, 26, tzinfo=timezone.utc)
    from datetime import timedelta
    started = _NOW - timedelta(hours=hours_ago)
    return RawReconciliationRun(
        run_id=run_id,
        trigger_source="scheduler",
        status=status,
        started_at_utc=started,
        finished_at_utc=started,
    )


def _raw(
    latest_run: RawReconciliationRun | None = None,
    open_issues: int = 0,
    table_exists: bool = True,
) -> RawReconciliationRead:
    return RawReconciliationRead(
        latest_run=latest_run,
        open_issue_count=open_issues,
        table_exists=table_exists,
    )


def _result(
    raw: RawReconciliationRead,
    interval_seconds: int | None = None,
) -> ReconciliationRawResult:
    return ReconciliationRawResult(raw=raw, interval_seconds=interval_seconds)


# ---------------------------------------------------------------------------
# State derivation table-driven
# ---------------------------------------------------------------------------

def test_state_healthy_success_no_issues():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success"), open_issues=0)),
        now=_NOW,
    )
    assert snap.state == "healthy"
    assert snap.drift_count == 0


def test_state_degraded_success_with_open_issues():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success"), open_issues=3)),
        now=_NOW,
    )
    assert snap.state == "degraded"
    assert snap.drift_count == 3
    assert any("3 open drift issues" in n for n in snap.notes)


def test_state_failed_latest_run_failed():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("failed"), open_issues=0)),
        now=_NOW,
    )
    assert snap.state == "failed"
    assert any("failed" in n for n in snap.notes)


def test_state_stale_run_30h_ago_threshold_24h(monkeypatch):
    monkeypatch.setenv("BOTIK_RECONCILIATION_STALE_HOURS", "24")
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success", hours_ago=30.0), open_issues=0)),
        now=_NOW,
    )
    assert snap.state == "stale"
    assert any("30.0 hours old" in n for n in snap.notes)


def test_state_unsupported_no_rows_in_table():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=None, table_exists=True)),
        now=_NOW,
    )
    assert snap.state == "unsupported"
    assert any("no runs recorded" in n for n in snap.notes)


def test_state_unsupported_missing_table():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=None, table_exists=False)),
        now=_NOW,
    )
    assert snap.state == "unsupported"
    assert any("no reconciliation_runs table" in n for n in snap.notes)


# ---------------------------------------------------------------------------
# last_run_age_seconds uses injected now
# ---------------------------------------------------------------------------

def test_last_run_age_seconds_computed_correctly():
    from datetime import timedelta
    started = _NOW - timedelta(seconds=3600)
    run = RawReconciliationRun(
        run_id="r",
        trigger_source="manual",
        status="success",
        started_at_utc=started,
        finished_at_utc=started,
    )
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=run)),
        now=_NOW,
    )
    assert snap.last_run_age_seconds == pytest.approx(3600.0, abs=1.0)


# ---------------------------------------------------------------------------
# next_run_in_seconds
# ---------------------------------------------------------------------------

def test_next_run_in_seconds_honors_interval():
    from datetime import timedelta
    started = _NOW - timedelta(seconds=300)  # 5 min ago
    run = RawReconciliationRun(
        run_id="r",
        trigger_source="scheduler",
        status="success",
        started_at_utc=started,
        finished_at_utc=started,
    )
    # interval=600s, age=300s → next=300s
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=run), interval_seconds=600),
        now=_NOW,
    )
    assert snap.next_run_in_seconds == 300


def test_next_run_in_seconds_clamped_at_zero():
    from datetime import timedelta
    # Run started 1000s ago, interval=600 → remaining < 0 → clamp to 0
    started = _NOW - timedelta(seconds=1000)
    run = RawReconciliationRun(
        run_id="r",
        trigger_source="scheduler",
        status="success",
        started_at_utc=started,
        finished_at_utc=started,
    )
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=run), interval_seconds=600),
        now=_NOW,
    )
    assert snap.next_run_in_seconds == 0


def test_next_run_in_seconds_null_when_not_configured():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success")), interval_seconds=None),
        now=_NOW,
    )
    assert snap.next_run_in_seconds is None
    assert any("not configured" in n for n in snap.notes)


# ---------------------------------------------------------------------------
# drift_count
# ---------------------------------------------------------------------------

def test_drift_count_matches_open_issues():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success"), open_issues=7)),
        now=_NOW,
    )
    assert snap.drift_count == 7


# ---------------------------------------------------------------------------
# notes populated for non-healthy cases
# ---------------------------------------------------------------------------

def test_notes_populated_for_stale(monkeypatch):
    monkeypatch.setenv("BOTIK_RECONCILIATION_STALE_HOURS", "24")
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("success", hours_ago=25.0))),
        now=_NOW,
    )
    assert snap.state == "stale"
    assert len(snap.notes) > 0


def test_notes_populated_for_failed():
    snap = derive_reconciliation_snapshot(
        _result(_raw(latest_run=_run("failed"))),
        now=_NOW,
    )
    assert len(snap.notes) > 0


# ---------------------------------------------------------------------------
# Legacy adapter — real temp SQLite
# ---------------------------------------------------------------------------

def _create_reconciliation_db(path: Path, *, with_run: bool = True, run_status: str = "success", open_issues: int = 0) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE reconciliation_runs (
                reconciliation_run_id TEXT PRIMARY KEY,
                trigger_source TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                summary_json TEXT
            );
            CREATE TABLE reconciliation_issues (
                issue_id TEXT PRIMARY KEY,
                reconciliation_run_id TEXT,
                issue_type TEXT NOT NULL,
                domain TEXT NOT NULL,
                symbol TEXT,
                severity TEXT NOT NULL,
                details_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at_utc TEXT NOT NULL,
                resolved_at_utc TEXT
            );
            """
        )
        if with_run:
            conn.execute(
                """
                INSERT INTO reconciliation_runs
                (reconciliation_run_id, trigger_source, status, started_at_utc, finished_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("run-1", "scheduler", run_status, "2026-04-26T11:00:00Z", "2026-04-26T11:00:30Z"),
            )
            for i in range(open_issues):
                conn.execute(
                    """
                    INSERT INTO reconciliation_issues
                    (issue_id, reconciliation_run_id, issue_type, domain, symbol, severity, details_json, status, created_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (f"issue-{i}", "run-1", "drift", "spot", "BTCUSDT", "low", "{}", "open", "2026-04-26T11:00:31Z"),
                )
        conn.commit()
    finally:
        conn.close()


def test_adapter_healthy(tmp_path: Path):
    db = tmp_path / "botik.db"
    _create_reconciliation_db(db, with_run=True, run_status="success", open_issues=0)

    from botik_app_service.reconciliation_read.legacy_adapter import LegacyReconciliationReadAdapter
    adapter = LegacyReconciliationReadAdapter(repo_root=REPO_ROOT)
    snap = adapter.read_snapshot(db_path=db)

    # Run is recent so not stale; no open issues
    assert snap.state in ("healthy", "stale")  # depends on threshold vs fixture time
    assert snap.last_run_status == "success"
    assert snap.drift_count == 0


def test_adapter_degraded_with_open_issues(tmp_path: Path):
    db = tmp_path / "botik.db"
    _create_reconciliation_db(db, with_run=True, run_status="success", open_issues=2)

    from botik_app_service.reconciliation_read.legacy_adapter import LegacyReconciliationReadAdapter
    adapter = LegacyReconciliationReadAdapter(repo_root=REPO_ROOT)
    snap = adapter.read_snapshot(db_path=db)

    assert snap.drift_count == 2


def test_adapter_unsupported_missing_table(tmp_path: Path):
    db = tmp_path / "botik.db"
    # Create an empty SQLite with no tables
    sqlite3.connect(db).close()

    from botik_app_service.reconciliation_read.legacy_adapter import LegacyReconciliationReadAdapter
    adapter = LegacyReconciliationReadAdapter(repo_root=REPO_ROOT)
    snap = adapter.read_snapshot(db_path=db)

    assert snap.state == "unsupported"


def test_adapter_unsupported_db_missing(tmp_path: Path):
    db = tmp_path / "does_not_exist.db"

    from botik_app_service.reconciliation_read.legacy_adapter import LegacyReconciliationReadAdapter
    adapter = LegacyReconciliationReadAdapter(repo_root=REPO_ROOT)
    snap = adapter.read_snapshot(db_path=db)

    assert snap.state == "unsupported"


# Need pytest for approx
import pytest
