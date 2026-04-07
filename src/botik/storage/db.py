"""
Database connection abstraction for Botik.

Supports SQLite (default) and PostgreSQL.
Driver is selected via DB_URL environment variable:
  - sqlite:///data/botik.db         → SQLite  (default)
  - postgresql://user:pass@host/db  → PostgreSQL

Usage:
    from src.botik.storage.db import get_db, Database

    db = get_db()               # singleton, reads DB_URL from env
    with db.connect() as conn:
        conn.execute("SELECT 1")
        conn.commit()
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterator


# ─────────────────────────────────────────────────────────────────────────────
#  Placeholder style
# ─────────────────────────────────────────────────────────────────────────────

SQLITE   = "sqlite"
POSTGRES = "postgres"


# ─────────────────────────────────────────────────────────────────────────────
#  Unified connection wrapper
# ─────────────────────────────────────────────────────────────────────────────

class Conn:
    """
    Thin wrapper that normalises SQLite and PostgreSQL connections to the same
    interface used throughout existing store modules.

    Key differences handled here:
    - Placeholder:  SQLite uses ?   | PostgreSQL uses %s
    - executescript: only SQLite    | PG: split on ';' and run separately
    - row_factory:  Row (SQLite)    | dict cursor (PG)
    """

    def __init__(self, raw, driver: str) -> None:
        self._raw = raw
        self._driver = driver

    # ── passthrough ──────────────────────────────────────────────────────────

    @property
    def dialect(self) -> str:
        return self._driver

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        sql_norm = self._normalize_sql(sql)
        cur = self._raw.cursor()
        cur.execute(sql_norm, params)
        return cur

    def executemany(self, sql: str, param_seq) -> Any:
        sql_norm = self._normalize_sql(sql)
        cur = self._raw.cursor()
        cur.executemany(sql_norm, param_seq)
        return cur

    def executescript(self, script: str) -> None:
        """Run a multi-statement script (CREATE TABLE IF NOT EXISTS …)."""
        if self._driver == SQLITE:
            self._raw.executescript(script)
        else:
            # PostgreSQL: translate SQLite dialect, split by ';', run each statement
            cur = self._raw.cursor()
            for stmt in _split_script(script):
                pg_stmt = _sqlite_to_pg(stmt)
                cur.execute(pg_stmt)
            self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    # ── introspection (used by _ensure_column helpers) ───────────────────────

    def table_exists(self, table: str) -> bool:
        if self._driver == SQLITE:
            row = self._raw.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        else:
            cur = self._raw.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name=%s", (table,)
            )
            row = cur.fetchone()
        return bool(row)

    def table_columns(self, table: str) -> set[str]:
        if self._driver == SQLITE:
            rows = self._raw.execute(f"PRAGMA table_info({table})").fetchall()
            return {str(r[1]) for r in rows if len(r) > 1 and r[1]}
        else:
            cur = self._raw.cursor()
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                (table,),
            )
            return {str(r[0]) for r in cur.fetchall()}

    def ensure_column(self, table: str, name: str, ddl: str) -> None:
        """Add column if it doesn't exist (idempotent)."""
        cols = self.table_columns(table)
        if name not in cols:
            ddl_pg = _sqlite_ddl_to_pg(ddl) if self._driver == POSTGRES else ddl
            self.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_pg}")

    # ── SQL dialect normalisation ────────────────────────────────────────────

    def _normalize_sql(self, sql: str) -> str:
        if self._driver == POSTGRES:
            return sql.replace("?", "%s")
        return sql

    # ── context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "Conn":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Database class
# ─────────────────────────────────────────────────────────────────────────────

class Database:
    """
    Central database accessor.  Instantiate once; call connect() to get a Conn.

    Thread safety:
    - SQLite:     each call returns a new sqlite3 connection (check_same_thread=False).
    - PostgreSQL: simple connection per-call (pool can be added later).
    """

    def __init__(self, url: str) -> None:
        self._url = url.strip()
        self._driver = _detect_driver(self._url)
        self._sqlite_path: Path | None = None
        self._pg_dsn: str | None = None

        if self._driver == SQLITE:
            path_str = self._url.replace("sqlite:///", "").replace("sqlite://", "")
            self._sqlite_path = Path(path_str)
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._pg_dsn = self._url

    @property
    def driver(self) -> str:
        return self._driver

    @property
    def url(self) -> str:
        return self._url

    def connect(self) -> Conn:
        """Return a new Conn.  Caller is responsible for commit/close."""
        if self._driver == SQLITE:
            raw = sqlite3.connect(
                str(self._sqlite_path),
                timeout=30,
                check_same_thread=False,
            )
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA journal_mode=WAL")
            raw.execute("PRAGMA foreign_keys=ON")
            return Conn(raw, SQLITE)
        else:
            try:
                import psycopg2
                import psycopg2.extras
                raw = psycopg2.connect(self._pg_dsn)
                raw.autocommit = False
                # DictCursor so .fetchone() / .fetchall() return dict-like rows
                raw.cursor_factory = psycopg2.extras.RealDictCursor
                return Conn(raw, POSTGRES)
            except ImportError as exc:
                raise RuntimeError(
                    "psycopg2 is required for PostgreSQL support. "
                    "Install it with: pip install psycopg2-binary"
                ) from exc

    @contextmanager
    def transaction(self) -> Generator[Conn, None, None]:
        """Context manager that auto-commits or rolls back."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton
# ─────────────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_instance: Database | None = None


def get_db(url: str | None = None) -> Database:
    """
    Return the process-level Database singleton.

    First call wins:  if url is given it takes precedence over DB_URL env var.
    Default: sqlite:///data/botik.db  (relative to cwd)
    """
    global _instance
    with _lock:
        if _instance is None:
            resolved_url = (
                url
                or os.environ.get("DB_URL", "")
                or "sqlite:///data/botik.db"
            )
            _instance = Database(resolved_url)
        return _instance


def reset_db(url: str | None = None) -> Database:
    """Force-reset the singleton (used in tests or on first startup with a new URL)."""
    global _instance
    with _lock:
        resolved_url = (
            url
            or os.environ.get("DB_URL", "")
            or "sqlite:///data/botik.db"
        )
        _instance = Database(resolved_url)
        return _instance


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_driver(url: str) -> str:
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return POSTGRES
    return SQLITE


def _split_script(script: str) -> list[str]:
    """Split SQL script on ';' ignoring empty statements."""
    stmts = []
    for s in script.split(";"):
        s = s.strip()
        if s:
            stmts.append(s)
    return stmts


def _sqlite_ddl_to_pg(ddl: str) -> str:
    """Convert SQLite column DDL snippet to PostgreSQL equivalent (used by ensure_column)."""
    ddl = ddl.upper()
    ddl = ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    ddl = ddl.replace("TEXT", "TEXT")
    ddl = ddl.replace("REAL", "DOUBLE PRECISION")
    ddl = ddl.replace("INTEGER", "BIGINT")
    ddl = ddl.replace("BLOB", "BYTEA")
    return ddl


def _sqlite_to_pg(sql: str) -> str:
    """
    Translate a full SQLite SQL statement to PostgreSQL dialect.

    Handles the SQLite-specific syntax used in migrations:
      - INTEGER PRIMARY KEY AUTOINCREMENT → BIGSERIAL PRIMARY KEY
      - REAL type → DOUBLE PRECISION
      - INTEGER type → BIGINT
      - BLOB → BYTEA
      - datetime('now') → NOW()
      - INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    """
    import re

    # AUTOINCREMENT — must come before generic INTEGER replacement
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGSERIAL PRIMARY KEY",
        sql, flags=re.IGNORECASE,
    )

    # REAL column type (word boundary prevents matching inside identifiers)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql, flags=re.IGNORECASE)

    # INTEGER standalone type
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql, flags=re.IGNORECASE)

    # BLOB
    sql = re.sub(r"\bBLOB\b", "BYTEA", sql, flags=re.IGNORECASE)

    # SQLite datetime functions
    sql = re.sub(r"datetime\('now'\)", "NOW()", sql, flags=re.IGNORECASE)

    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    if re.search(r"\bINSERT\s+OR\s+IGNORE\b", sql, re.IGNORECASE):
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", sql, flags=re.IGNORECASE)
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip() + " ON CONFLICT DO NOTHING"

    return sql
