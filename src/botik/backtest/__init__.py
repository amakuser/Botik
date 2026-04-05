"""
Модуль бэктестинга торговых стратегий.

Экспортирует:
  BacktestRunner          — псевдоним для FuturesBacktestRunner (по умолчанию)
  FuturesBacktestRunner   — бэктест фьючерсной стратегии
  SpotBacktestRunner      — бэктест спотовой стратегии
  BacktestResult          — датакласс с результатами прогона
"""
from src.botik.backtest.backtest_result import BacktestResult
from src.botik.backtest.backtest_runner import (
    FuturesBacktestRunner,
    SpotBacktestRunner,
)

# Псевдоним для удобства импорта
BacktestRunner = FuturesBacktestRunner

__all__ = [
    "BacktestResult",
    "BacktestRunner",
    "FuturesBacktestRunner",
    "SpotBacktestRunner",
]
