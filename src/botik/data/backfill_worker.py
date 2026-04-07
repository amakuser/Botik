"""
BackfillWorker — исторический сбор OHLCV данных (M1.3).

Читает SymbolRegistry чтобы понять что качать.
Делегирует HTTP-запросы OHLCVWorker.
После каждого символа обновляет SymbolRegistry (candle_count, data_status).

Не знает ничего про модели, разметку или обучение.
Не содержит хардкодированных символов — всё из registry.

Таймфреймы по умолчанию: 1m, 5m, 15m, 1h
Глубина истории: максимально доступная (с 2020 для BTC, 2021+ для остальных)

Использование:
    from src.botik.storage.db import get_db
    from src.botik.data.symbol_registry import SymbolRegistry
    from src.botik.data.backfill_worker import BackfillWorker

    registry = SymbolRegistry(get_db())
    worker = BackfillWorker(registry)
    await worker.run_all()          # качает всё что нужно
    await worker.run_symbol("BTCUSDT", "linear")  # один символ
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import json
import sqlite3

from src.botik.data.symbol_registry import SymbolRegistry, MIN_CANDLES_READY
from src.botik.marketdata.ohlcv_worker import OHLCVWorker

log = logging.getLogger("botik.data.backfill_worker")

# Таймфреймы по умолчанию — причинно-следственный контекст от 1m до 1h
DEFAULT_INTERVALS: tuple[str, ...] = ("1", "5", "15", "60")

# Сколько лет истории качать (Bybit хранит с 2020-03-25 для BTC)
DEFAULT_DAYS_BACK: int = 365 * 6   # 6 лет

# Минимум свечей для перехода в статус 'ready'
MIN_CANDLES: int = MIN_CANDLES_READY

# Пауза между запросами к Bybit — не превышать rate limit
REQUEST_DELAY_SEC: float = 0.15


# ─────────────────────────────────────────────────────────────────────────────
#  Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SymbolBackfillResult:
    """Result of backfilling one (symbol, category, interval) combination."""

    symbol: str
    category: str
    interval: str
    candles_added: int
    total_candles: int
    elapsed_sec: float
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class BackfillReport:
    """Aggregated result of a full backfill run."""

    results: list[SymbolBackfillResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    @property
    def total_added(self) -> int:
        return sum(r.candles_added for r in self.results)

    @property
    def failed(self) -> list[SymbolBackfillResult]:
        return [r for r in self.results if not r.success]

    @property
    def succeeded(self) -> list[SymbolBackfillResult]:
        return [r for r in self.results if r.success]

    def summary_lines(self) -> list[str]:
        lines = [
            f"Backfill finished: {len(self.succeeded)} ok, "
            f"{len(self.failed)} failed, "
            f"{self.total_added} new candles total",
        ]
        for r in self.failed:
            lines.append(f"  FAILED {r.symbol}/{r.category}/{r.interval}: {r.error}")
        return lines


# ─────────────────────────────────────────────────────────────────────────────
#  BackfillWorker
# ─────────────────────────────────────────────────────────────────────────────

class BackfillWorker:
    """
    Downloads historical OHLCV candles for all symbols in SymbolRegistry
    that don't yet have enough data (candle_count < MIN_CANDLES_READY).

    After each symbol completes, updates SymbolRegistry so the pipeline
    knows which symbols are ready for the next stage (TrainingPipeline).
    """

    def __init__(
        self,
        registry: SymbolRegistry,
        intervals: Sequence[str] = DEFAULT_INTERVALS,
        days_back: int = DEFAULT_DAYS_BACK,
    ) -> None:
        self._registry = registry
        self._intervals = list(intervals)
        self._days_back = days_back
        self._ohlcv = OHLCVWorker()
        self._running = False
        # resolved lazily from DB URL env var
        self._db_path: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_all(self) -> BackfillReport:
        """
        Backfill all symbols in the registry that need more candles.
        Processes each (symbol, category) for all configured intervals.
        """
        report = BackfillReport(started_at=_now_utc())
        self._running = True

        symbols_needing_data = self._registry.get_needing_backfill()
        if not symbols_needing_data:
            log.info("BackfillWorker: all symbols are up to date, nothing to do")
            report.finished_at = _now_utc()
            return report

        # Unique (symbol, category) pairs — same pair may appear for each interval
        pairs: list[tuple[str, str]] = list({
            (r.symbol, r.category) for r in symbols_needing_data
        })

        total_pairs = len(pairs)
        log.info(
            "BackfillWorker: starting for %d symbol(s), intervals=%s, days_back=%d",
            total_pairs, self._intervals, self._days_back,
        )

        for idx, (symbol, category) in enumerate(pairs):
            if not self._running:
                log.info("BackfillWorker: stopped by request")
                break
            self._write_progress(symbol, category, None, idx, total_pairs)
            for interval in self._intervals:
                if not self._running:
                    break
                self._write_progress(symbol, category, interval, idx, total_pairs)
                result = await self._backfill_one(symbol, category, interval)
                report.results.append(result)
                if result.success:
                    log.info(
                        "  %s/%s/%s: +%d candles (total %d) in %.1fs",
                        symbol, category, interval,
                        result.candles_added, result.total_candles,
                        result.elapsed_sec,
                    )
                else:
                    log.warning(
                        "  %s/%s/%s: FAILED — %s",
                        symbol, category, interval, result.error,
                    )

        report.finished_at = _now_utc()
        self._running = False
        self._write_progress(None, None, None, total_pairs, total_pairs, done=True)

        for line in report.summary_lines():
            log.info(line)

        return report

    async def run_symbol(
        self,
        symbol: str,
        category: str,
        intervals: Sequence[str] | None = None,
    ) -> list[SymbolBackfillResult]:
        """
        Backfill a specific symbol across all intervals.
        Registers the symbol in the registry if not already present.
        """
        use_intervals = list(intervals) if intervals else self._intervals
        results: list[SymbolBackfillResult] = []

        for interval in use_intervals:
            # Register if not present (idempotent)
            self._registry.register(symbol, category, interval)
            result = await self._backfill_one(symbol, category, interval)
            results.append(result)

        return results

    def stop(self) -> None:
        """Signal the worker to stop after the current request completes."""
        self._running = False
        log.info("BackfillWorker: stop requested")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _backfill_one(
        self,
        symbol: str,
        category: str,
        interval: str,
    ) -> SymbolBackfillResult:
        """
        Download historical candles for one (symbol, category, interval).
        Updates SymbolRegistry on success.
        """
        t_start = time.monotonic()
        try:
            candles_added = await self._ohlcv.backfill(
                symbol=symbol,
                category=category,
                interval=interval,
                days_back=self._days_back,
            )
            await asyncio.sleep(REQUEST_DELAY_SEC)

            total = self._ohlcv.get_candle_count(symbol, category, interval)
            last_ms = self._get_last_candle_ms(symbol, category, interval)

            self._registry.update_candle_stats(
                symbol=symbol,
                category=category,
                interval=interval,
                candle_count=total,
                last_candle_ms=last_ms,
                last_backfill_at=_now_utc(),
            )

            return SymbolBackfillResult(
                symbol=symbol,
                category=category,
                interval=interval,
                candles_added=candles_added,
                total_candles=total,
                elapsed_sec=time.monotonic() - t_start,
            )

        except Exception as exc:
            log.error(
                "BackfillWorker._backfill_one %s/%s/%s failed: %s",
                symbol, category, interval, exc,
            )
            return SymbolBackfillResult(
                symbol=symbol,
                category=category,
                interval=interval,
                candles_added=0,
                total_candles=0,
                elapsed_sec=time.monotonic() - t_start,
                error=str(exc),
            )

    def _get_db_path(self) -> str | None:
        """Resolve SQLite path from DB_URL env var (set by webview_app.main)."""
        if self._db_path:
            return self._db_path
        import os
        url = os.environ.get("DB_URL", "")
        if url.startswith("sqlite:///"):
            self._db_path = url[len("sqlite:///"):]
            return self._db_path
        return None

    def _write_progress(
        self,
        symbol: str | None,
        category: str | None,
        interval: str | None,
        processed: int,
        total: int,
        done: bool = False,
    ) -> None:
        """Write current backfill progress to bot_settings table (for UI display)."""
        db_path = self._get_db_path()
        if not db_path:
            return
        payload = json.dumps({
            "symbol":    symbol,
            "category":  category,
            "interval":  interval,
            "processed": processed,
            "total":     total,
            "done":      done,
            "updated_at": _now_utc(),
        })
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            conn.execute(
                "INSERT INTO bot_settings (key, value, is_secret) VALUES (?, ?, 0) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("backfill_progress", payload),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            log.debug("BackfillWorker._write_progress failed: %s", exc)

    def _get_last_candle_ms(
        self,
        symbol: str,
        category: str,
        interval: str,
    ) -> int | None:
        """Read the timestamp of the most recent candle from price_history."""
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT MAX(open_time_ms) FROM price_history "
                    "WHERE symbol=? AND category=? AND interval=?",
                    (symbol, category, interval),
                ).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
