from __future__ import annotations

from pathlib import Path

from src.botik.main import get_reconciliation_entry_block_reason
from src.botik.storage.core_store import insert_reconciliation_issue
from src.botik.storage.sqlite_store import get_connection


def test_reconciliation_entry_lock_blocks_symbol_for_open_blocking_issue(tmp_path: Path) -> None:
    db_path = tmp_path / "reconciliation_lock.db"
    conn = get_connection(db_path)
    try:
        insert_reconciliation_issue(
            conn,
            issue_type="orphaned_exchange_position",
            domain="futures",
            severity="error",
            symbol="BTCUSDT",
            details={"source": "test"},
            status="open",
        )
        reason = get_reconciliation_entry_block_reason(conn, symbol="btcusdt")
        assert reason is not None
        assert "orphaned_exchange_position" in reason
    finally:
        conn.close()


def test_reconciliation_entry_lock_ignores_non_blocking_issue_types(tmp_path: Path) -> None:
    db_path = tmp_path / "reconciliation_lock_non_blocking.db"
    conn = get_connection(db_path)
    try:
        insert_reconciliation_issue(
            conn,
            issue_type="unprotected_position",
            domain="futures",
            severity="critical",
            symbol="ETHUSDT",
            details={"source": "test"},
            status="open",
        )
        reason = get_reconciliation_entry_block_reason(conn, symbol="ETHUSDT")
        assert reason is None
    finally:
        conn.close()
