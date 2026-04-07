"""
DbMixin — low-level SQLite helpers shared by all API mixins.

All methods are @staticmethod or @classmethod — no instance state required.
"""
from __future__ import annotations

import sqlite3
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
