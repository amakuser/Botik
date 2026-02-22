"""
Конфигурация бота: YAML + переменные окружения для секретов.
Секреты не хранятся в YAML — только имена переменных (api_key_env и т.д.).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# --- Модели секций (валидация и типы) ---


class BybitConfig(BaseModel):
    host: str = "api-demo.bybit.com"
    api_key_env: str = "BYBIT_API_KEY"
    api_secret_env: str = "BYBIT_API_SECRET"
    # WebSocket public (spot): mainnet stream.bybit.com, testnet stream-testnet.bybit.com
    ws_public_host: str = "stream-testnet.bybit.com"


class StrategyInventoryConfig(BaseModel):
    max_net_base_pct: float = 10.0
    max_position_value_usdt: float = 500.0


class StrategyConfig(BaseModel):
    min_spread_ticks: int = 2
    replace_interval_ms: int = 5000
    order_ttl_sec: int = 60
    default_tick_size: float = 0.01  # для перевода спреда в тики (spot USDT)
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
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5


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

    def get_bybit_api_key(self) -> str | None:
        return os.environ.get(self.bybit.api_key_env)

    def get_bybit_api_secret(self) -> str | None:
        return os.environ.get(self.bybit.api_secret_env)

    def get_telegram_token(self) -> str | None:
        return os.environ.get(self.telegram.token_env)

    def get_telegram_chat_id(self) -> str | None:
        return os.environ.get(self.telegram.chat_id_env)


def load_config(path: str | Path | None = None) -> AppConfig:
    """
    Загружает конфиг из YAML. Если path не передан — ищет config.yaml в текущей директории.
    Секреты подставляются из окружения по именам из конфига.
    """
    load_dotenv(override=False)
    if path is None:
        path = Path.cwd() / "config.yaml"
    path = Path(path)
    data: dict[str, Any] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return AppConfig.model_validate(data)


# --- Как проверить: python -c "from src.botik.config import load_config; c=load_config(); print(c.bybit.host)"
# --- Частые ошибки: не задать переменные окружения для API/Telegram; указать секрет в YAML.
# --- Что улучшить позже: валидация символов по списку биржи; подстановка config path через env.
