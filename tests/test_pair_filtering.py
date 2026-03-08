from __future__ import annotations

from src.botik.config import AppConfig
from src.botik.state.state import OrderBookAggregate, PublicTradeEvent, TradingState
from src.botik.strategy.pair_admission import evaluate_pair_admission


def _seed_state(state: TradingState, symbol: str, *, best_bid: float, best_ask: float) -> int:
    ts = 1_700_000_100_000
    bids = [(best_bid, 100.0), (best_bid - 0.1, 50.0)]
    asks = [(best_ask, 100.0), (best_ask + 0.1, 50.0)]
    mid = (best_bid + best_ask) / 2.0
    for i in range(60):
        state.set_orderbook(
            symbol,
            OrderBookAggregate(
                symbol=symbol,
                best_bid=best_bid,
                best_ask=best_ask,
                mid=mid,
                spread_ticks=1,
                imbalance_top_n=0.1,
                best_bid_size=100.0,
                best_ask_size=100.0,
                ts_ms=ts + i * 1000,
                ts_utc="2026-03-08T00:00:00Z",
            ),
            bids=bids,
            asks=asks,
            is_snapshot=True,
            tick_size=0.1,
        )
        state.record_public_trade(
            PublicTradeEvent(
                symbol=symbol,
                trade_id=f"t-{i}",
                seq=i + 1,
                ts_ms=ts + i * 1000,
                taker_side="Buy",
                price=mid,
                qty=0.1,
            )
        )
    return ts + 59_000


def _base_config() -> AppConfig:
    cfg = AppConfig()
    cfg.strategy.min_trades_per_min = 0.0
    cfg.strategy.max_p95_trade_gap_ms = 60_000
    cfg.strategy.max_max_gap_ms = 60_000
    cfg.strategy.min_depth_multiplier = 0.0
    cfg.strategy.max_total_slippage_bps = 10.0
    cfg.strategy.bootstrap_fee_entry_bps = 0.0
    cfg.strategy.bootstrap_fee_exit_bps = 0.0
    cfg.strategy.safety_buffer_bps = 0.0
    cfg.strategy.target_edge_bps = 0.0
    cfg.fees.maker_rate = 0.0
    cfg.fees.taker_rate = 0.0
    return cfg


def test_pair_admission_rejects_when_live_spread_below_min_spread_bps() -> None:
    symbol = "BTCUSDT"
    state = TradingState()
    now_ms = _seed_state(state, symbol, best_bid=100.0, best_ask=100.1)  # ~10 bps
    cfg = _base_config()
    cfg.strategy.min_spread_bps = 20.0

    decision = evaluate_pair_admission(symbol=symbol, state=state, config=cfg, now_ms=now_ms)
    assert decision.status != "PASS"
    assert float(decision.metrics["live_spread_bps"]) < float(decision.metrics["min_spread_bps"])
    assert "min_spread" in str(decision.reason).lower()


def test_pair_admission_can_pass_when_min_spread_bps_is_low() -> None:
    symbol = "ETHUSDT"
    state = TradingState()
    now_ms = _seed_state(state, symbol, best_bid=200.0, best_ask=200.2)  # ~10 bps
    cfg = _base_config()
    cfg.strategy.min_spread_bps = 1.0

    decision = evaluate_pair_admission(symbol=symbol, state=state, config=cfg, now_ms=now_ms)
    assert decision.status in {"PASS", "WATCH"}
    assert float(decision.metrics["live_spread_bps"]) >= float(decision.metrics["min_spread_bps"])
