"""
Тесты логики micro_spread: при paused нет intents; при достаточном спреде — есть намерения.
"""
import pytest
from src.botik.config import AppConfig
from src.botik.state.state import OrderBookAggregate, TradingState
from src.botik.strategy.micro_spread import MicroSpreadStrategy


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def strategy(config):
    return MicroSpreadStrategy(config)


@pytest.fixture
def state_with_tight_spread():
    s = TradingState()
    s.set_orderbook(
        "BTCUSDT",
        OrderBookAggregate(
            symbol="BTCUSDT",
            best_bid=50000.0,
            best_ask=50000.01,
            mid=50000.005,
            spread_ticks=1,
            imbalance_top_n=0.0,
        ),
    )
    return s


@pytest.fixture
def state_with_wide_spread():
    s = TradingState()
    s.set_orderbook(
        "BTCUSDT",
        OrderBookAggregate(
            symbol="BTCUSDT",
            best_bid=50000.0,
            best_ask=50002.0,
            mid=50001.0,
            spread_ticks=200,
            imbalance_top_n=0.1,
        ),
    )
    return s


def test_paused_returns_no_intents(strategy, state_with_wide_spread):
    state_with_wide_spread.paused = True
    intents = strategy.get_intents(state_with_wide_spread)
    assert len(intents) == 0


def test_wide_spread_returns_intents(strategy, state_with_wide_spread):
    state_with_wide_spread.paused = False
    intents = strategy.get_intents(state_with_wide_spread)
    assert len(intents) >= 1
    sides = {i.side for i in intents}
    assert "Buy" in sides
    assert "Sell" in sides
    for i in intents:
        assert i.symbol == "BTCUSDT"
        assert i.order_link_id.startswith("mm-")
