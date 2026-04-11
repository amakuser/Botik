from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


TelegramOpsSourceMode = Literal["fixture", "compatibility"]
TelegramConnectivityState = Literal["healthy", "degraded", "disabled", "missing_token", "unknown"]


class TelegramCommandEntry(BaseModel):
    ts: datetime | None = None
    command: str
    source: str
    status: str
    chat_id_masked: str | None = None
    username: str | None = None
    args: str | None = None


class TelegramAlertEntry(BaseModel):
    ts: datetime | None = None
    alert_type: str
    message: str
    delivered: bool = True
    source: str = "telegram"
    status: str = "ok"


class TelegramErrorEntry(BaseModel):
    ts: datetime | None = None
    error: str
    source: str = "telegram"
    status: str = "error"


class TelegramOpsSummary(BaseModel):
    bot_profile: str = "default"
    token_profile_name: str = "TELEGRAM_BOT_TOKEN"
    token_configured: bool = False
    internal_bot_disabled: bool = False
    connectivity_state: TelegramConnectivityState = "unknown"
    connectivity_detail: str | None = None
    allowed_chat_count: int = 0
    allowed_chats_masked: list[str] = Field(default_factory=list)
    commands_count: int = 0
    alerts_count: int = 0
    errors_count: int = 0
    last_successful_send: str | None = None
    last_error: str | None = None
    startup_status: str = "unknown"


class TelegramOpsTruncation(BaseModel):
    recent_commands: bool = False
    recent_alerts: bool = False
    recent_errors: bool = False


class TelegramOpsSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: TelegramOpsSourceMode
    summary: TelegramOpsSummary
    recent_commands: list[TelegramCommandEntry] = Field(default_factory=list)
    recent_alerts: list[TelegramAlertEntry] = Field(default_factory=list)
    recent_errors: list[TelegramErrorEntry] = Field(default_factory=list)
    truncated: TelegramOpsTruncation = Field(default_factory=TelegramOpsTruncation)


class TelegramConnectivityCheckResult(BaseModel):
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: TelegramOpsSourceMode
    state: TelegramConnectivityState
    detail: str | None = None
    bot_username: str | None = None
    latency_ms: float | None = None
    error: str | None = None
