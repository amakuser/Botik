"""
Bot configuration: YAML + env vars for secrets.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class BybitConfig(BaseModel):
    host: str = "api-demo.bybit.com"
    api_key_env: str = "BYBIT_API_KEY"
    api_secret_key_env: str = "BYBIT_API_SECRET_KEY"
    # Legacy fallback (backward compatibility)
    api_secret_env: str = "BYBIT_API_SECRET"
    rsa_private_key_path_env: str = "BYBIT_RSA_PRIVATE_KEY_PATH"
    # Public Spot market data host.
    ws_public_host: str = "stream.bybit.com"


class StrategyInventoryConfig(BaseModel):
    max_net_base_pct: float = 10.0
    max_position_value_usdt: float = 500.0


class StrategyConfig(BaseModel):
    min_spread_ticks: int = 2
    replace_interval_ms: int = 5000
    order_ttl_sec: int = 60
    default_tick_size: float = 0.01

    # Spread scanner params.
    order_qty_base: float = 0.001
    entry_tick_offset: int = 1
    target_profit: float = 0.0002
    safety_buffer: float = 0.0001
    min_top_book_qty: float = 0.0

    # Execution behavior.
    maker_only: bool = True
    position_hold_timeout_sec: int = 180
    min_position_qty_base: float = 0.000001
    force_exit_enabled: bool = True
    force_exit_time_in_force: str = "IOC"
    force_exit_cooldown_sec: int = 10
    stop_loss_pct: float = 0.003
    take_profit_pct: float = 0.005
    pnl_exit_enabled: bool = True

    inventory: StrategyInventoryConfig = Field(default_factory=StrategyInventoryConfig)


class RiskConfig(BaseModel):
    initial_equity_usdt: float = 10000.0
    max_total_exposure_pct_of_initial: float = 2.0
    max_symbol_exposure_pct: float = 1.0
    max_orders_per_minute: int = 30


class FeesConfig(BaseModel):
    maker_rate: float = 0.001
    taker_rate: float = 0.001
    default_when_unknown: str = "taker"


class TelegramConfig(BaseModel):
    token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"


class StorageConfig(BaseModel):
    path: str = "data/botik.db"
    metrics_interval_sec: int = 1


class LoggingConfig(BaseModel):
    dir: str = "logs"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


class ExecutionConfig(BaseModel):
    mode: str = "live"  # live | paper
    paper_fill_on_cross: bool = True


class AppConfig(BaseModel):
    bybit: BybitConfig = Field(default_factory=BybitConfig)
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    ws_depth: int = 50
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    fees: FeesConfig = Field(default_factory=FeesConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    start_paused: bool = True
    allow_panic_market_close: bool = False
    storage: StorageConfig = Field(default_factory=StorageConfig)
    retention_days: int = 30
    retention_max_db_size_gb: float = 50.0
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    def get_bybit_api_key(self) -> str | None:
        return os.environ.get(self.bybit.api_key_env)

    def get_bybit_api_secret(self) -> str | None:
        return os.environ.get(self.bybit.api_secret_key_env) or os.environ.get(self.bybit.api_secret_env)

    def get_bybit_rsa_private_key_path(self) -> str | None:
        return os.environ.get(self.bybit.rsa_private_key_path_env)

    def get_bybit_auth_mode(self) -> str:
        """Auth mode for REST: hmac (primary), rsa (fallback), none."""
        if self.get_bybit_api_secret():
            return "hmac"
        if self.get_bybit_rsa_private_key_path():
            return "rsa"
        return "none"

    def get_telegram_token(self) -> str | None:
        return os.environ.get(self.telegram.token_env)

    def get_telegram_chat_id(self) -> str | None:
        return os.environ.get(self.telegram.chat_id_env)


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv(override=False)
    if path is None:
        path = Path.cwd() / "config.yaml"
    path = Path(path)
    data: dict[str, Any] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return AppConfig.model_validate(data)
