from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.learning.bandit import GaussianThompsonBandit
from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, insert_signal_snapshot


def test_bandit_update_by_signal_persists_state(tmp_path: Path) -> None:
    db_path = tmp_path / "bandit.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)
        insert_signal_snapshot(
            conn,
            signal_id="sig-1",
            ts_signal_ms=1,
            symbol="BTCUSDT",
            side="Buy",
            best_bid=100.0,
            best_ask=100.1,
            mid=100.05,
            spread_bps=10.0,
            depth_bid_quote=1000.0,
            depth_ask_quote=1000.0,
            slippage_buy_bps_est=0.1,
            slippage_sell_bps_est=0.1,
            trades_per_min=10.0,
            p95_trade_gap_ms=1000.0,
            vol_1s_bps=1.0,
            min_required_spread_bps=5.0,
            scanner_status="PASS",
            model_version="rules-v1",
            profile_id="p1",
            order_size_quote=20.0,
            order_size_base=0.2,
            entry_price=100.0,
        )

        bandit = GaussianThompsonBandit(conn=conn, profile_ids=["p1", "p2"], epsilon=0.0)
        bandit.update(signal_id="sig-1", reward_bps=5.0)
        bandit.update(signal_id="sig-1", reward_bps=3.0)

        row = conn.execute(
            "SELECT n, mean FROM bandit_state WHERE symbol=? AND profile_id=?",
            ("BTCUSDT", "p1"),
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 2
        assert float(row[1]) == 4.0
    finally:
        conn.close()


def test_bandit_select_returns_profile_for_each_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "bandit_select.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)
        bandit = GaussianThompsonBandit(conn=conn, profile_ids=["safe", "aggr"], epsilon=0.1)
        selected = bandit.select(["BTCUSDT", "ETHUSDT"], ctx={})
        assert set(selected.keys()) == {"BTCUSDT", "ETHUSDT"}
        assert selected["BTCUSDT"] in {"safe", "aggr"}
        assert selected["ETHUSDT"] in {"safe", "aggr"}
    finally:
        conn.close()

