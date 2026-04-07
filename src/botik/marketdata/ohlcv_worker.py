"""
OHLCVWorker — накачка исторических и текущих OHLCV данных из Bybit.

Использует публичный REST endpoint /v5/market/kline — авторизация не нужна.
Bybit отдаёт максимум 1000 свечей за запрос. Для backfill пагинируем по времени.

Режимы:
  backfill(symbol, category, interval, days_back=30)
    → Тянет данные за N дней, пишет в price_history (UPSERT)
    → Возвращает кол-во новых свечей

  fetch_recent(symbol, category, interval, limit=200)
    → Забирает последние N свечей (непрерывное обновление)

Формат свечи Bybit /v5/market/kline:
  [openTimeMs, open, high, low, close, volume, turnover]

Переменные окружения:
  BYBIT_HOST — api-demo.bybit.com (default) | api.bybit.com
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

log = logging.getLogger("botik.marketdata.ohlcv_worker")

BYBIT_HOST = os.environ.get("BYBIT_HOST", "api-demo.bybit.com")
BASE_URL = f"https://{BYBIT_HOST}"
KLINE_LIMIT = 1000          # максимум Bybit за один запрос
REQUEST_DELAY = 0.25        # пауза между запросами (не бить по rate limit)
MS_PER_MIN = 60_000


def _interval_to_ms(interval: str) -> int:
    """Конвертирует interval Bybit в миллисекунды на свечу."""
    table = {
        "1": 60_000, "3": 180_000, "5": 300_000,
        "15": 900_000, "30": 1_800_000,
        "60": 3_600_000, "120": 7_200_000, "240": 14_400_000,
        "360": 21_600_000, "720": 43_200_000,
        "D": 86_400_000, "W": 604_800_000,
    }
    return table.get(str(interval), 60_000)


class OHLCVWorker:
    """
    Загружает OHLCV свечи из Bybit и сохраняет в таблицу price_history.

    Использование:
      worker = OHLCVWorker()
      saved = await worker.backfill("BTCUSDT", "linear", "1", days_back=30)
      saved += await worker.fetch_recent("BTCUSDT", "linear", "1", limit=100)
    """

    def __init__(self) -> None:
        self._session = None   # aiohttp.ClientSession — создаётся при первом запросе

    # ── Public API ────────────────────────────────────────────

    async def backfill(
        self,
        symbol: str,
        category: str,
        interval: str = "1",
        days_back: int = 30,
    ) -> int:
        """
        Загружает исторические свечи за последние days_back дней.
        Пагинирует запросами по 1000 свечей.
        Возвращает кол-во сохранённых свечей.
        """
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - days_back * 24 * 60 * 60 * 1000
        interval_ms = _interval_to_ms(interval)

        total_saved = 0
        current_start = start_ms

        log.info("Backfill %s/%s interval=%s days=%d", symbol, category, interval, days_back)

        while current_start < now_ms:
            candles = await self._fetch_kline(
                symbol=symbol,
                category=category,
                interval=interval,
                start_ms=current_start,
                limit=KLINE_LIMIT,
            )
            if not candles:
                break

            saved = self._save_candles(candles, symbol, category, interval)
            total_saved += saved

            # Следующий диапазон: после последней полученной свечи
            last_ts = int(candles[-1][0])
            next_start = last_ts + interval_ms
            if next_start <= current_start:
                break   # защита от зависания
            current_start = next_start

            if len(candles) < KLINE_LIMIT:
                break   # получили меньше максимума — это конец истории

            await asyncio.sleep(REQUEST_DELAY)

        log.info("Backfill done: %s/%s → %d свечей сохранено", symbol, category, total_saved)
        return total_saved

    async def fetch_recent(
        self,
        symbol: str,
        category: str,
        interval: str = "1",
        limit: int = 200,
    ) -> int:
        """
        Забирает последние N свечей. Используется для непрерывного обновления.
        Возвращает кол-во новых (несохранённых ранее) свечей.
        """
        candles = await self._fetch_kline(
            symbol=symbol,
            category=category,
            interval=interval,
            limit=min(limit, KLINE_LIMIT),
        )
        if not candles:
            return 0
        return self._save_candles(candles, symbol, category, interval)

    async def close(self) -> None:
        """Закрывает HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Internal ──────────────────────────────────────────────

    async def _get_session(self):
        """Lazy-инициализация aiohttp.ClientSession."""
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError("aiohttp не установлен: pip install aiohttp")
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _fetch_kline(
        self,
        symbol: str,
        category: str,
        interval: str,
        limit: int = KLINE_LIMIT,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[list[Any]]:
        """
        GET /v5/market/kline
        Возвращает список свечей вида [openTimeMs, open, high, low, close, volume, turnover].
        Bybit отдаёт в порядке убывания времени — переворачиваем.
        """
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms

        url = f"{BASE_URL}/v5/market/kline"
        try:
            session = await self._get_session()
            import aiohttp
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        except Exception as exc:
            log.warning("_fetch_kline %s/%s error: %s", symbol, category, exc)
            return []

        if data.get("retCode") != 0:
            log.debug("kline retCode=%s for %s: %s", data.get("retCode"), symbol, data.get("retMsg"))
            return []

        raw_list = data.get("result", {}).get("list", [])
        if not raw_list:
            return []

        # Bybit отдаёт в порядке убывания → переворачиваем (старые → новые)
        return list(reversed(raw_list))

    def _save_candles(
        self,
        candles: list[list[Any]],
        symbol: str,
        category: str,
        interval: str,
    ) -> int:
        """
        Сохраняет список свечей в price_history.
        Использует INSERT OR IGNORE — дубликаты молча пропускаются.
        Возвращает кол-во вставленных строк.
        Использует executemany для пакетной вставки вместо цикла.
        """
        if not candles:
            return 0

        rows = []
        for c in candles:
            try:
                open_time_ms = int(c[0])
                open_p  = float(c[1])
                high    = float(c[2])
                low     = float(c[3])
                close   = float(c[4])
                volume  = float(c[5])
                turnover = float(c[6]) if len(c) > 6 else 0.0
            except (IndexError, ValueError, TypeError):
                continue
            if close <= 0:
                continue
            rows.append((symbol, category, interval, open_time_ms,
                         open_p, high, low, close, volume, turnover))

        if not rows:
            return 0

        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                cur = conn.executemany(
                    """
                    INSERT OR IGNORE INTO price_history
                      (symbol, category, interval, open_time_ms,
                       open, high, low, close, volume, turnover)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                # rowcount is accumulated across all executemany statements
                return max(0, cur.rowcount)
        except Exception as exc:
            log.error("_save_candles DB error: %s", exc)
            return 0

    def get_candle_count(self, symbol: str, category: str, interval: str) -> int:
        """Возвращает кол-во свечей в БД для данного символа."""
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM price_history WHERE symbol=? AND category=? AND interval=?",
                    (symbol, category, interval),
                ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
