# -*- coding: utf-8 -*-
"""
Менеджер ордеров (Python).

Проверяет дневные лимиты (RuleEngine), корректирует размер позиции по win rate,
отправляет ордера через BybitClient (или только пишет в БД при dry_run),
записывает сделки в SQLite и по счётчику запускает переобучение ML.
"""
import logging
from pathlib import Path
from typing import Any, Optional

from strategies.base import Signal

from stats.rule_engine import RuleEngine
from stats import storage as stats_storage

log = logging.getLogger("OrderManager")


class OrderManager:
    """
    Исполнение сигналов: проверка лимитов -> расчёт размера -> ордер (или dry_run) -> запись в БД.
    Клиент Bybit задаётся через set_client() из main.
    """

    def __init__(
        self,
        config: dict[str, Any],
        daily_limits: dict[str, Any],
        bybit_settings: dict[str, Any],
        db_path: str,
        dry_run: bool = True,
    ) -> None:
        self.config = config
        self.daily_limits = daily_limits
        self.bybit_settings = bybit_settings
        self.db_path = db_path
        self.dry_run = dry_run
        self._client: Any = None
        self._rule_engine = RuleEngine(db_path, daily_limits)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def set_client(self, client: Any) -> None:
        self._client = client

    def can_open_trade(self, symbol: str, strategy_id: str) -> tuple[bool, str]:
        """Разрешена ли новая сделка с учётом дневных лимитов (убыток, прибыль, кол-во)."""
        return self._rule_engine.can_open_trade(symbol, strategy_id)

    def _size_with_rules(self, signal: Signal, base_size: float) -> float:
        """Умножить размер на множитель из правил (win rate по стратегии)."""
        mult = self._rule_engine.get_position_size_multiplier(signal.strategy_id)
        return base_size * mult

    def apply_signal(self, signal: Signal, market_data: Any) -> bool:
        """Исполнить сигнал: проверка лимитов -> размер -> ордер/запись. True если исполнено."""
        symbol = getattr(market_data, "symbol", "BTCUSDT")
        price = getattr(market_data, "price", 0.0) or 0.0
        allowed, reason = self.can_open_trade(symbol, signal.strategy_id)
        if not allowed:
            log.warning("Blocked by limits: %s", reason)
            return False

        size = self._size_with_rules(signal, signal.size)
        qty = size / price if price else 0
        if qty <= 0:
            return False

        if self.dry_run:
            log.info("DRY-RUN: would apply signal %s (qty=%.6f)", signal, qty)
            stats_storage.record_trade(
                self.db_path, symbol, signal.strategy_id,
                side="Buy" if signal.direction == "long" else "Sell",
                qty=qty, price=price, extra={"dry_run": True},
            )
            self._maybe_retrain_ml()
            return True

        if not self._client:
            log.warning("No Bybit client; skipping order")
            return False

        side = "Buy" if signal.direction == "long" else "Sell"
        result = self._client.place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            take_profit=signal.take_profit,
            stop_loss=signal.stop_loss,
        )
        ret_code = result.get("retCode") or result.get("ret_code")
        if ret_code and ret_code != 0:
            log.error("Place order failed: %s", result)
            return False
        stats_storage.record_trade(
            self.db_path, symbol, signal.strategy_id,
            side=side, qty=qty, price=price,
        )
        self._maybe_retrain_ml()
        return True

    def _maybe_retrain_ml(self) -> None:
        """Раз в retrain_after_trades сделок запустить ML pipeline (обучение по истории)."""
        ml_cfg = self.config.get("ml") or {}
        if not ml_cfg.get("enabled"):
            return
        retrain_after = ml_cfg.get("retrain_after_trades", 50)
        try:
            n = stats_storage.get_today_trade_count(self.db_path) + len(
                stats_storage.get_trades_for_ml(self.db_path, limit=1)
            )
        except Exception:
            return
        if n > 0 and n % retrain_after == 0:
            try:
                from ml.pipeline import run_pipeline
                run_pipeline(
                    self.db_path,
                    ml_cfg.get("model_path", "data/model.pkl"),
                    retrain_after_trades=retrain_after,
                )
            except Exception as e:
                log.debug("ML retrain: %s", e)
