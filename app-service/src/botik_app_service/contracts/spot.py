from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


SpotReadSourceMode = Literal["fixture", "compatibility"]


class SpotBalance(BaseModel):
    asset: str
    free_qty: float = 0.0
    locked_qty: float = 0.0
    total_qty: float = 0.0
    source_of_truth: str | None = None
    updated_at_utc: datetime | None = None


class SpotHolding(BaseModel):
    account_type: str
    symbol: str
    base_asset: str
    free_qty: float = 0.0
    locked_qty: float = 0.0
    total_qty: float = 0.0
    avg_entry_price: float | None = None
    hold_reason: str
    source_of_truth: str
    recovered_from_exchange: bool = False
    strategy_owner: str | None = None
    auto_sell_allowed: bool = False
    updated_at_utc: datetime | None = None


class SpotOrder(BaseModel):
    account_type: str
    symbol: str
    side: str
    order_id: str | None = None
    order_link_id: str | None = None
    order_type: str | None = None
    time_in_force: str | None = None
    price: float = 0.0
    qty: float = 0.0
    filled_qty: float = 0.0
    status: str
    strategy_owner: str | None = None
    updated_at_utc: datetime | None = None


class SpotFill(BaseModel):
    account_type: str
    symbol: str
    side: str
    exec_id: str
    order_id: str | None = None
    order_link_id: str | None = None
    price: float = 0.0
    qty: float = 0.0
    fee: float | None = None
    fee_currency: str | None = None
    is_maker: bool | None = None
    exec_time_ms: int | None = None
    created_at_utc: datetime | None = None


class SpotReadSummary(BaseModel):
    account_type: str
    balance_assets_count: int = 0
    holdings_count: int = 0
    recovered_holdings_count: int = 0
    strategy_owned_holdings_count: int = 0
    open_orders_count: int = 0
    recent_fills_count: int = 0
    pending_intents_count: int = 0


class SpotReadTruncation(BaseModel):
    balances: bool = False
    holdings: bool = False
    active_orders: bool = False
    recent_fills: bool = False


class SpotReadSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: SpotReadSourceMode
    summary: SpotReadSummary
    balances: list[SpotBalance] = Field(default_factory=list)
    holdings: list[SpotHolding] = Field(default_factory=list)
    active_orders: list[SpotOrder] = Field(default_factory=list)
    recent_fills: list[SpotFill] = Field(default_factory=list)
    truncated: SpotReadTruncation = Field(default_factory=SpotReadTruncation)
