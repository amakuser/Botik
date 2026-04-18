from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

OrderbookCategory = Literal["linear", "spot"]


class OrderbookLevel(BaseModel):
    price: str
    size: str
    total: str


class OrderbookSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    category: OrderbookCategory
    bids: list[OrderbookLevel] = Field(default_factory=list)
    asks: list[OrderbookLevel] = Field(default_factory=list)
    error: str | None = None
