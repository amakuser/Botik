from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from botik_app_service.contracts.runtime_status import RuntimeId
from botik_app_service.runtime_status.interfaces import RuntimeActivity

RUNTIME_CHANNELS: dict[RuntimeId, str] = {
    "spot": "spot",
    "futures": "futures",
}


class LegacyRuntimeStatusAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_activity(self, runtime_id: RuntimeId) -> RuntimeActivity:
        db_path = self._resolve_db_path()
        if not db_path.exists():
            return RuntimeActivity()

        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2) as connection:
                connection.row_factory = sqlite3.Row
                channel = RUNTIME_CHANNELS[runtime_id]
                last_heartbeat_row = connection.execute(
                    """
                    SELECT created_at_utc, message
                    FROM app_logs
                    WHERE channel = ?
                    ORDER BY created_at_utc DESC
                    LIMIT 1
                    """,
                    (channel,),
                ).fetchone()
                last_error_row = connection.execute(
                    """
                    SELECT created_at_utc, message
                    FROM app_logs
                    WHERE channel = ?
                      AND UPPER(level) IN ('ERROR', 'WARNING')
                    ORDER BY created_at_utc DESC
                    LIMIT 1
                    """,
                    (channel,),
                ).fetchone()
        except sqlite3.Error:
            return RuntimeActivity()

        return RuntimeActivity(
            last_heartbeat_at=self._parse_datetime(last_heartbeat_row["created_at_utc"]) if last_heartbeat_row else None,
            last_error=str(last_error_row["message"]) if last_error_row else None,
            last_error_at=self._parse_datetime(last_error_row["created_at_utc"]) if last_error_row else None,
        )

    def _resolve_db_path(self) -> Path:
        from botik_app_service.infra.legacy_helpers import load_config, resolve_db_path

        return resolve_db_path(self._repo_root, load_config(self._repo_root))

    @staticmethod
    def _parse_datetime(raw: object) -> datetime | None:
        if not raw:
            return None
        value = str(raw).strip()
        if not value:
            return None
        try:
            if value.endswith("Z"):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None
