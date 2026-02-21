"""Tests for strategy base and MA strategy."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.base import BaseStrategy, MarketData, Signal
from strategies.ma_strategy import MAStrategy


def test_signal():
    s = Signal(direction="long", size=100.0, strategy_id="MAStrategy")
    assert s.direction == "long"
    assert s.size == 100.0


def test_ma_strategy_no_signal_without_ma():
    strat = MAStrategy("BTCUSDT", "15", {"fast_period": 10, "slow_period": 20})
    md = MarketData("BTCUSDT", "15", 40000.0, 0.0, {})
    assert strat.on_tick(md) is None


def test_ma_strategy_long():
    strat = MAStrategy("BTCUSDT", "15", {"fast_period": 10, "slow_period": 20, "position_size_pct": 0.01})
    md = MarketData("BTCUSDT", "15", 40000.0, 0.0, {"fast_ma": 40100, "slow_ma": 39900})
    sig = strat.on_tick(md)
    assert sig is not None
    assert sig.direction == "long"
    assert sig.strategy_id == "MAStrategy"


def test_ma_strategy_short():
    strat = MAStrategy("BTCUSDT", "15", {"fast_period": 10, "slow_period": 20})
    md = MarketData("BTCUSDT", "15", 40000.0, 0.0, {"fast_ma": 39900, "slow_ma": 40100})
    sig = strat.on_tick(md)
    assert sig is not None
    assert sig.direction == "short"
