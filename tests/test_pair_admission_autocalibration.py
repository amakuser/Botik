from __future__ import annotations

import json
from pathlib import Path

from src.botik.config import AppConfig
from src.botik.state.state import OrderBookAggregate, PublicTradeEvent, TradingState
from src.botik.strategy.pair_admission import evaluate_pair_admission


def _seed_state(state: TradingState, symbol: str) -> None:
    bids = [(100.0, 50.0), (99.9, 40.0), (99.8, 30.0)]
    asks = [(100.1, 50.0), (100.2, 40.0), (100.3, 30.0)]
    ts = 1_700_000_000_000
    for step in range(20):
        agg = OrderBookAggregate(
            symbol=symbol,
            best_bid=100.0,
            best_ask=100.1,
            mid=100.05,
            spread_ticks=1,
            imbalance_top_n=0.1,
            best_bid_size=50.0,
            best_ask_size=50.0,
            ts_ms=ts + step * 1000,
            ts_utc="2025-01-01T00:00:00Z",
        )
        state.set_orderbook(symbol, agg, bids=bids, asks=asks, is_snapshot=True, tick_size=0.1)
        state.record_public_trade(
            PublicTradeEvent(
                symbol=symbol,
                trade_id=f"t-{step}",
                seq=step + 1,
                ts_ms=ts + step * 1000,
                taker_side="Buy",
                price=100.05,
                qty=0.1,
            )
        )


def test_autocalibration_changes_min_required_spread(tmp_path: Path) -> None:
    symbol = "BTCUSDT"
    state = TradingState()
    _seed_state(state, symbol)

    config = AppConfig()
    config.strategy.min_trades_per_min = 0.0
    config.strategy.max_p95_trade_gap_ms = 60_000
    config.strategy.max_max_gap_ms = 60_000
    config.strategy.min_depth_multiplier = 0.0
    config.strategy.max_total_slippage_bps = 6.0
    config.strategy.bootstrap_fee_entry_bps = 2.0
    config.strategy.bootstrap_fee_exit_bps = 2.0
    config.fees.maker_rate = 0.0
    config.fees.taker_rate = 0.0
    # Keep baseline deterministic: do not read a real project autocalibration file.
    config.ml.autocalibration_path = str(tmp_path / "autocalibration_missing.json")

    no_auto = evaluate_pair_admission(symbol=symbol, state=state, config=config, now_ms=1_700_000_020_000)
    base_required = float(no_auto.metrics["min_required_spread_bps"])
    base_fee = float(no_auto.metrics["fee_entry_bps"])

    autocalib_path = tmp_path / "autocalibration.json"
    autocalib_path.write_text(
        json.dumps(
            {
                "sample_fills": 25,
                "recommended_fee_entry_bps": 10.0,
                "recommended_fee_exit_bps": 11.0,
                "recommended_total_slippage_bps": 2.0,
            }
        ),
        encoding="utf-8",
    )
    config.ml.autocalibration_path = str(autocalib_path)
    config.ml.min_fills_for_autocalibration = 20

    with_auto = evaluate_pair_admission(symbol=symbol, state=state, config=config, now_ms=1_700_000_020_000)
    assert float(with_auto.metrics["fee_entry_bps"]) > base_fee
    assert float(with_auto.metrics["min_required_spread_bps"]) > base_required
    assert bool(with_auto.metrics["autocalibration_applied"]) is True
