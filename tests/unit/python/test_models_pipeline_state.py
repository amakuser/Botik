"""Tests for ModelsSummary.pipeline_state normalization."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

import pytest
from botik_app_service.models_read.legacy_adapter import _derive_pipeline_state
from botik_app_service.models_read.service import ModelsReadService


# ---------------------------------------------------------------------------
# Table-driven mapping tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,ready_scopes,expected",
    [
        ("running", 0, "training"),
        ("running", 2, "training"),
        ("completed", 2, "serving"),
        ("completed", 0, "idle"),
        ("failed", 0, "error"),
        ("failed", 1, "error"),
        ("not available", 0, "idle"),
        ("not available", 2, "idle"),
        ("pending", 0, "unknown"),
        ("", 0, "unknown"),
        ("RUNNING", 0, "training"),   # case-insensitive
        ("Completed", 1, "serving"),  # case-insensitive
    ],
)
def test_derive_pipeline_state(status: str, ready_scopes: int, expected: str):
    assert _derive_pipeline_state(status, ready_scopes) == expected


# ---------------------------------------------------------------------------
# Integration: raw status preserved alongside pipeline_state
# ---------------------------------------------------------------------------

def _create_db_with_run(path: Path, status: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT UNIQUE NOT NULL,
                path_or_payload TEXT,
                metrics_json TEXT,
                created_at_utc TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            );
            CREATE TABLE ml_training_runs (
                run_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                model_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                epoch INTEGER,
                max_epochs INTEGER,
                loss REAL,
                accuracy REAL,
                sharpe_ratio REAL,
                trade_count INTEGER,
                is_trained INTEGER NOT NULL DEFAULT 0,
                trained_at_utc TEXT,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                notes TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO ml_training_runs
            (run_id, model_scope, model_version, mode, status, is_trained, started_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-1", "spot", "spot-v1", "offline", status, 0, "2026-04-26T10:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def test_raw_status_preserved_alongside_pipeline_state(tmp_path: Path):
    db = tmp_path / "models.db"
    _create_db_with_run(db, "running")

    service = ModelsReadService(repo_root=REPO_ROOT, fixture_db_path=db)
    snap = service.snapshot()

    assert snap.summary.latest_run_status == "running"
    assert snap.summary.pipeline_state == "training"


def test_pipeline_state_serving_when_completed_and_ready(tmp_path: Path):
    db = tmp_path / "models.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT UNIQUE NOT NULL,
                path_or_payload TEXT,
                metrics_json TEXT,
                created_at_utc TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            );
            CREATE TABLE ml_training_runs (
                run_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                model_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                epoch INTEGER,
                max_epochs INTEGER,
                loss REAL,
                accuracy REAL,
                sharpe_ratio REAL,
                trade_count INTEGER,
                is_trained INTEGER NOT NULL DEFAULT 0,
                trained_at_utc TEXT,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                notes TEXT
            );
            """
        )
        # Insert a ready model registry entry
        conn.execute(
            """
            INSERT INTO model_registry (model_id, path_or_payload, metrics_json, created_at_utc, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "spot-v1",
                "data/models/spot-v1.pkl",
                '{"instrument":"spot","policy":"hybrid","status":"ready","quality_score":0.8}',
                "2026-04-26T09:00:00Z",
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO ml_training_runs
            (run_id, model_scope, model_version, mode, status, is_trained, started_at_utc, finished_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-1", "spot", "spot-v1", "offline", "completed", 1, "2026-04-26T08:00:00Z", "2026-04-26T09:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()

    manifest = tmp_path / "active_models.fixture.yaml"
    manifest.write_text(
        "active_spot_model: spot-v1\nactive_futures_model: unknown\n", encoding="utf-8"
    )

    service = ModelsReadService(repo_root=REPO_ROOT, fixture_db_path=db, manifest_path=manifest)
    snap = service.snapshot()

    assert snap.summary.latest_run_status == "completed"
    assert snap.summary.pipeline_state == "serving"
    # ready_scopes >= 1 (spot is active)
    assert snap.summary.ready_scopes >= 1


def test_pipeline_state_error_when_failed(tmp_path: Path):
    db = tmp_path / "models.db"
    _create_db_with_run(db, "failed")

    service = ModelsReadService(repo_root=REPO_ROOT, fixture_db_path=db)
    snap = service.snapshot()

    assert snap.summary.latest_run_status == "failed"
    assert snap.summary.pipeline_state == "error"


def test_pipeline_state_idle_when_no_runs(tmp_path: Path):
    db = tmp_path / "models.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT UNIQUE NOT NULL,
                path_or_payload TEXT,
                metrics_json TEXT,
                created_at_utc TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            );
            CREATE TABLE ml_training_runs (
                run_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                model_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                is_trained INTEGER NOT NULL DEFAULT 0,
                started_at_utc TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    service = ModelsReadService(repo_root=REPO_ROOT, fixture_db_path=db)
    snap = service.snapshot()

    assert snap.summary.latest_run_status == "not available"
    assert snap.summary.pipeline_state == "idle"
