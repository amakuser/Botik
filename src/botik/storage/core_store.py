"""
Shared storage primitives for account snapshots, reconciliation and audit.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    cols = _table_columns(conn, table)
    if name in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def ensure_core_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT UNIQUE NOT NULL,
            reconciliation_run_id TEXT,
            account_type TEXT NOT NULL,
            snapshot_kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_account_snapshots_run ON account_snapshots(reconciliation_run_id);
        CREATE INDEX IF NOT EXISTS idx_account_snapshots_kind ON account_snapshots(snapshot_kind, created_at_utc);

        CREATE TABLE IF NOT EXISTS reconciliation_runs (
            reconciliation_run_id TEXT PRIMARY KEY,
            trigger_source TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            summary_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_started ON reconciliation_runs(started_at_utc);
        CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_status ON reconciliation_runs(status, started_at_utc);

        CREATE TABLE IF NOT EXISTS reconciliation_issues (
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
        CREATE INDEX IF NOT EXISTS idx_reconciliation_issues_run ON reconciliation_issues(reconciliation_run_id);
        CREATE INDEX IF NOT EXISTS idx_reconciliation_issues_open ON reconciliation_issues(status, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_reconciliation_issues_domain_symbol ON reconciliation_issues(domain, symbol);

        CREATE TABLE IF NOT EXISTS strategy_runs (
            strategy_run_id TEXT PRIMARY KEY,
            strategy_name TEXT NOT NULL,
            market_category TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            config_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_runs_started ON strategy_runs(started_at_utc);
        CREATE INDEX IF NOT EXISTS idx_strategy_runs_status ON strategy_runs(status, started_at_utc);

        CREATE TABLE IF NOT EXISTS events_audit (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            domain TEXT NOT NULL,
            symbol TEXT,
            ref_id TEXT,
            payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_audit_type ON events_audit(event_type, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_events_audit_domain ON events_audit(domain, symbol, created_at_utc);
        """
    )
    _ensure_column(conn, "reconciliation_runs", "summary_json", "TEXT")
    _ensure_column(conn, "strategy_runs", "config_json", "TEXT")
    conn.commit()


def start_reconciliation_run(
    conn: sqlite3.Connection,
    *,
    trigger_source: str,
    reconciliation_run_id: str | None = None,
    started_at_utc: str | None = None,
) -> str:
    run_id = str(reconciliation_run_id or f"recon-{uuid.uuid4().hex[:16]}")
    started = str(started_at_utc or utc_now_iso())
    conn.execute(
        """
        INSERT INTO reconciliation_runs (
            reconciliation_run_id,
            trigger_source,
            status,
            started_at_utc,
            finished_at_utc,
            summary_json
        ) VALUES (?, ?, ?, ?, NULL, NULL)
        """,
        (run_id, str(trigger_source), "running", started),
    )
    conn.commit()
    return run_id


def finish_reconciliation_run(
    conn: sqlite3.Connection,
    *,
    reconciliation_run_id: str,
    status: str,
    summary: dict[str, Any] | str | None = None,
    finished_at_utc: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE reconciliation_runs
        SET status=?, finished_at_utc=?, summary_json=?
        WHERE reconciliation_run_id=?
        """,
        (
            str(status),
            str(finished_at_utc or utc_now_iso()),
            _json_text(summary or {}),
            str(reconciliation_run_id),
        ),
    )
    conn.commit()


def insert_reconciliation_issue(
    conn: sqlite3.Connection,
    *,
    issue_type: str,
    domain: str,
    severity: str,
    details: dict[str, Any] | str,
    symbol: str | None = None,
    reconciliation_run_id: str | None = None,
    issue_id: str | None = None,
    status: str = "open",
) -> str:
    resolved_at_utc = utc_now_iso() if str(status).strip().lower() == "resolved" else None
    row_id = str(issue_id or f"issue-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO reconciliation_issues (
            issue_id,
            reconciliation_run_id,
            issue_type,
            domain,
            symbol,
            severity,
            details_json,
            status,
            created_at_utc,
            resolved_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            reconciliation_run_id,
            str(issue_type),
            str(domain),
            symbol,
            str(severity),
            _json_text(details),
            str(status),
            utc_now_iso(),
            resolved_at_utc,
        ),
    )
    conn.commit()
    return row_id


def resolve_reconciliation_issue(
    conn: sqlite3.Connection,
    *,
    issue_id: str,
    resolved_at_utc: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE reconciliation_issues
        SET status='resolved', resolved_at_utc=?
        WHERE issue_id=?
        """,
        (str(resolved_at_utc or utc_now_iso()), str(issue_id)),
    )
    conn.commit()


def insert_account_snapshot(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    snapshot_kind: str,
    payload: dict[str, Any] | str,
    reconciliation_run_id: str | None = None,
    snapshot_id: str | None = None,
    created_at_utc: str | None = None,
) -> str:
    row_id = str(snapshot_id or f"snap-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO account_snapshots (
            snapshot_id,
            reconciliation_run_id,
            account_type,
            snapshot_kind,
            payload_json,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            reconciliation_run_id,
            str(account_type),
            str(snapshot_kind),
            _json_text(payload),
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()
    return row_id


def upsert_strategy_run(
    conn: sqlite3.Connection,
    *,
    strategy_run_id: str,
    strategy_name: str,
    market_category: str,
    status: str,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    config_payload: dict[str, Any] | str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO strategy_runs (
            strategy_run_id,
            strategy_name,
            market_category,
            status,
            started_at_utc,
            finished_at_utc,
            config_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(strategy_run_id) DO UPDATE SET
            strategy_name=excluded.strategy_name,
            market_category=excluded.market_category,
            status=excluded.status,
            started_at_utc=excluded.started_at_utc,
            finished_at_utc=excluded.finished_at_utc,
            config_json=excluded.config_json
        """,
        (
            str(strategy_run_id),
            str(strategy_name),
            str(market_category),
            str(status),
            str(started_at_utc or utc_now_iso()),
            finished_at_utc,
            _json_text(config_payload or {}),
        ),
    )
    conn.commit()


def insert_event_audit(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    domain: str,
    payload: dict[str, Any] | str,
    symbol: str | None = None,
    ref_id: str | None = None,
    event_id: str | None = None,
    created_at_utc: str | None = None,
) -> str:
    row_id = str(event_id or f"evt-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO events_audit (
            event_id,
            event_type,
            domain,
            symbol,
            ref_id,
            payload_json,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            str(event_type),
            str(domain),
            symbol,
            ref_id,
            _json_text(payload),
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()
    return row_id
