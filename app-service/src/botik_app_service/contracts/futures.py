from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


FuturesReadSourceMode = Literal["fixture", "compatibility"]


class FuturesPosition(BaseModel):
    account_type: str
    symbol: str
    side: str
    position_idx: int
    margin_mode: str | None = None
    leverage: float | None = None
    qty: float = 0.0
    entry_price: float | None = None
    mark_price: float | None = None
    liq_price: float | None = None
    unrealized_pnl: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    protection_status: str
    source_of_truth: str
    recovered_from_exchange: bool = False
    strategy_owner: str | None = None
    updated_at_utc: datetime | None = None


class FuturesOpenOrder(BaseModel):
    account_type: str
    symbol: str
    side: str | None = None
    order_id: str | None = None
    order_link_id: str | None = None
    order_type: str | None = None
    time_in_force: str | None = None
    price: float | None = None
    qty: float | None = None
    status: str
    reduce_only: bool | None = None
    close_on_trigger: bool | None = None
    strategy_owner: str | None = None
    updated_at_utc: datetime | None = None


class FuturesFill(BaseModel):
    account_type: str
    symbol: str
    side: str
    exec_id: str
    order_id: str | None = None
    order_link_id: str | None = None
    price: float = 0.0
    qty: float = 0.0
    exec_fee: float | None = None
    fee_currency: str | None = None
    is_maker: bool | None = None
    exec_time_ms: int | None = None
    created_at_utc: datetime | None = None


class FuturesReadSummary(BaseModel):
    account_type: str
    positions_count: int = 0
    protected_positions_count: int = 0
    attention_positions_count: int = 0
    recovered_positions_count: int = 0
    open_orders_count: int = 0
    recent_fills_count: int = 0
    unrealized_pnl_total: float = 0.0


class FuturesReadTruncation(BaseModel):
    positions: bool = False
    active_orders: bool = False
    recent_fills: bool = False


class FuturesReadSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: FuturesReadSourceMode
    summary: FuturesReadSummary
    positions: list[FuturesPosition] = Field(default_factory=list)
    active_orders: list[FuturesOpenOrder] = Field(default_factory=list)
    recent_fills: list[FuturesFill] = Field(default_factory=list)
    truncated: FuturesReadTruncation = Field(default_factory=FuturesReadTruncation)
