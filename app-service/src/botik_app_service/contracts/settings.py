from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SettingsSourceMode = Literal["env_file", "environment", "unknown"]
SettingsTestState = Literal["ok", "error", "skipped", "unknown"]


class SettingsField(BaseModel):
    key: str
    label: str
    value: str
    masked: bool = False
    present: bool = False


class SettingsSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: SettingsSourceMode
    env_file_path: str | None = None
    env_file_exists: bool = False
    fields: list[SettingsField] = Field(default_factory=list)


class SettingsSaveRequest(BaseModel):
    bybit_api_key: str | None = None
    bybit_api_secret: str | None = None
    bybit_mainnet_api_key: str | None = None
    bybit_mainnet_api_secret: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    db_url: str | None = None


class SettingsSaveResult(BaseModel):
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool
    detail: str | None = None
    fields_written: list[str] = Field(default_factory=list)


class BybitTestRequest(BaseModel):
    host: str = "demo"
    api_key: str
    api_secret: str


class BybitTestResult(BaseModel):
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: SettingsTestState
    detail: str | None = None
    latency_ms: float | None = None
