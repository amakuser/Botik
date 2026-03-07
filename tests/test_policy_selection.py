from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from src.botik.config import ActionProfileConfig
from src.botik.learning.bandit import GaussianThompsonBandit
from src.botik.learning.policy import PolicySelector
from src.botik.learning.policy_manager import ModelBundle
from src.botik.storage.lifecycle_store import ensure_lifecycle_schema


def test_policy_select_uses_model_when_available(monkeypatch, tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "policy.db"))
    try:
        ensure_lifecycle_schema(conn)
        bandit = GaussianThompsonBandit(conn=conn, profile_ids=["safe", "aggr"], epsilon=0.0)
        selector = PolicySelector(bandit=bandit)

        monkeypatch.setattr(
            bandit,
            "select",
            lambda pass_symbols, ctx: {sym: "safe" for sym in pass_symbols},
        )

        profiles = [
            ActionProfileConfig(profile_id="safe", order_qty_base=0.001, target_profit=0.0001),
            ActionProfileConfig(profile_id="aggr", order_qty_base=0.002, target_profit=0.0002),
        ]
        ctx = {
            "BTCUSDT": {
                "median_spread_bps": 12.0,
                "depth_bid_quote": 20000.0,
                "depth_ask_quote": 18000.0,
                "slippage_buy_bps": 0.5,
                "slippage_sell_bps": 0.5,
                "trades_per_min": 30.0,
                "p95_trade_gap_ms": 2500.0,
                "vol_1s_bps": 1.0,
                "min_required_spread_bps": 8.0,
                "mid": 50000.0,
            }
        }

        no_model = selector.select(
            pass_symbols=["BTCUSDT"],
            profiles=profiles,
            ctx=ctx,
            model=None,
            eps=0.0,
        )
        assert no_model["BTCUSDT"] == "safe"

        monkeypatch.setattr(
            "src.botik.learning.policy.predict_with_details",
            lambda _model, _matrix: (np.array([0.2, 0.9]), np.array([1.0, 12.0])),
        )
        with_model = selector.select(
            pass_symbols=["BTCUSDT"],
            profiles=profiles,
            ctx=ctx,
            model=ModelBundle(model_id="m-1", payload={}),
            eps=0.0,
        )
        assert with_model["BTCUSDT"] == "aggr"
    finally:
        conn.close()
