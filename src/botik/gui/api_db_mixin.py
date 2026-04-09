"""
DbMixin — low-level SQLite helpers shared by all API mixins.

All methods are @staticmethod or @classmethod — no instance state required.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DbMixin:
    """Mixin providing low-level SQLite helper methods to DashboardAPI."""

    @staticmethod
    def _db_connect(db_path: Path) -> sqlite3.Connection | None:
        if not db_path.exists():
            return None
        try:
            conn = sqlite3.connect(str(db_path), timeout=3, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        try:
            conn.execute(f"SELECT 1 FROM {table_name} WHERE 1=0").fetchall()
            return True
        except Exception:
            return False

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            cursor = conn.execute(f"SELECT * FROM {table_name} WHERE 1=0")
            return {str(col[0]) for col in (cursor.description or [])}
        except Exception:
            return set()

    @staticmethod
    def _first_existing_column(columns: set[str], *candidates: str) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @classmethod
    def _column_expr(
        cls,
        columns: set[str],
        candidates: tuple[str, ...] | list[str],
        alias: str,
        *,
        default_sql: str = "NULL",
    ) -> str:
        column = cls._first_existing_column(columns, *candidates)
        return f"{column} AS {alias}" if column else f"{default_sql} AS {alias}"

    @staticmethod
    def _normalize_model_scope(value: Any, fallback: Any = "") -> str:
        text = str(value or "").strip().lower()
        hint = str(fallback or "").strip().lower()
        joined = f"{text} {hint}".strip()
        if "future" in joined or "linear" in joined:
            return "futures"
        if "spot" in joined:
            return "spot"
        return text or (hint if hint else "unknown")

    @staticmethod
    def _model_ids_match(left: Any, right: Any) -> bool:
        a = str(left or "").strip().lower()
        b = str(right or "").strip().lower()
        if not a or not b or a in {"unknown", "none", "null"} or b in {"unknown", "none", "null"}:
            return False
        return a == b or a.endswith(b) or b.endswith(a)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except Exception:
            return None

    @classmethod
    def _app_logs_ts_column(cls, conn: sqlite3.Connection) -> str | None:
        columns = cls._table_columns(conn, "app_logs")
        return cls._first_existing_column(columns, "created_at_utc", "recorded_at_utc")

    @classmethod
    def _read_app_logs(
        cls,
        conn: sqlite3.Connection,
        *,
        channels: tuple[str, ...] | list[str] | None = None,
        limit: int = 120,
        levels: tuple[str, ...] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not cls._table_exists(conn, "app_logs"):
            return []
        ts_column = cls._app_logs_ts_column(conn)
        if not ts_column:
            return []

        where_parts: list[str] = []
        params: list[Any] = []
        if channels:
            placeholders = ",".join("?" for _ in channels)
            where_parts.append(f"channel IN ({placeholders})")
            params.extend(str(channel or "") for channel in channels)
        if levels:
            placeholders = ",".join("?" for _ in levels)
            where_parts.append(f"level IN ({placeholders})")
            params.extend(str(level or "") for level in levels)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        rows = conn.execute(
            f"SELECT channel, level, message, {ts_column} AS ts "
            "FROM app_logs "
            f"{where_sql} "
            f"ORDER BY {ts_column} DESC, id DESC LIMIT ?",
            (*params, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    @classmethod
    def _write_app_log(
        cls,
        db_path: Path,
        *,
        channel: str,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> bool:
        conn = cls._db_connect(db_path)
        if conn is None or not cls._table_exists(conn, "app_logs"):
            if conn is not None:
                conn.close()
            return False
        ts_column = cls._app_logs_ts_column(conn)
        if not ts_column:
            conn.close()
            return False

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        try:
            conn.execute(
                f"INSERT INTO app_logs (channel, level, message, extra_json, {ts_column}) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(channel or "sys"), str(level or "INFO"), str(message or ""), extra_json, now_utc),
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()
