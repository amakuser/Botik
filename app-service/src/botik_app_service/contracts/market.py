from datetime import datetime, timezone

from pydantic import BaseModel, Field


class MarketTickerEntry(BaseModel):
    symbol: str
    last_price: str
    price_24h_pcnt: str
    turnover_24h: str
    high_price_24h: str
    low_price_24h: str


class MarketTickerSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "bybit_public"
    category: str = "linear"
    tickers: list[MarketTickerEntry] = Field(default_factory=list)
    error: str | None = None
