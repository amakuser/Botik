"""
SpotRunner — asyncio цикл для спот paper-торговли.

Запускается как отдельный процесс через ManagedProcess в webview_app.py:
  python -m src.botik.runners.spot_runner

Жизненный цикл:
  1. bootstrap_db() — применяем миграции
  2. WebSocket подписка на orderbook + kline (публичный WS)
  3. REST poller (фоновая задача) — приватные данные demo-аккаунта
  4. Каждый orderbook тик → spike detection → engine.buy()
  5. Каждый kline тик → engine.on_price_tick() → policy решает выход
  6. Каждые 60с → stats в app_logs

Отличия от FuturesRunner:
  - Только long (нет шортов на спот)
  - Нет leverage
  - Меньший спайк-порог (спот менее волатильный)
  - Выход = sell() через SpotPaperEngine

Переменные окружения:
  BYBIT_HOST         — api-demo.bybit.com (default) | api.bybit.com
  BYBIT_API_KEY      — API ключ (для REST poller)
  BYBIT_API_SECRET_KEY — API секрет
  SPOT_SYMBOLS       — BTCUSDT,ETHUSDT (default)
  SPOT_BALANCE       — виртуальный баланс USDT (default 10000)
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

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)
except ImportError:
    pass  # python-dotenv необязателен

from src.botik.storage.schema import bootstrap_db
from src.botik.storage.db import get_db
from src.botik.execution.spot_paper import SpotPaperEngine
from src.botik.position.sizer import PositionSizer, calc_atr
from src.botik.position.simple_exit import SimpleExitPolicy
from src.botik.marketdata.rest_private_poller import RestPrivatePoller
from src.botik.ml.trainer import ModelTrainer

log = logging.getLogger("botik.runners.spot")

# ── Конфиг из env ─────────────────────────────────────────────
BYBIT_HOST = os.environ.get("BYBIT_HOST", "api-demo.bybit.com")
API_KEY = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET_KEY", "")

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SYMBOLS = [s.strip() for s in os.environ.get("SPOT_SYMBOLS", "").split(",") if s.strip()] \
          or DEFAULT_SYMBOLS

BALANCE         = float(os.environ.get("SPOT_BALANCE",        "10000"))
# Strategy params (RISK_PCT, MAX_POS_PCT stored as percent in .env: "0.8" = 0.8%)
RISK_PCT        = float(os.environ.get("SPOT_RISK_PCT",        "0.8"))  / 100
ATR_SL_MULT     = float(os.environ.get("SPOT_ATR_SL_MULT",     "1.2"))
ATR_TP_MULT     = float(os.environ.get("SPOT_ATR_TP_MULT",     "2.0"))
MAX_POS_PCT     = float(os.environ.get("SPOT_MAX_POS_PCT",     "10"))   / 100
HOLD_TIMEOUT_H  = float(os.environ.get("SPOT_HOLD_TIMEOUT_H",  "8"))
WS_URL = f"wss://{BYBIT_HOST}/v5/public/spot"
LOG_INTERVAL_SEC = 60
RECONNECT_DELAY_SEC = 5

# Спот менее волатильный — порог пониже
SPIKE_THRESHOLD_BPS = float(os.environ.get("SPOT_SPIKE_BPS",   "20.0"))
IMB_THRESHOLD = 0.62           # дисбаланс стакана
ATR_PERIOD = 14
MIN_BUF_SIZE = 15


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_app_log(msg: str, channel: str = "spot") -> None:
    try:
        db = get_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, recorded_at_utc) "
                "VALUES (?, 'INFO', ?, ?)",
                (channel, msg, _utc_now()),
            )
    except Exception:
        pass


class SpotRunner:
    """
    Главный класс SpotRunner. Управляет WS соединением и торговым циклом.
    """

    def __init__(self) -> None:
        # Paper engine
        self.engine = SpotPaperEngine(
            policy=SimpleExitPolicy(hold_timeout_ms=int(HOLD_TIMEOUT_H * 3600 * 1000)),
            model_scope="spot",
            balance_usdt=BALANCE,
        )

        # PositionSizer (спот: меньший риск, ATR SL/TP)
        self.sizer = PositionSizer(
            risk_pct=RISK_PCT,
            atr_sl_mult=ATR_SL_MULT,
            atr_tp_mult=ATR_TP_MULT,
            max_position_pct=MAX_POS_PCT,
        )

        # ML для спота
        self._trainer = ModelTrainer(model_scope="spot")
        predict_fn = self._trainer.get_predict_fn()

        if predict_fn:
            log.info("ML модель подключена к SpotRunner (spot predictor ready)")
        else:
            log.info("ML spot модель не обучена — работаем по правилам")

        self._predict_fn = predict_fn
        self._closed_since_retrain = 0

        # REST poller для demo-аккаунта
        self._poller = RestPrivatePoller(
            api_key=API_KEY,
            api_secret=API_SECRET,
            category="spot",
        )

        # Ценовые буферы
        self._price_buf: dict[str, list[tuple[float, float, float]]] = {
            s: [] for s in SYMBOLS
        }
        self._last_price: dict[str, float] = {}
        self._running = True
        self._last_stats_ts = 0.0

    # ── Main entry ────────────────────────────────────────────

    async def run(self) -> None:
        log.info("SpotRunner starting. Symbols: %s  Host: %s", SYMBOLS, BYBIT_HOST)
        _write_app_log(f"SpotRunner start. symbols={SYMBOLS}")

        # Запускаем REST poller в фоне
        asyncio.create_task(self._poller.run())

        while self._running:
            try:
                await self._ws_loop()
            except Exception as exc:
                log.warning("WS loop error, reconnect in %ds: %s", RECONNECT_DELAY_SEC, exc)
                _write_app_log(f"WS reconnect: {exc}")
                await asyncio.sleep(RECONNECT_DELAY_SEC)

    async def _ws_loop(self) -> None:
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
        topics = []
        for sym in SYMBOLS:
            topics.append(f"orderbook.50.{sym}")
            topics.append(f"kline.1.{sym}")

        await ws.send(json.dumps({
            "op": "subscribe",
            "args": topics,
        }))
        log.info("Subscribed to %d spot topics", len(topics))

    async def _handle_message(self, msg: dict) -> None:
        topic = msg.get("topic", "")
        data = msg.get("data", {})

        if topic.startswith("kline."):
            symbol = topic.split(".")[-1]
            await self._on_kline(symbol, data)

        elif topic.startswith("orderbook."):
            symbol = topic.split(".")[-1]
            await self._on_orderbook(symbol, data)

    async def _on_kline(self, symbol: str, data) -> None:
        """Обновляем ценовой буфер и проверяем выход из позиций."""
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

            # Проверяем выход
            closed = self.engine.on_price_tick(symbol, c)
            for trade in closed:
                msg_text = (
                    f"CLOSED {symbol} LONG "
                    f"exit={trade['exit_price']:.4f} "
                    f"pnl={trade['net_pnl']:+.4f} [{trade['exit_reason']}]"
                )
                log.info(msg_text)
                _write_app_log(msg_text, "spot")

                # ML outcome learning
                self._trainer.outcome_learner.record_trade(
                    net_pnl=trade["net_pnl"],
                    hold_time_ms=trade.get("hold_time_ms", 0),
                    exit_reason=trade["exit_reason"],
                )
                self._closed_since_retrain += 1

                # Инкрементальное переобучение
                if self._closed_since_retrain >= 50:
                    log.info("Spot: запускаем инкрементальное переобучение...")
                    _write_app_log("Spot incremental retrain triggered", "ml")
                    result = self._trainer.incremental()
                    self._closed_since_retrain = 0
                    new_fn = self._trainer.get_predict_fn()
                    if new_fn:
                        self._predict_fn = new_fn
                        log.info("Spot ML predict_fn обновлена (acc=%.3f)",
                                 result.get("predictor_accuracy", 0))

        # Периодический лог
        now = time.monotonic()
        if now - self._last_stats_ts > LOG_INTERVAL_SEC:
            self._last_stats_ts = now
            stats = self.engine.get_stats()
            _write_app_log(
                f"stats: trades={stats.get('total', 0)} "
                f"wins={stats.get('wins', 0)} "
                f"win_rate={stats.get('win_rate', 0.0):.1f}% "
                f"total_pnl={stats.get('total_pnl', 0.0):+.2f}",
                "spot",
            )

    async def _on_orderbook(self, symbol: str, data) -> None:
        """Получаем лучший bid/ask и пробуем открыть покупку."""
        bids = data.get("b", [])
        asks = data.get("a", [])
        if not bids or not asks:
            return

        best_bid = float(bids[0][0]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else 0.0
        if best_bid <= 0 or best_ask <= 0:
            return

        mid = (best_bid + best_ask) / 2

        # Уже есть холдинг?
        if self.engine.get_holdings(symbol):
            return

        # Нужно минимум данных для ATR
        buf = self._price_buf.get(symbol, [])
        if len(buf) < MIN_BUF_SIZE:
            return

        highs = [b[0] for b in buf]
        lows  = [b[1] for b in buf]
        closes = [b[2] for b in buf]
        atr = calc_atr(highs, lows, closes, period=ATR_PERIOD)
        if atr <= 0:
            return

        # Детектируем спайк (последние 5 свечей)
        if len(closes) < 5:
            return
        ref_price = closes[-5]
        if ref_price <= 0:
            return
        spike_bps = (mid - ref_price) / ref_price * 10_000

        # Дисбаланс стакана
        bid_vol = sum(float(b[1]) for b in bids[:5])
        ask_vol = sum(float(a[1]) for a in asks[:5])
        total_vol = bid_vol + ask_vol
        imbalance = bid_vol / total_vol if total_vol > 0 else 0.5

        # На споте только лонги:
        # spike_bps < -threshold (цена упала) + больше покупателей → reversal long
        if spike_bps >= -SPIKE_THRESHOLD_BPS or imbalance <= IMB_THRESHOLD:
            return

        entry = best_ask

        # ML фильтр (если обучен)
        if self._predict_fn is not None:
            try:
                from src.botik.ml.feature_engine import build_futures_features
                features = build_futures_features(
                    [{"high": h, "low": lo, "close": c} for h, lo, c in buf[-20:]],
                    ob_imbalance=imbalance,
                )
                if features is not None:
                    score = self._predict_fn(features)
                    if score < self._trainer.predictor.entry_threshold:
                        log.debug("Spot ML фильтр отклонил вход: score=%.3f", score)
                        return
            except Exception as exc:
                log.debug("Spot ML predict error: %s", exc)

        sl, tp = self.sizer.calc_sl_tp(entry, atr, "long")
        qty = self.sizer.calc_qty(BALANCE, entry, sl)

        if qty <= 0:
            return

        trade_id = self.engine.buy(
            symbol=symbol,
            qty=qty,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            entry_reason=f"spike={spike_bps:.1f}bps imb={imbalance:.2f}",
        )

        if trade_id:
            msg_text = (
                f"BUY {symbol} "
                f"entry={entry:.4f} sl={sl:.4f} tp={tp:.4f} "
                f"qty={qty:.6f} spike={spike_bps:.1f}bps"
            )
            log.info(msg_text)
            _write_app_log(msg_text, "spot")

    def stop(self) -> None:
        self._running = False
        self._poller.stop()
        log.info("SpotRunner stopping...")
        _write_app_log("SpotRunner stopped", "spot")


# ── Entry point ───────────────────────────────────────────────

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bootstrap_db()

    runner = SpotRunner()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except (NotImplementedError, OSError):
            pass

    await runner.run()


if __name__ == "__main__":
    asyncio.run(_main())
