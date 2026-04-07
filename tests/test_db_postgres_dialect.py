"""
Тесты для _sqlite_to_pg — трансляция SQL диалекта SQLite → PostgreSQL.
Задача #11: PostgreSQL миграция.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Убедимся, что src доступен
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.botik.storage.db import _sqlite_to_pg, _split_script


# ── _sqlite_to_pg ─────────────────────────────────────────────────────────


def test_autoincrement_translated_to_bigserial() -> None:
    sql = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
    result = _sqlite_to_pg(sql)
    assert "BIGSERIAL PRIMARY KEY" in result
    assert "AUTOINCREMENT" not in result


def test_integer_translated_to_bigint() -> None:
    sql = "CREATE TABLE t (qty INTEGER NOT NULL)"
    result = _sqlite_to_pg(sql)
    assert "BIGINT" in result
    assert "INTEGER" not in result


def test_real_translated_to_double_precision() -> None:
    sql = "CREATE TABLE t (price REAL DEFAULT 0.0)"
    result = _sqlite_to_pg(sql)
    assert "DOUBLE PRECISION" in result
    assert " REAL" not in result


def test_blob_translated_to_bytea() -> None:
    sql = "CREATE TABLE t (data BLOB)"
    result = _sqlite_to_pg(sql)
    assert "BYTEA" in result
    assert "BLOB" not in result


def test_datetime_now_translated() -> None:
    sql = "INSERT INTO t (ts) VALUES (datetime('now'))"
    result = _sqlite_to_pg(sql)
    assert "NOW()" in result.upper()
    assert "datetime" not in result.lower()


def test_insert_or_ignore_translated() -> None:
    sql = "INSERT OR IGNORE INTO t (a) VALUES (?)"
    result = _sqlite_to_pg(sql)
    assert "OR IGNORE" not in result.upper()
    assert "ON CONFLICT DO NOTHING" in result.upper()


def test_insert_or_ignore_does_not_double_add_conflict() -> None:
    """Если ON CONFLICT уже есть, не добавлять дважды."""
    sql = "INSERT OR IGNORE INTO t (a) VALUES (?) ON CONFLICT DO NOTHING"
    result = _sqlite_to_pg(sql)
    assert result.upper().count("ON CONFLICT DO NOTHING") == 1


def test_combined_translation() -> None:
    sql = (
        "CREATE TABLE price_history ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "  close REAL NOT NULL, "
        "  vol INTEGER, "
        "  ts TEXT DEFAULT (datetime('now'))"
        ")"
    )
    result = _sqlite_to_pg(sql)
    assert "BIGSERIAL PRIMARY KEY" in result
    assert "DOUBLE PRECISION" in result
    assert "BIGINT" in result
    assert "NOW()" in result.upper()


def test_text_type_unchanged() -> None:
    sql = "CREATE TABLE t (name TEXT NOT NULL)"
    result = _sqlite_to_pg(sql)
    assert "TEXT" in result


# ── _split_script ─────────────────────────────────────────────────────────


def test_split_script_basic() -> None:
    script = "SELECT 1; SELECT 2; SELECT 3"
    stmts = _split_script(script)
    assert len(stmts) == 3


def test_split_script_ignores_empty() -> None:
    script = "SELECT 1;  ; SELECT 2"
    stmts = _split_script(script)
    assert len(stmts) == 2


def test_split_script_single_statement() -> None:
    stmts = _split_script("SELECT 1")
    assert stmts == ["SELECT 1"]
