"""
BacktestMixin — запуск бэктеста и получение символов для страницы Бэктест.

Зависит от:
  src/botik/backtest/backtest_runner.py — FuturesBacktestRunner / SpotBacktestRunner
  (может отсутствовать если параллельный агент ещё не создал файл — тогда graceful fallback)
"""
from __future__ import annotations

import logging
from typing import Any

from .api_helpers import _load_yaml, _resolve_db_path

log = logging.getLogger("botik.webview")

_FALLBACK_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
_VALID_SCOPES     = frozenset({"futures", "spot"})
_VALID_INTERVALS  = frozenset({"1", "5", "15", "60"})


class BacktestMixin:
    """Mixin providing backtest launch and symbol listing to DashboardAPI."""

    # ── Public API ────────────────────────────────────────────

    def run_backtest(
        self,
        scope: str,
        symbol: str,
        interval: str,
        days_back: int,
        balance: float = 10_000.0,
    ) -> dict[str, Any]:
        """Запускает бэктест синхронно, возвращает BacktestResult.to_dict().

        Args:
            scope:     "futures" | "spot"
            symbol:    торговая пара, напр. "BTCUSDT"
            interval:  "1" | "5" | "15" | "60"
            days_back: сколько дней назад начинать (7–365)
            balance:   стартовый баланс для расчёта (по умолчанию 10 000)

        Returns:
            dict с полями BacktestResult.to_dict() либо {"error": "..."} при сбое.
        """
        scope_str = str(scope).lower().strip()
        if scope_str not in _VALID_SCOPES:
            return {"error": f"invalid_scope: {scope_str}"}

        interval_str = str(interval).strip()
        if interval_str not in _VALID_INTERVALS:
            return {"error": f"invalid_interval: {interval_str}"}

        days_int = max(1, min(365, int(days_back)))
        symbol_str = str(symbol).upper().strip()
        balance_f = float(balance) if float(balance) > 0 else 10_000.0

        try:
            if scope_str == "futures":
                from src.botik.backtest.backtest_runner import FuturesBacktestRunner
                runner = FuturesBacktestRunner(
                    symbol=symbol_str,
                    interval=interval_str,
                    days_back=days_int,
                    balance=balance_f,
                )
            else:
                from src.botik.backtest.backtest_runner import SpotBacktestRunner
                runner = SpotBacktestRunner(
                    symbol=symbol_str,
                    interval=interval_str,
                    days_back=days_int,
                    balance=balance_f,
                )
        except ImportError as exc:
            log.warning("BacktestMixin: runner not available: %s", exc)
            return {"error": f"backtest_runner not available: {exc}"}
        except Exception as exc:
            log.error("BacktestMixin: runner init error: %s", exc)
            return {"error": str(exc)}

        try:
            result = runner.run()
            return result.to_dict()
        except Exception as exc:
            log.error("BacktestMixin: run error: %s", exc)
            return {"error": str(exc)}

    def get_backtest_symbols(self) -> list[str]:
        """Возвращает список активных символов из symbol_registry.

        Выполняет:  SELECT DISTINCT symbol FROM symbol_registry WHERE is_active=1
        Fallback при отсутствии таблицы или ошибке: стандартный список из 5 пар.
        """
        try:
            conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        except Exception:
            conn = None

        if conn is None:
            return list(_FALLBACK_SYMBOLS)

        try:
            if not self._table_exists(conn, "symbol_registry"):  # type: ignore[attr-defined]
                return list(_FALLBACK_SYMBOLS)

            cols = self._table_columns(conn, "symbol_registry")  # type: ignore[attr-defined]

            if "is_active" in cols:
                rows = conn.execute(
                    "SELECT DISTINCT symbol FROM symbol_registry "
                    "WHERE is_active = 1 ORDER BY symbol"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT symbol FROM symbol_registry ORDER BY symbol"
                ).fetchall()

            symbols = [str(r[0]) for r in rows if r[0]]
            return symbols if symbols else list(_FALLBACK_SYMBOLS)

        except Exception as exc:
            log.warning("BacktestMixin.get_backtest_symbols: %s", exc)
            return list(_FALLBACK_SYMBOLS)
        finally:
            try:
                conn.close()
            except Exception:
                pass
