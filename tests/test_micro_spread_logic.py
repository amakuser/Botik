"""Tests for micro spread strategy behavior."""
import pytest

from src.botik.config import AppConfig
from src.botik.state.state import OrderBookAggregate, TradingState
from src.botik.strategy.micro_spread import MicroSpreadStrategy


@pytest.fixture
def config() -> AppConfig:
    cfg = AppConfig()
    cfg.symbols = ["BTCUSDT"]
    cfg.strategy.replace_interval_ms = 0
    cfg.strategy.target_profit = 0.0
    cfg.strategy.safety_buffer = 0.0
    cfg.strategy.min_top_book_qty = 0.5
    cfg.strategy.order_qty_base = 0.001
    cfg.strategy.entry_tick_offset = 1
    cfg.fees.maker_rate = 0.0
    cfg.fees.taker_rate = 0.0
    return cfg


@pytest.fixture
def strategy(config: AppConfig) -> MicroSpreadStrategy:
    return MicroSpreadStrategy(config)


@pytest.fixture
def state_with_tight_spread() -> TradingState:
    state = TradingState()
    state.set_orderbook(
        "BTCUSDT",
        OrderBookAggregate(
            symbol="BTCUSDT",
            best_bid=50000.0,
            best_ask=50000.01,
            best_bid_size=10.0,
            best_ask_size=10.0,
            mid=50000.005,
            spread_ticks=1,
            imbalance_top_n=0.0,
        ),
    )
    return state


@pytest.fixture
def state_with_wide_spread() -> TradingState:
    state = TradingState()
    state.set_orderbook(
        "BTCUSDT",
        OrderBookAggregate(
            symbol="BTCUSDT",
            best_bid=50000.0,
            best_ask=50020.0,
            best_bid_size=10.0,
            best_ask_size=10.0,
            mid=50010.0,
            spread_ticks=2000,
            imbalance_top_n=0.1,
        ),
    )
    return state


def test_paused_returns_no_intents(strategy: MicroSpreadStrategy, state_with_wide_spread: TradingState) -> None:
    state_with_wide_spread.paused = True
    assert strategy.get_intents(state_with_wide_spread) == []


def test_wide_spread_returns_bid_and_ask(strategy: MicroSpreadStrategy, state_with_wide_spread: TradingState) -> None:
    state_with_wide_spread.paused = False
    intents = strategy.get_intents(state_with_wide_spread)
    assert len(intents) == 2
    sides = {intent.side for intent in intents}
    assert sides == {"Buy", "Sell"}
    for intent in intents:
        assert intent.symbol == "BTCUSDT"
        assert intent.order_link_id.startswith("mm-")


def test_tight_spread_rejects(strategy: MicroSpreadStrategy, state_with_tight_spread: TradingState) -> None:
    state_with_tight_spread.paused = False
    intents = strategy.get_intents(state_with_tight_spread)
    assert intents == []
