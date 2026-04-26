from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from botik_app_service.contracts.db_health import DbHealthSnapshot, DbHealthState
from botik_app_service.db_health.interfaces import DbProbeResult
from botik_app_service.infra.legacy_helpers import load_config, resolve_db_path


def _slow_threshold_ms() -> int:
    try:
        return int(os.environ.get("BOTIK_DB_HEALTH_SLOW_MS", "200"))
    except (ValueError, TypeError):
        return 200


def _probe_db(db_path: Path) -> DbProbeResult:
    probed_at = datetime.now(timezone.utc)
    path_str = str(db_path)

    # Explicit existence check: sqlite3.connect() creates a new file on missing
    # path rather than raising, which would give a false "ok" reading.
    if not db_path.exists():
        return DbProbeResult(
            success=False,
            latency_ms=None,
            error=f"OperationalError: database file not found: {path_str[:200]}",
            probed_at=probed_at,
            db_path=path_str,
        )

    t0 = time.perf_counter()
    try:
        # Open read-only via URI to avoid accidental writes or file creation.
        # PRAGMA integrity_check(1) reads the file header — catches corrupt DBs.
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0) as conn:
            conn.execute("PRAGMA integrity_check(1)").fetchone()
            conn.execute("SELECT 1").fetchone()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return DbProbeResult(
            success=True,
            latency_ms=elapsed_ms,
            error=None,
            probed_at=probed_at,
            db_path=path_str,
        )
    except Exception as exc:
        # Sanitize: only class name + first 200 chars of message
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        return DbProbeResult(
            success=False,
            latency_ms=None,
            error=error_msg,
            probed_at=probed_at,
            db_path=path_str,
        )


class DbHealthService:
    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root

    def snapshot(self) -> DbHealthSnapshot:
        cfg = load_config(self._repo_root)
        db_path = resolve_db_path(self._repo_root, cfg)
        threshold_ms = _slow_threshold_ms()
        probe = _probe_db(db_path)

        state: DbHealthState
        if not probe.success:
            state = "unavailable"
        elif probe.latency_ms is not None and probe.latency_ms >= threshold_ms:
            state = "degraded"
        else:
            state = "ok"

        return DbHealthSnapshot(
            state=state,
            last_check_at=probe.probed_at,
            latency_ms=probe.latency_ms,
            error=probe.error,
            db_path=probe.db_path,
            slow_threshold_ms=threshold_ms,
        )
