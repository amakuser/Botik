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
    market_category: str = "spot"  # spot | linear


class StrategyInventoryConfig(BaseModel):
    max_net_base_pct: float = 10.0
    max_position_value_usdt: float = 500.0


class ActionProfileConfig(BaseModel):
    profile_id: str
    entry_tick_offset: int = 1
    order_qty_base: float = 0.001
    target_profit: float = 0.0001
    safety_buffer: float = 0.00005
    min_top_book_qty: float = 0.0
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    hold_timeout_sec: int | None = None
    maker_only: bool | None = None


class StrategyConfig(BaseModel):
    runtime_strategy: str = "spread_maker"  # spread_maker | spike_reversal
    min_spread_ticks: int = 1
    min_spread_bps: float = 8.0
    replace_interval_ms: int = 5000
    order_ttl_sec: int = 60
    default_tick_size: float = 0.01

    # Spread scanner params.
    order_qty_base: float = 0.001
    entry_tick_offset: int = 1
    target_profit: float = 0.0001
    safety_buffer: float = 0.00005
    min_top_book_qty: float = 0.0

    # Execution behavior.
    # Deprecated runtime switch: entries are always maker-only now.
    maker_only: bool = True
    position_hold_timeout_sec: int = 180
    min_position_qty_base: float = 0.000001
    # Positions below this quote notional are treated as dust (primarily for spot).
    min_active_position_usdt: float = 1.0
    force_exit_enabled: bool = True
    force_exit_time_in_force: str = "IOC"
    force_exit_use_market: bool = False  # When True, stop-loss exits use Market order (guaranteed fill on spot)
    force_exit_cooldown_sec: int = 10
    force_exit_dust_cooldown_sec: int = 300
    allow_taker_exit: bool = True
    stop_loss_pct: float = 0.003
    take_profit_pct: float = 0.005
    pnl_exit_enabled: bool = True
    fallback_stoploss_bps: float = 0.0
    fallback_breakeven_bps: float = 0.0
    fallback_trailing_bps: float = 0.0
    fallback_trailing_activation_bps: float = 0.0
    allow_partial_outcome: bool = False
    scanner_enabled: bool = True
    scanner_interval_sec: int = 3
    scanner_top_k: int = 30
    fast_reprice_on_send: bool = True
    quote_max_book_age_ms: int = 1200
    execution_refresh_interval_sec: float = 8.0
    execution_refresh_max_symbols: int = 12
    execution_refresh_concurrency: int = 4
    reconciliation_enabled: bool = True
    reconciliation_interval_sec: int = 120
    reconciliation_symbols_limit: int = 120
    auto_universe_enabled: bool = False
    auto_universe_host: str = "api.bybit.com"
    auto_universe_quote: str = "USDT"
    auto_universe_exclude_st_tag_1: bool = True
    auto_universe_size: int = 200
    auto_universe_min_symbols: int = 60
    auto_universe_refresh_sec: int = 180
    auto_universe_min_turnover_24h: float = 3_000_000.0
    auto_universe_min_raw_spread_bps: float = 0.0
    auto_universe_min_top_book_notional: float = 0.0
    bandit_enabled: bool = True
    bandit_epsilon: float = 0.05
    action_profiles: list[ActionProfileConfig] = Field(default_factory=list)

    # Bootstrap profile for spread admission filter.
    spread_window_sec: int = 60
    trade_window_sec: int = 300
    vol_window_sec: int = 60
    min_hold_seconds: int = 15
    cooldown_seconds: int = 60
    order_notional_quote: float = 50.0   # used by pair admission filter only
    max_order_notional_usdt: float = 10.0  # hard cap: no single order > this USDT value
    bootstrap_fee_entry_bps: float = 2.0
    bootstrap_fee_exit_bps: float = 2.0
    safety_buffer_bps: float = 0.5
    target_edge_bps: float = 1.0
    maker_only_entry: bool = True
    min_trades_per_min: float = 10.0
    max_p95_trade_gap_ms: int = 12000
    max_max_gap_ms: int = 30000
    depth_band_bps: float = 25.0
    min_depth_multiplier: float = 8.0
    max_total_slippage_bps: float = 4.0
    max_vol_to_spread_ratio: float = 1.2
    max_trade_silence_ms: int = 12000
    max_book_silence_ms: int = 5000
    spike_window_sec: int = 3
    spike_threshold_bps: float = 12.0
    spike_min_trades_per_min: float = 8.0
    spike_burst_enabled: bool = True
    spike_burst_slices: int = 4
    spike_burst_qty_scale: float = 0.25
    spike_burst_tick_step: int = 1
    spike_profile_id: str = "spike"
    spike_reversal_reverse: bool = True
    spike_reversal_taker: bool = True
    spike_reversal_min_strength_bps: float = 12.0
    spike_reversal_entry_offset_ticks: int = 1
    spike_reversal_qty_scale: float = 1.0
    spike_reversal_max_symbols: int = 40
    spike_reversal_cooldown_sec: float = 2.0
    strict_pair_filter: bool = True

    inventory: StrategyInventoryConfig = Field(default_factory=StrategyInventoryConfig)

    def get_action_profile(self, profile_id: str | None) -> ActionProfileConfig | None:
        if not profile_id:
            return None
        target = profile_id.strip()
        if not target:
            return None
        for profile in self.action_profiles:
            if profile.profile_id.strip() == target:
                return profile
        return None


class RiskConfig(BaseModel):
    initial_equity_usdt: float = 10000.0
    max_total_exposure_pct_of_initial: float = 2.0
    max_symbol_exposure_pct: float = 1.0
    max_orders_per_minute: int = 30
    max_open_positions: int = 0  # 0 = unlimited; set >0 to hard-cap simultaneous open positions
    default_leverage: float = 1.0  # leverage multiplier for linear/futures exposure checks


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


class MlConfig(BaseModel):
    mode: str = "bootstrap"  # bootstrap | train | predict | online
    enabled: bool = True
    run_interval_sec: int = 300
    model_dir: str = "data/models"
    train_limit_rows: int = 200000
    train_batch_size: int = 50
    min_closed_trades_to_train: int = 120
    min_fills_for_autocalibration: int = 20
    autocalibration_path: str = "data/ml/autocalibration.json"
    training_pause_flag_path: str = "data/ml/training.paused"
    predict_top_k: int = 10


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
    ml: MlConfig = Field(default_factory=MlConfig)

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
