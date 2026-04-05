"""
BacktestResult — датакласс с результатами бэктеста.

Хранит агрегированную статистику по прогону:
  - период, инструмент, таймфрейм
  - количество сделок, побед/поражений
  - PnL, max drawdown, Sharpe ratio, profit factor
  - список закрытых сделок

Используется BacktestRunner для возврата результата пользователю.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacktestResult:
    """
    Результат прогона бэктеста.

    Поля:
      symbol          — торговый инструмент (BTCUSDT и т.п.)
      scope           — "futures" | "spot"
      interval        — таймфрейм ("1", "5", "15", "60")
      start_date      — начало периода (ISO строка)
      end_date        — конец периода (ISO строка)
      total_candles   — кол-во свечей в данных
      trades          — кол-во совершённых сделок
      wins            — кол-во прибыльных сделок
      losses          — кол-во убыточных сделок
      win_rate        — % прибыльных сделок (0–100)
      total_pnl       — суммарный PnL в USDT
      max_drawdown    — максимальная просадка (абсолютная, в USDT)
      max_drawdown_pct— максимальная просадка в % от начального баланса
      sharpe_ratio    — коэффициент Шарпа (annualized)
      avg_win         — средний PnL по прибыльным сделкам
      avg_loss        — средний PnL по убыточным сделкам (отрицательный)
      profit_factor   — sum(wins_pnl) / abs(sum(losses_pnl)), inf если нет убытков
      trades_list     — список словарей с деталями каждой сделки
    """

    symbol: str
    scope: str           # "futures" | "spot"
    interval: str        # "1", "5", "15", "60"
    start_date: str      # ISO
    end_date: str        # ISO
    total_candles: int
    trades: int
    wins: int
    losses: int
    win_rate: float      # 0–100
    total_pnl: float
    max_drawdown: float        # абсолютный (USDT)
    max_drawdown_pct: float    # % от начального баланса
    sharpe_ratio: float
    avg_win: float
    avg_loss: float
    profit_factor: float       # sum(wins) / abs(sum(losses)), float('inf') если нет убытков
    trades_list: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Конвертирует результат в словарь для сериализации/логирования."""
        return {
            "symbol": self.symbol,
            "scope": self.scope,
            "interval": self.interval,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_candles": self.total_candles,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 2),
            "total_pnl": round(self.total_pnl, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "profit_factor": self.profit_factor if self.profit_factor != float("inf") else "inf",
            "trades_list": self.trades_list,
        }
