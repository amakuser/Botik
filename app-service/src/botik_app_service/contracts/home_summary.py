"""Public contract for GET /home/summary.

All fields that cannot be sourced from in-process data are explicitly null.
bybit and telegram connections are deferred — always null in this slice.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PrimaryAction(BaseModel):
    label: str
    kind: Literal["pause-trading", "open-diagnostics"]


class GlobalBlock(BaseModel):
    state: Literal["healthy", "warning", "critical"]
    health_score: int  # 0..100
    critical_reason: str | None
    primary_action: PrimaryAction | None  # only when state == "critical"


class TradingRuntimeBlock(BaseModel):
    state: Literal["running", "degraded", "offline", "unknown"]
    lag_seconds: float | None  # last_heartbeat_age_seconds


class TodayPnL(BaseModel):
    value: float
    currency: str  # "USDT"
    trend: Literal["up", "down", "flat"]


class TradingBlock(BaseModel):
    spot: TradingRuntimeBlock
    futures: TradingRuntimeBlock
    today_pnl: TodayPnL | None  # null if no PnL data
    today_pnl_series: None = None  # always null in this slice


class PositionEntry(BaseModel):
    id: str          # synthetic key "{symbol}-{side}"
    symbol: str
    side: str
    protection_state: str  # raw protection_status


class RiskByState(BaseModel):
    protected: int = 0
    pending: int = 0
    unprotected: int = 0
    repairing: int = 0
    failed: int = 0


class RiskBlock(BaseModel):
    positions_total: int
    by_state: RiskByState
    positions: list[PositionEntry]  # capped at 8


class ReconciliationBlock(BaseModel):
    state: Literal["healthy", "degraded", "stale", "failed", "unsupported"]
    last_run_at: datetime | None
    last_run_age_seconds: float | None
    next_run_in_seconds: int | None
    drift_count: int


class ActiveModel(BaseModel):
    version: str
    accuracy: float | None
    trained_at: datetime | None


class LastTrainingRun(BaseModel):
    scope: str
    ended_at: datetime | None
    status: str


class MLBlock(BaseModel):
    pipeline_state: Literal["idle", "training", "serving", "error", "unknown"]
    active_model: ActiveModel | None
    last_training_run: LastTrainingRun | None


class ConnectionsBlock(BaseModel):
    bybit: None = None        # always null — deferred
    telegram: None = None     # always null — deferred
    database: Literal["ok", "degraded", "unavailable"]


class ActivityEntry(BaseModel):
    ts: datetime
    summary: str
    severity: Literal["info", "warn", "err", "critical"]


class HomeSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    global_: GlobalBlock = Field(alias="global")
    trading: TradingBlock
    risk: RiskBlock
    reconciliation: ReconciliationBlock
    ml: MLBlock
    connections: ConnectionsBlock
    activity: list[ActivityEntry]  # capped at 12
