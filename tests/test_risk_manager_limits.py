"""
Тесты RiskManager: лимиты по экспозиции и по количеству ордеров в минуту.
"""
import pytest
from src.botik.config import AppConfig
from src.botik.risk.manager import RiskManager


@pytest.fixture
def risk_config():
    return AppConfig().risk


@pytest.fixture
def manager(risk_config):
    return RiskManager(risk_config)


def test_allow_single_order_within_limits(manager):
    # initial_equity=10000, max_total_exposure_pct=2% -> max 200 USDT
    result = manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=50000.0,
        qty=0.001,
        current_total_exposure_usdt=0,
        current_symbol_exposure_usdt=0,
    )
    assert result.allowed is True
    assert result.reason == "OK"


def test_reject_when_total_exposure_exceeded(manager):
    # 200 USDT limit; 100 already + 150 new = 250 > 200
    result = manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=50000.0,
        qty=0.003,
        current_total_exposure_usdt=100.0,
        current_symbol_exposure_usdt=100.0,
    )
    assert result.allowed is False
    assert "total_exposure" in result.reason.lower() or "exceed" in result.reason.lower()


def test_reject_when_symbol_exposure_exceeded(manager):
    # max_symbol_exposure_pct=1% -> 100 USDT per symbol; 50 + 60 = 110
    result = manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=60000.0,
        qty=0.001,
        current_total_exposure_usdt=50.0,
        current_symbol_exposure_usdt=50.0,
    )
    assert result.allowed is False
    assert "symbol" in result.reason.lower() or "exceed" in result.reason.lower()


def test_reject_zero_notional(manager):
    result = manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=50000.0,
        qty=0,
        current_total_exposure_usdt=0,
        current_symbol_exposure_usdt=0,
    )
    assert result.allowed is False
    assert "notional" in result.reason.lower() or "0" in result.reason


def test_orders_per_minute_tracked(manager):
    for _ in range(manager.max_orders_per_minute):
        manager.register_order_placed()
    result = manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=100.0,
        qty=0.01,
        current_total_exposure_usdt=0,
        current_symbol_exposure_usdt=0,
    )
    assert result.allowed is False
    assert "minute" in result.reason.lower() or "order" in result.reason.lower()
