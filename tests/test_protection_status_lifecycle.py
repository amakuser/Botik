from __future__ import annotations

from pathlib import Path

from src.botik.storage.futures_store import upsert_futures_position, upsert_futures_protection
from src.botik.storage.sqlite_store import get_connection


def test_futures_protection_status_lifecycle_updates(tmp_path: Path) -> None:
    db_path = tmp_path / "protection_lifecycle.db"
    conn = get_connection(db_path)
    try:
        upsert_futures_position(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            margin_mode="cross",
            leverage=3.0,
            qty=0.5,
            entry_price=3000.0,
            mark_price=2995.0,
            liq_price=2500.0,
            unrealized_pnl=-2.5,
            realized_pnl=0.0,
            take_profit=None,
            stop_loss=None,
            trailing_stop=None,
            protection_status="pending",
            strategy_owner="runtime",
            source_of_truth="runtime",
            recovered_from_exchange=False,
        )
        upsert_futures_protection(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            status="pending",
            source_of_truth="runtime",
            stop_loss=None,
            take_profit=None,
        )
        upsert_futures_position(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            margin_mode="cross",
            leverage=3.0,
            qty=0.5,
            entry_price=3000.0,
            mark_price=3010.0,
            liq_price=2500.0,
            unrealized_pnl=5.0,
            realized_pnl=0.0,
            take_profit=3060.0,
            stop_loss=2970.0,
            trailing_stop=None,
            protection_status="protected",
            strategy_owner="runtime",
            source_of_truth="runtime",
            recovered_from_exchange=False,
        )
        upsert_futures_protection(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            status="protected",
            source_of_truth="runtime",
            stop_loss=2970.0,
            take_profit=3060.0,
        )
        upsert_futures_position(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            margin_mode="cross",
            leverage=3.0,
            qty=0.5,
            entry_price=3000.0,
            mark_price=2960.0,
            liq_price=2500.0,
            unrealized_pnl=-20.0,
            realized_pnl=0.0,
            take_profit=None,
            stop_loss=None,
            trailing_stop=None,
            protection_status="unprotected",
            strategy_owner="runtime",
            source_of_truth="runtime",
            recovered_from_exchange=False,
        )
        row = conn.execute(
            """
            SELECT protection_status, stop_loss, take_profit
            FROM futures_positions
            WHERE account_type='UNIFIED' AND symbol='ETHUSDT' AND side='Buy' AND position_idx=0
            """
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "unprotected"
        assert row[1] is None
        assert row[2] is None

        prot = conn.execute(
            """
            SELECT status, stop_loss, take_profit
            FROM futures_protection_orders
            WHERE account_type='UNIFIED' AND symbol='ETHUSDT' AND side='Buy' AND position_idx=0
            """
        ).fetchone()
        assert prot is not None
        assert str(prot[0]) == "protected"
    finally:
        conn.close()
