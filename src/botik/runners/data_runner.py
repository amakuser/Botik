"""
DataRunner — сборщик рыночных данных и запуск ML обучения.

Запускается как отдельный процесс:
  python -m src.botik.runners.data_runner

Фазы работы:
  1. BACKFILL — качает историю OHLCV за BACKFILL_DAYS дней для всех символов
               (linear + spot категории)
  2. BOOTSTRAP — запускает ModelTrainer.bootstrap() для futures и spot
               (только если набрано достаточно данных)
  3. REFRESH  — каждые REFRESH_INTERVAL_SEC обновляет последние свечи

Переменные окружения:
  BYBIT_HOST           — api-demo.bybit.com (default)
  DATA_SYMBOLS         — BTCUSDT,ETHUSDT,SOLUSDT (default)
  DATA_BACKFILL_DAYS   — 30 (default)
  DATA_INTERVAL        — 1 (минуты, default)
  DATA_REFRESH_SEC     — 60 (default)
  DATA_SKIP_BOOTSTRAP  — 1 чтобы пропустить ML обучение (для быстрого теста)
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

from src.botik.storage.schema import bootstrap_db
from src.botik.storage.db import get_db
from src.botik.marketdata.ohlcv_worker import OHLCVWorker

log = logging.getLogger("botik.runners.data")

# ── Конфиг ────────────────────────────────────────────────────
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SYMBOLS = [s.strip() for s in os.environ.get("DATA_SYMBOLS", "").split(",") if s.strip()] \
          or DEFAULT_SYMBOLS

BACKFILL_DAYS    = int(os.environ.get("DATA_BACKFILL_DAYS", "30"))
INTERVAL         = os.environ.get("DATA_INTERVAL", "1")
REFRESH_SEC      = int(os.environ.get("DATA_REFRESH_SEC", "60"))
SKIP_BOOTSTRAP   = os.environ.get("DATA_SKIP_BOOTSTRAP", "") == "1"

# Категории: linear (фьючерсы) + spot
CATEGORIES = ["linear", "spot"]

# Минимум свечей для запуска bootstrap
MIN_CANDLES_FOR_BOOTSTRAP = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_app_log(msg: str, channel: str = "sys") -> None:
    try:
        db = get_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, created_at_utc) "
                "VALUES (?, 'INFO', ?, ?)",
                (channel, msg, _utc_now()),
            )
    except Exception:
        pass


class DataRunner:
    """
    Оркестрирует сбор OHLCV данных и ML обучение.
    """

    def __init__(self) -> None:
        self.worker = OHLCVWorker()
        self._running = True

    # ── Main entry ────────────────────────────────────────────

    async def run(self) -> None:
        log.info(
            "DataRunner start: symbols=%s interval=%s backfill=%dd",
            SYMBOLS, INTERVAL, BACKFILL_DAYS,
        )
        _write_app_log(
            f"DataRunner start: symbols={SYMBOLS} backfill={BACKFILL_DAYS}d"
        )

        try:
            # Фаза 1: backfill истории
            await self._phase_backfill()

            # Фаза 2: ML bootstrap (если достаточно данных)
            if not SKIP_BOOTSTRAP:
                await self._phase_bootstrap()

            # Фаза 3: непрерывное обновление
            await self._phase_refresh()

        finally:
            await self.worker.close()

    def stop(self) -> None:
        self._running = False
        log.info("DataRunner stopping...")

    # ── Phases ────────────────────────────────────────────────

    async def _phase_backfill(self) -> None:
        """Фаза 1: качаем историю для всех символов и категорий."""
        log.info("=== PHASE 1: BACKFILL ===")
        _write_app_log("DataRunner: начинаем backfill истории", "ml")

        total = 0
        for symbol in SYMBOLS:
            if not self._running:
                break
            for category in CATEGORIES:
                if not self._running:
                    break

                existing = self.worker.get_candle_count(symbol, category, INTERVAL)
                if existing >= BACKFILL_DAYS * 24 * 60 * 0.8:
                    log.info(
                        "Skip backfill %s/%s — уже %d свечей",
                        symbol, category, existing,
                    )
                    continue

                log.info("Backfill %s/%s...", symbol, category)
                saved = await self.worker.backfill(
                    symbol=symbol,
                    category=category,
                    interval=INTERVAL,
                    days_back=BACKFILL_DAYS,
                )
                total += saved
                _write_app_log(
                    f"Backfill {symbol}/{category}: +{saved} свечей",
                    "ml",
                )

        log.info("=== BACKFILL DONE: %d свечей сохранено ===", total)
        _write_app_log(f"Backfill завершён: итого {total} свечей", "ml")

    async def _phase_bootstrap(self) -> None:
        """Фаза 2: ML bootstrap если данных достаточно."""
        log.info("=== PHASE 2: ML BOOTSTRAP ===")

        # Проверяем что данных достаточно
        total_candles = 0
        for symbol in SYMBOLS:
            total_candles += self.worker.get_candle_count(symbol, "linear", INTERVAL)

        if total_candles < MIN_CANDLES_FOR_BOOTSTRAP:
            log.warning(
                "Bootstrap пропущен: только %d свечей (нужно >= %d)",
                total_candles, MIN_CANDLES_FOR_BOOTSTRAP,
            )
            _write_app_log(
                f"Bootstrap пропущен: {total_candles} свечей < {MIN_CANDLES_FOR_BOOTSTRAP}",
                "ml",
            )
            return

        log.info("Запускаем ML bootstrap: %d свечей доступно", total_candles)
        _write_app_log(f"ML bootstrap start: {total_candles} свечей", "ml")

        # Импортируем здесь чтобы не замедлять старт если sklearn не установлен
        try:
            from src.botik.ml.trainer import ModelTrainer
        except ImportError as exc:
            log.error("ML trainer недоступен: %s", exc)
            return

        # Futures bootstrap
        try:
            log.info("Bootstrap futures...")
            trainer_futures = ModelTrainer(model_scope="futures")
            result = trainer_futures.bootstrap(symbols=SYMBOLS, interval=INTERVAL)
            deployed = result.get("deployed", False)
            samples  = result.get("samples", 0)
            hist_acc = result.get("historian_accuracy", 0.0)
            pred_acc = result.get("predictor_accuracy", 0.0)
            msg = (
                f"Bootstrap futures: samples={samples} "
                f"hist_acc={hist_acc:.3f} pred_acc={pred_acc:.3f} "
                f"deployed={deployed}"
            )
            log.info(msg)
            _write_app_log(msg, "ml")
        except Exception as exc:
            log.error("Bootstrap futures error: %s", exc)
            _write_app_log(f"Bootstrap futures error: {exc}", "ml")

        # Spot bootstrap
        try:
            log.info("Bootstrap spot...")
            trainer_spot = ModelTrainer(model_scope="spot")
            result = trainer_spot.bootstrap(symbols=SYMBOLS, interval=INTERVAL)
            deployed = result.get("deployed", False)
            samples  = result.get("samples", 0)
            msg = (
                f"Bootstrap spot: samples={samples} "
                f"deployed={deployed}"
            )
            log.info(msg)
            _write_app_log(msg, "ml")
        except Exception as exc:
            log.error("Bootstrap spot error: %s", exc)
            _write_app_log(f"Bootstrap spot error: {exc}", "ml")

        log.info("=== ML BOOTSTRAP DONE ===")

    async def _phase_refresh(self) -> None:
        """Фаза 3: каждые REFRESH_SEC обновляем последние свечи."""
        log.info("=== PHASE 3: CONTINUOUS REFRESH (every %ds) ===", REFRESH_SEC)
        _write_app_log(f"DataRunner: непрерывное обновление каждые {REFRESH_SEC}с")

        while self._running:
            t_start = time.monotonic()

            for symbol in SYMBOLS:
                if not self._running:
                    break
                for category in CATEGORIES:
                    try:
                        saved = await self.worker.fetch_recent(
                            symbol=symbol,
                            category=category,
                            interval=INTERVAL,
                            limit=5,   # только последние 5 свечей — быстро
                        )
                        if saved > 0:
                            log.debug("Refresh %s/%s: +%d", symbol, category, saved)
                    except Exception as exc:
                        log.debug("Refresh %s/%s error: %s", symbol, category, exc)

            elapsed = time.monotonic() - t_start
            sleep_for = max(0.0, REFRESH_SEC - elapsed)
            await asyncio.sleep(sleep_for)

    # ── CLI: разовый backfill ──────────────────────────────────

    @classmethod
    async def run_once(cls, symbols: list[str], days_back: int) -> None:
        """Запускает только backfill + bootstrap, без непрерывного обновления."""
        runner = cls()
        runner._running = True
        try:
            await runner._phase_backfill()
            if not SKIP_BOOTSTRAP:
                await runner._phase_bootstrap()
        finally:
            await runner.worker.close()


# ── Entry point ───────────────────────────────────────────────

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bootstrap_db()

    runner = DataRunner()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except (NotImplementedError, OSError):
            pass

    await runner.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Botik Data Runner")
    parser.add_argument("--symbols", default="", help="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--days", type=int, default=BACKFILL_DAYS, help="Дней истории")
    parser.add_argument("--once", action="store_true", help="Только backfill, без loop")
    parser.add_argument("--skip-bootstrap", action="store_true", help="Пропустить ML обучение")
    args = parser.parse_args()

    if args.symbols:
        SYMBOLS[:] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.skip_bootstrap:
        os.environ["DATA_SKIP_BOOTSTRAP"] = "1"

    if args.once:
        asyncio.run(DataRunner.run_once(SYMBOLS, args.days))
    else:
        asyncio.run(_main())
