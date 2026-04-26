"""Unit tests for db_health service — real temp SQLite files, no mocking."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.db_health.service import DbHealthService, _probe_db


def _make_service(repo_root: Path) -> DbHealthService:
    return DbHealthService(repo_root=repo_root)


def test_probe_ok_against_real_db(tmp_path: Path):
    db = tmp_path / "test.db"
    sqlite3.connect(db).close()  # create empty valid DB

    result = _probe_db(db)

    assert result.success is True
    assert result.latency_ms is not None
    assert result.latency_ms >= 0.0
    assert result.error is None
    assert result.db_path == str(db)
    assert result.probed_at is not None


def test_probe_unavailable_missing_path(tmp_path: Path):
    db = tmp_path / "no_such.db"

    result = _probe_db(db)

    assert result.success is False
    assert result.latency_ms is None
    assert result.error is not None
    # error message must be sanitized: class + short message, no gigantic tracebacks
    assert len(result.error) <= 300


def test_probe_unavailable_corrupt_db(tmp_path: Path):
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"this is not a sqlite database at all, garbage garbage garbage")

    result = _probe_db(db)

    assert result.success is False
    assert result.error is not None


def test_snapshot_ok_state(tmp_path: Path, monkeypatch):
    db = tmp_path / "test.db"
    sqlite3.connect(db).close()

    # patch threshold to 9999ms so any real probe is under threshold
    monkeypatch.setenv("BOTIK_DB_HEALTH_SLOW_MS", "9999")

    # We need a service that probes our tmp db, not the real one.
    # Patch resolve_db_path via monkeypatching env isn't viable here — use the
    # probe function directly and verify the full snapshot contract via service.
    # Instead, subclass the service to inject db_path:
    from botik_app_service.db_health import service as _svc_mod

    original_resolve = _svc_mod.resolve_db_path

    def _mock_resolve(repo_root, cfg=None):
        return db

    monkeypatch.setattr(_svc_mod, "resolve_db_path", _mock_resolve)

    service = DbHealthService(repo_root=REPO_ROOT)
    snap = service.snapshot()

    assert snap.state == "ok"
    assert snap.latency_ms is not None
    assert snap.latency_ms >= 0.0
    assert snap.error is None
    assert snap.db_path == str(db)
    assert snap.slow_threshold_ms == 9999
    assert snap.last_check_at is not None


def test_snapshot_unavailable_missing_db(tmp_path: Path, monkeypatch):
    db = tmp_path / "missing.db"

    from botik_app_service.db_health import service as _svc_mod

    def _mock_resolve(repo_root, cfg=None):
        return db

    monkeypatch.setattr(_svc_mod, "resolve_db_path", _mock_resolve)

    service = DbHealthService(repo_root=REPO_ROOT)
    snap = service.snapshot()

    assert snap.state == "unavailable"
    assert snap.error is not None
    assert snap.latency_ms is None


def test_snapshot_unavailable_corrupt_db(tmp_path: Path, monkeypatch):
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"garbage data not sqlite")

    from botik_app_service.db_health import service as _svc_mod

    def _mock_resolve(repo_root, cfg=None):
        return db

    monkeypatch.setattr(_svc_mod, "resolve_db_path", _mock_resolve)

    service = DbHealthService(repo_root=REPO_ROOT)
    snap = service.snapshot()

    assert snap.state == "unavailable"
    assert snap.error is not None


def test_snapshot_degraded_above_threshold(tmp_path: Path, monkeypatch):
    """Simulate slow probe by setting threshold to 0ms."""
    db = tmp_path / "test.db"
    sqlite3.connect(db).close()

    monkeypatch.setenv("BOTIK_DB_HEALTH_SLOW_MS", "0")

    from botik_app_service.db_health import service as _svc_mod

    def _mock_resolve(repo_root, cfg=None):
        return db

    monkeypatch.setattr(_svc_mod, "resolve_db_path", _mock_resolve)

    service = DbHealthService(repo_root=REPO_ROOT)
    snap = service.snapshot()

    # Any real latency will be > 0ms, so state must be degraded
    assert snap.state == "degraded"
    assert snap.latency_ms is not None
    assert snap.slow_threshold_ms == 0


def test_snapshot_fields_populated(tmp_path: Path, monkeypatch):
    db = tmp_path / "test.db"
    sqlite3.connect(db).close()

    monkeypatch.setenv("BOTIK_DB_HEALTH_SLOW_MS", "9999")

    from botik_app_service.db_health import service as _svc_mod

    def _mock_resolve(repo_root, cfg=None):
        return db

    monkeypatch.setattr(_svc_mod, "resolve_db_path", _mock_resolve)

    service = DbHealthService(repo_root=REPO_ROOT)
    snap = service.snapshot()

    assert snap.db_path == str(db)
    assert snap.slow_threshold_ms == 9999
    assert snap.last_check_at is not None
    assert snap.generated_at is not None
