"""
Точка входа CLI: загрузка конфига, настройка логов, маркетдата, стратегия, RiskManager, execution.
Торговля только при заданных API-ключах и при state.paused=False (/resume).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from src.botik.config import load_config
from src.botik.control.telegram_bot import start_telegram_bot_in_thread
from src.botik.execution.bybit_rest import BybitRestClient
from src.botik.marketdata.ws_public import BybitSpotOrderbookWS
from src.botik.risk.manager import RiskManager
from src.botik.state.state import TradingState
from src.botik.storage.sqlite_store import get_connection, insert_metrics, insert_order
from src.botik.strategy.micro_spread import MicroSpreadStrategy
from src.botik.utils.logging import setup_logging
from src.botik.utils.time import utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit Spot DEMO Bot")
    parser.add_argument("--config", type=str, default=None, help="Путь к config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    log = logging.getLogger("botik")
    log.info("Конфиг загружен: bybit host=%s, symbols=%s, start_paused=%s",
             config.bybit.host, config.symbols, config.start_paused)

    state = TradingState()
    state.paused = config.start_paused

    telegram_token = config.get_telegram_token()
    telegram_chat_id = config.get_telegram_chat_id()
    if telegram_token:
        start_telegram_bot_in_thread(telegram_token, state, config, allowed_chat_id=telegram_chat_id)
        log.info("Telegram бот запущен (чат: %s).", telegram_chat_id or "любой")
    else:
        log.warning("TELEGRAM_BOT_TOKEN не задан — команды /pause, /resume, /panic недоступны.")

    async def run_ws_metrics_trading() -> None:
        conn = get_connection(config.storage.path)
        api_key = config.get_bybit_api_key()
        api_secret = config.get_bybit_api_secret()
        rest: BybitRestClient | None = None
        if api_key and api_secret:
            rest = BybitRestClient(
                base_url=f"https://{config.bybit.host}",
                api_key=api_key,
                api_secret=api_secret,
            )
        risk_manager = RiskManager(config.risk)
        strategy = MicroSpreadStrategy(config)
        replace_interval_sec = config.strategy.replace_interval_ms / 1000.0

        async def trading_loop() -> None:
            if rest is None:
                return
            while True:
                await asyncio.sleep(replace_interval_sec)
                if state.panic_requested:
                    try:
                        await rest.cancel_all_orders()
                        log.warning("PANIC: отменены все ордера.")
                    except Exception as e:
                        log.exception("Ошибка при panic cancel: %s", e)
                    state.set_panic_requested(False)
                    continue
                if state.paused:
                    continue
                try:
                    resp = await rest.get_open_orders()
                    list_ = (resp.get("result") or {}).get("list") or []
                    total_exposure = 0.0
                    symbol_exposure: dict[str, float] = {}
                    our_order_link_ids: list[tuple[str, str]] = []  # (symbol, orderLinkId)
                    for o in list_:
                        sym = o.get("symbol", "")
                        price = float(o.get("price") or 0)
                        qty = float(o.get("qty") or 0)
                        link = o.get("orderLinkId") or ""
                        notional = price * qty
                        total_exposure += notional
                        symbol_exposure[sym] = symbol_exposure.get(sym, 0) + notional
                        if link.startswith("mm-"):
                            our_order_link_ids.append((sym, link))
                    for sym, link in our_order_link_ids:
                        await rest.cancel_order(symbol=sym, order_link_id=link)
                    intents = strategy.get_intents(state)
                    for intent in intents:
                        res = risk_manager.check_order(
                            intent.symbol,
                            intent.side,
                            intent.price,
                            intent.qty,
                            total_exposure,
                            symbol_exposure.get(intent.symbol, 0),
                        )
                        if not res.allowed:
                            log.debug("Risk reject: %s", res.reason)
                            continue
                        price_str = f"{intent.price:.8f}".rstrip("0").rstrip(".")
                        qty_str = f"{intent.qty:.8f}".rstrip("0").rstrip(".")
                        ret = await rest.place_order(
                            symbol=intent.symbol,
                            side=intent.side,
                            qty=qty_str,
                            price=price_str,
                            order_link_id=intent.order_link_id,
                            time_in_force="PostOnly",
                        )
                        if ret.get("retCode") == 0:
                            risk_manager.register_order_placed()
                            total_exposure += intent.price * intent.qty
                            symbol_exposure[intent.symbol] = symbol_exposure.get(intent.symbol, 0) + intent.price * intent.qty
                            ts = utc_now_iso()
                            insert_order(
                                conn,
                                symbol=intent.symbol,
                                side=intent.side,
                                order_link_id=intent.order_link_id,
                                price=price_str,
                                qty=qty_str,
                                status="New",
                                created_at_utc=ts,
                                exchange_order_id=(ret.get("result") or {}).get("orderId"),
                            )
                except Exception as e:
                    log.exception("Trading loop error: %s", e)

        ws = BybitSpotOrderbookWS(
            ws_host=config.bybit.ws_public_host,
            symbols=config.symbols,
            depth=config.ws_depth,
            state=state,
            tick_size=config.strategy.default_tick_size,
        )
        interval = config.storage.metrics_interval_sec

        async def metrics_loop() -> None:
            while True:
                await asyncio.sleep(interval)
                ts = utc_now_iso()
                for symbol in config.symbols:
                    ob = state.get_orderbook(symbol)
                    if ob is None:
                        continue
                    insert_metrics(
                        conn,
                        symbol=symbol,
                        ts_utc=ts,
                        best_bid=ob.best_bid,
                        best_ask=ob.best_ask,
                        mid=ob.mid,
                        spread_ticks=ob.spread_ticks,
                        imbalance_top_n=ob.imbalance_top_n,
                    )

        try:
            await asyncio.gather(ws.run(), metrics_loop(), trading_loop())
        finally:
            conn.close()

    asyncio.run(run_ws_metrics_trading())


# --- Как проверить: запуск с config.yaml и .env (BYBIT_*), start_paused=true — ордера не выставляются; /resume (через Telegram в Шаге 5) или state.paused=False — цикл выставляет ордера на DEMO.
# --- Частые ошибки: не задать API ключи — trading_loop не запускает ордера; перепутать mainnet/demo host.
# --- Что улучшить позже: polling исполнений и запись fills + PnL snapshot; TTL отмена ордеров по order_ttl_sec.

if __name__ == "__main__":
    main()
