from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


AnalyticsReadSourceMode = Literal["fixture", "compatibility"]


class AnalyticsSummary(BaseModel):
    total_closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_net_pnl: float = 0.0
    average_net_pnl: float = 0.0
    today_net_pnl: float = 0.0


class AnalyticsEquityPoint(BaseModel):
    date: str
    daily_pnl: float = 0.0
    cumulative_pnl: float = 0.0


class AnalyticsClosedTrade(BaseModel):
    symbol: str
    scope: str
    net_pnl: float = 0.0
    was_profitable: bool = False
    closed_at: str


class AnalyticsReadTruncation(BaseModel):
    equity_curve: bool = False
    recent_closed_trades: bool = False


class AnalyticsReadSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: AnalyticsReadSourceMode
    summary: AnalyticsSummary = Field(default_factory=AnalyticsSummary)
    equity_curve: list[AnalyticsEquityPoint] = Field(default_factory=list)
    recent_closed_trades: list[AnalyticsClosedTrade] = Field(default_factory=list)
    truncated: AnalyticsReadTruncation = Field(default_factory=AnalyticsReadTruncation)
