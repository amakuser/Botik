"""
FuturesRunner — asyncio цикл для фьючерсной paper-торговли.

Запускается как отдельный процесс через ManagedProcess в webview_app.py:
  python -m src.botik.runners.futures_runner

Жизненный цикл:
  1. bootstrap_db() — применяем миграции
  2. WebSocket подписка на orderbook + trades (публичный WS, demo данные)
  3. Каждый тик → strategy.get_intents() → sizer.calc_qty() → engine.open_position()
  4. Каждый тик → engine.on_price_tick() → policy решает выход
  5. Каждые 60с → сохраняем stats в app_logs

Переменные окружения:
  BYBIT_HOST  — api-demo.bybit.com (default) | api.bybit.com
  FUTURES_SYMBOLS — BTCUSDT,ETHUSDT (default)
  FUTURES_TIMEFRAME — 1 (default, минуты)
  FUTURES_BALANCE  — виртуальный баланс USDT (default 10000)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path when run as __main__
_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)
except ImportError:
    pass  # python-dotenv необязателен — можно задавать переменные окружения напрямую

from src.botik.storage.schema import bootstrap_db
from src.botik.storage.db import get_db
from src.botik.execution.futures_paper import FuturesPaperEngine
from src.botik.position.sizer import PositionSizer, calc_atr
from src.botik.position.simple_exit import SimpleExitPolicy
from src.botik.strategy.futures_spike_reversal import FuturesSpikeReversalStrategy
from src.botik.ml.trainer import ModelTrainer
from src.botik.ml.labeler import Labeler

log = logging.getLogger("botik.runners.futures")

# ── Конфиг из env ─────────────────────────────────────────────
BYBIT_HOST = os.environ.get("BYBIT_HOST", "api-demo.bybit.com")
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SYMBOLS = [s.strip() for s in os.environ.get("FUTURES_SYMBOLS", "").split(",") if s.strip()] \
          or DEFAULT_SYMBOLS
BALANCE         = float(os.environ.get("FUTURES_BALANCE",        "10000"))
# Strategy params (RISK_PCT, MAX_POS_PCT stored as percent in .env: "1.0" = 1%)
RISK_PCT        = float(os.environ.get("FUTURES_RISK_PCT",        "1.0"))  / 100
ATR_SL_MULT     = float(os.environ.get("FUTURES_ATR_SL_MULT",     "1.5"))
ATR_TP_MULT     = float(os.environ.get("FUTURES_ATR_TP_MULT",     "2.5"))
MAX_POS_PCT     = float(os.environ.get("FUTURES_MAX_POS_PCT",     "15"))   / 100
HOLD_TIMEOUT_H  = float(os.environ.get("FUTURES_HOLD_TIMEOUT_H",  "4"))
SPIKE_BPS       = float(os.environ.get("FUTURES_SPIKE_BPS",       "80"))
MAX_POSITIONS   = int(  os.environ.get("FUTURES_MAX_POSITIONS",   "3"))
WS_URL = f"wss://{BYBIT_HOST}/v5/public/linear"
LOG_INTERVAL_SEC = 60
RECONNECT_DELAY_SEC = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_app_log(msg: str, channel: str = "futures") -> None:
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


class FuturesRunner:
    """
    Главный класс runner-а. Управляет WS соединением и торговым циклом.
    """

    def __init__(self) -> None:
        self.engine = FuturesPaperEngine(
            policy=SimpleExitPolicy(hold_timeout_ms=int(HOLD_TIMEOUT_H * 3600 * 1000)),
            model_scope="futures",
        )
        self.sizer = PositionSizer(
            risk_pct=RISK_PCT,
            atr_sl_mult=ATR_SL_MULT,
            atr_tp_mult=ATR_TP_MULT,
            max_position_pct=MAX_POS_PCT,
        )
        # ML: загружаем модели если обучены
        self._trainer = ModelTrainer(model_scope="futures")
        self._labeler = Labeler(model_scope="futures")
        predict_fn = self._trainer.get_predict_fn()   # None если не обучены

        self.strategy = FuturesSpikeReversalStrategy(
            spike_threshold_bps=SPIKE_BPS,
            max_open_positions=MAX_POSITIONS,
            model_predict_fn=predict_fn,
        )
        if predict_fn:
            log.info("ML модель подключена к стратегии (predictor is_ready=True)")
        else:
            log.info("ML модель не обучена — стратегия работает по правилам")

        self._closed_since_retrain = 0

        # Буфер последних цен для ATR (symbol → list of (high, low, close))
        self._price_buf: dict[str, list[tuple[float, float, float]]] = {
            s: [] for s in SYMBOLS
        }
        self._last_price: dict[str, float] = {}
        self._running = True
        self._last_stats_ts = 0.0

    # ── Main entry ────────────────────────────────────────────

    async def run(self) -> None:
        log.info("FuturesRunner starting. Symbols: %s  Host: %s", SYMBOLS, BYBIT_HOST)
        _write_app_log(f"FuturesRunner start. symbols={SYMBOLS}")

        while self._running:
            try:
                await self._ws_loop()
            except Exception as exc:
                log.warning("WS loop error, reconnect in %ds: %s", RECONNECT_DELAY_SEC, exc)
                _write_app_log(f"WS reconnect: {exc}", "futures")
                await asyncio.sleep(RECONNECT_DELAY_SEC)

    async def _ws_loop(self) -> None:
        """WebSocket цикл. При разрыве — вызывается снова из run()."""
        try:
            import websockets
        except ImportError:
            log.error("websockets не установлен: pip install websockets")
            await asyncio.sleep(30)
            return

        async with websockets.connect(WS_URL, ping_interval=20) as ws:
            log.info("WS connected: %s", WS_URL)
            await self._subscribe(ws)

            async for raw in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    await self._handle_message(msg)
                except Exception as exc:
                    log.debug("message parse error: %s", exc)

    async def _subscribe(self, ws) -> None:
        """Подписываемся на orderbook и kline для каждого символа."""
        topics = []
        for sym in SYMBOLS:
            topics.append(f"orderbook.50.{sym}")
            topics.append(f"kline.1.{sym}")        # 1-минутные свечи

        await ws.send(json.dumps({
            "op": "subscribe",
            "args": topics,
        }))
        log.info("Subscribed to %d topics", len(topics))

    async def _handle_message(self, msg: dict) -> None:
        topic = msg.get("topic", "")
        data = msg.get("data", {})

        if topic.startswith("kline."):
            # kline.1.BTCUSDT
            symbol = topic.split(".")[-1]
            await self._on_kline(symbol, data)

        elif topic.startswith("orderbook."):
            symbol = topic.split(".")[-1]
            await self._on_orderbook(symbol, data)

    async def _on_kline(self, symbol: str, data) -> None:
        """Обновляем ценовой буфер и запускаем торговый цикл."""
        candles = data if isinstance(data, list) else [data]
        for candle in candles:
            h = float(candle.get("high", 0))
            lo = float(candle.get("low", 0))
            c = float(candle.get("close", 0))
            if c <= 0:
                continue

            buf = self._price_buf.setdefault(symbol, [])
            buf.append((h, lo, c))
            if len(buf) > 50:
                buf.pop(0)

            self._last_price[symbol] = c

            # Проверяем выход из открытых позиций
            closed = self.engine.on_price_tick(symbol, c)
            for trade in closed:
                msg = (f"CLOSED {symbol} {trade['side'].upper()} "
                       f"exit={trade['exit_price']:.4f} "
                       f"pnl={trade['net_pnl']:+.4f} [{trade['exit_reason']}]")
                log.info(msg)
                _write_app_log(msg, "futures")

                # Передаём результат в OutcomeLearner
                updated = self._trainer.outcome_learner.record_trade(
                    net_pnl=trade["net_pnl"],
                    exit_reason=trade["exit_reason"],
                )
                self._closed_since_retrain += 1

                # Автоматическое инкрементальное переобучение
                if updated or self._closed_since_retrain >= 50:
                    log.info("Запускаем инкрементальное переобучение...")
                    _write_app_log("Incremental retrain triggered", "ml")
                    result = self._trainer.incremental()
                    self._closed_since_retrain = 0
                    # Обновляем predict_fn в стратегии
                    new_fn = self._trainer.get_predict_fn()
                    if new_fn:
                        self.strategy.model_predict_fn = new_fn
                        log.info("ML predict_fn обновлена (acc=%.3f)",
                                 result.get("predictor_accuracy", 0))

        # Периодический лог статистики
        now = time.monotonic()
        if now - self._last_stats_ts > LOG_INTERVAL_SEC:
            self._last_stats_ts = now
            stats = self.engine.get_stats()
            _write_app_log(
                f"stats: trades={stats.get('total',0)} "
                f"wins={stats.get('wins',0)} "
                f"win_rate={stats.get('win_rate',0.0):.1f}% "
                f"total_pnl={stats.get('total_pnl',0.0):+.2f}",
                "futures",
            )

    async def _on_orderbook(self, symbol: str, data) -> None:
        """Получаем лучший bid/ask и пробуем открыть позицию."""
        bids = data.get("b", [])
        asks = data.get("a", [])
        if not bids or not asks:
            return

        best_bid = float(bids[0][0]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else 0.0
        if best_bid <= 0 or best_ask <= 0:
            return

        mid = (best_bid + best_ask) / 2

        # Проверяем есть ли уже открытая позиция по символу
        open_pos = self.engine.get_open_positions(symbol)
        if open_pos:
            return

        # Вычисляем ATR из буфера
        buf = self._price_buf.get(symbol, [])
        if len(buf) < 15:
            return   # мало данных для ATR

        highs = [b[0] for b in buf]
        lows  = [b[1] for b in buf]
        closes = [b[2] for b in buf]
        atr = calc_atr(highs, lows, closes, period=14)
        if atr <= 0:
            return

        # Детектируем спайк вручную через буфер цен
        if len(closes) < 5:
            return
        ref_price = closes[-5]
        if ref_price <= 0:
            return
        spike_bps = (mid - ref_price) / ref_price * 10_000

        # Упрощённый дисбаланс стакана
        bid_vol = sum(float(b[1]) for b in bids[:5])
        ask_vol = sum(float(a[1]) for a in asks[:5])
        total_vol = bid_vol + ask_vol
        imbalance = bid_vol / total_vol if total_vol > 0 else 0.5

        # Сигнал входа
        threshold = self.strategy.spike_threshold_bps
        imb_threshold = self.strategy.imbalance_threshold

        if spike_bps < -threshold and imbalance > imb_threshold:
            side, entry = "long", best_ask
        elif spike_bps > threshold and imbalance < (1 - imb_threshold):
            side, entry = "short", best_bid
        else:
            return

        sl, tp = self.sizer.calc_sl_tp(entry, atr, side)
        qty = self.sizer.calc_qty(BALANCE, entry, sl)

        if qty <= 0:
            return

        trade_id = self.engine.open_position(
            symbol=symbol,
            side=side,
            entry_price=entry,
            qty=qty,
            stop_loss=sl,
            take_profit=tp,
            spike_direction=-1 if spike_bps < 0 else 1,
            spike_strength_bps=abs(spike_bps),
            entry_reason=f"spike={spike_bps:.1f}bps imb={imbalance:.2f}",
        )

        if trade_id:
            # Сохраняем SL/TP для policy
            self.engine._save_protection(symbol, side, sl, tp)
            msg = (f"OPEN {symbol} {side.upper()} "
                   f"entry={entry:.4f} sl={sl:.4f} tp={tp:.4f} "
                   f"qty={qty:.6f} spike={spike_bps:.1f}bps")
            log.info(msg)
            _write_app_log(msg, "futures")

    def stop(self) -> None:
        self._running = False
        log.info("FuturesRunner stopping...")
        _write_app_log("FuturesRunner stopped", "futures")


# ── Entry point ───────────────────────────────────────────────

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bootstrap_db()

    runner = FuturesRunner()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except (NotImplementedError, OSError):
            pass  # Windows не поддерживает add_signal_handler для всех сигналов

    await runner.run()


if __name__ == "__main__":
    asyncio.run(_main())
