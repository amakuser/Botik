from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

BacktestScope = Literal["futures", "spot"]
BacktestInterval = Literal["1", "5", "15", "60"]


class BacktestRunRequest(BaseModel):
    scope: BacktestScope = "futures"
    symbol: str = "BTCUSDT"
    interval: BacktestInterval = "15"
    days_back: int = 30
    balance: float = 10000.0


class BacktestTrade(BaseModel):
    opened_at: str = ""
    closed_at: str = ""
    symbol: str = ""
    side: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    pnl: float = 0.0
    reason: str = ""


class BacktestRunResult(BaseModel):
    ran_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scope: BacktestScope
    symbol: str
    interval: str
    days_back: int
    start_date: str = ""
    end_date: str = ""
    total_candles: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: Any = 0.0
    trades_list: list[BacktestTrade] = Field(default_factory=list)
    error: str | None = None
