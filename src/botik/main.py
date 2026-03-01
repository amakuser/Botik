"""
CLI entrypoint: config, logging, WS market data, strategy, risk checks and execution.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
import uuid
from typing import Any

from src.botik.config import load_config
from src.botik.control.telegram_bot import start_telegram_bot_in_thread
from src.botik.execution.bybit_rest import BybitRestClient
from src.botik.execution.paper import PaperTradingClient
from src.botik.marketdata.ws_public import BybitSpotOrderbookWS
from src.botik.risk.manager import RiskManager
from src.botik.risk.position import apply_fill, unrealized_pnl_pct
from src.botik.state.state import TradingState
from src.botik.storage.sqlite_store import get_connection, insert_fill, insert_metrics, insert_order
from src.botik.strategy.micro_spread import MicroSpreadStrategy
from src.botik.utils.logging import setup_logging
from src.botik.utils.time import utc_now_iso


def _fmt_float(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit Spot Bot")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    log = logging.getLogger("botik")
    log.info(
        "Config loaded: host=%s ws=%s symbols=%s start_paused=%s execution_mode=%s",
        config.bybit.host,
        config.bybit.ws_public_host,
        config.symbols,
        config.start_paused,
        config.execution.mode,
    )

    state = TradingState()
    state.paused = config.start_paused

    telegram_token = config.get_telegram_token()
    telegram_chat_id = config.get_telegram_chat_id()
    if telegram_token:
        start_telegram_bot_in_thread(telegram_token, state, config, allowed_chat_id=telegram_chat_id)
        log.info("Telegram bot started (chat: %s)", telegram_chat_id or "any")
    else:
        log.warning("TELEGRAM_BOT_TOKEN is not set, control commands are disabled.")

    async def run_ws_metrics_trading() -> None:
        conn = get_connection(config.storage.path)

        api_key = config.get_bybit_api_key()
        api_secret = config.get_bybit_api_secret()
        rsa_private_key_path = config.get_bybit_rsa_private_key_path()

        executor: Any | None = None
        mode = config.execution.mode.lower().strip()
        if mode == "paper":
            executor = PaperTradingClient(state=state, fill_on_cross=config.execution.paper_fill_on_cross)
            log.info("Execution mode: paper (no real exchange orders).")
        elif api_key and (api_secret or rsa_private_key_path):
            executor = BybitRestClient(
                base_url=f"https://{config.bybit.host}",
                api_key=api_key,
                api_secret=api_secret,
                rsa_private_key_path=rsa_private_key_path,
            )
            log.info(
                "Execution mode: live auth=%s host=%s recv_window=%s",
                executor.auth_mode,
                config.bybit.host,
                executor.recv_window,
            )
        else:
            log.warning("Execution is disabled: set execution.mode=paper or BYBIT credentials for live mode.")

        if executor is not None:
            preflight = await executor.get_open_orders(config.symbols[0] if config.symbols else None)
            if preflight.get("retCode") != 0:
                raise RuntimeError(
                    f"Execution preflight failed: retCode={preflight.get('retCode')} retMsg={preflight.get('retMsg')}"
                )
            log.info("Execution preflight passed.")

        risk_manager = RiskManager(config.risk)
        strategy = MicroSpreadStrategy(config)
        replace_interval_sec = config.strategy.replace_interval_ms / 1000.0

        min_position_qty = config.strategy.min_position_qty_base
        hold_timeout_sec = config.strategy.position_hold_timeout_sec
        force_exit_enabled = config.strategy.force_exit_enabled
        force_exit_tif = config.strategy.force_exit_time_in_force
        force_exit_cooldown_sec = config.strategy.force_exit_cooldown_sec
        stop_loss_pct = max(config.strategy.stop_loss_pct, 0.0)
        take_profit_pct = max(config.strategy.take_profit_pct, 0.0)
        pnl_exit_enabled = config.strategy.pnl_exit_enabled

        net_position_base: dict[str, float] = {s: 0.0 for s in config.symbols}
        avg_entry_price: dict[str, float] = {s: 0.0 for s in config.symbols}
        position_opened_at: dict[str, float | None] = {s: None for s in config.symbols}
        last_force_exit_ts: dict[str, float] = {s: 0.0 for s in config.symbols}
        seen_exec_ids: set[str] = set()

        async def refresh_positions_from_executions() -> None:
            if executor is None:
                return
            for symbol in config.symbols:
                try:
                    resp = await executor.get_execution_list(symbol=symbol, limit=100)
                except Exception as exc:
                    log.warning("get_execution_list failed for %s: %s", symbol, exc)
                    continue
                if resp.get("retCode") != 0:
                    log.warning(
                        "get_execution_list error for %s: retCode=%s retMsg=%s",
                        symbol,
                        resp.get("retCode"),
                        resp.get("retMsg"),
                    )
                    continue

                items = (resp.get("result") or {}).get("list") or []
                for item in reversed(items):
                    exec_id = str(
                        item.get("execId")
                        or f"{item.get('orderId')}:{item.get('execTime')}:{item.get('execQty')}:{item.get('symbol')}"
                    )
                    if exec_id in seen_exec_ids:
                        continue
                    seen_exec_ids.add(exec_id)
                    if len(seen_exec_ids) > 20000:
                        seen_exec_ids.clear()

                    side = str(item.get("side") or "").lower()
                    qty = float(item.get("execQty") or item.get("qty") or 0.0)
                    price = float(item.get("execPrice") or item.get("price") or 0.0)
                    if qty <= 0 or side not in {"buy", "sell"}:
                        continue

                    old_qty = net_position_base.get(symbol, 0.0)
                    new_qty, new_avg = apply_fill(
                        current_qty=old_qty,
                        current_avg_entry=avg_entry_price.get(symbol, 0.0),
                        side=side,
                        fill_qty=qty,
                        fill_price=price,
                    )
                    net_position_base[symbol] = new_qty
                    avg_entry_price[symbol] = new_avg

                    if abs(old_qty) < min_position_qty and abs(new_qty) >= min_position_qty:
                        position_opened_at[symbol] = time.monotonic()
                    elif abs(new_qty) < min_position_qty:
                        position_opened_at[symbol] = None

                    insert_fill(
                        conn,
                        symbol=symbol,
                        side="Buy" if side == "buy" else "Sell",
                        price=str(price),
                        qty=str(qty),
                        filled_at_utc=utc_now_iso(),
                        order_link_id=item.get("orderLinkId"),
                        exchange_order_id=item.get("orderId"),
                        fee=str(item.get("execFee") or ""),
                        fee_currency=item.get("feeCurrency"),
                        liquidity="Maker" if str(item.get("isMaker") or "").lower() == "true" else "Taker",
                    )

        async def maybe_force_exit(symbol: str) -> bool:
            if executor is None:
                return False
            pos_qty = net_position_base.get(symbol, 0.0)
            if abs(pos_qty) < min_position_qty:
                return False

            opened_at = position_opened_at.get(symbol)
            if opened_at is None:
                position_opened_at[symbol] = time.monotonic()
                return True

            ob = state.get_orderbook(symbol)
            if ob is None:
                return True

            mark_price = ob.best_bid if pos_qty > 0 else ob.best_ask
            pnl_pct = unrealized_pnl_pct(
                position_qty=pos_qty,
                avg_entry_price=avg_entry_price.get(symbol, 0.0),
                mark_price=mark_price,
            )
            age = time.monotonic() - opened_at

            reason: str | None = None
            if pnl_exit_enabled and pnl_pct is not None:
                if stop_loss_pct > 0 and pnl_pct <= -stop_loss_pct:
                    reason = "stop_loss"
                elif take_profit_pct > 0 and pnl_pct >= take_profit_pct:
                    reason = "take_profit"

            if reason is None and age >= hold_timeout_sec:
                reason = "hold_timeout"

            # Symbol has an open position: block opening additional inventory.
            if reason is None:
                return True

            if not force_exit_enabled:
                log.warning(
                    "Exit rule triggered but force_exit_enabled=false: symbol=%s reason=%s qty=%s pnl_pct=%s age=%.1fs",
                    symbol,
                    reason,
                    pos_qty,
                    f"{pnl_pct:.6f}" if pnl_pct is not None else "n/a",
                    age,
                )
                return True

            if time.monotonic() - last_force_exit_ts.get(symbol, 0.0) < force_exit_cooldown_sec:
                return True

            side = "Sell" if pos_qty > 0 else "Buy"
            exit_price = ob.best_bid if side == "Sell" else ob.best_ask
            qty_str = _fmt_float(abs(pos_qty))
            price_str = _fmt_float(exit_price)
            order_link_id = f"force-exit-{symbol}-{uuid.uuid4().hex[:10]}"

            ret = await executor.place_order(
                symbol=symbol,
                side=side,
                qty=qty_str,
                price=price_str,
                order_link_id=order_link_id,
                time_in_force=force_exit_tif,
            )
            last_force_exit_ts[symbol] = time.monotonic()

            if ret.get("retCode") != 0:
                log.warning(
                    "Force-exit failed: symbol=%s side=%s qty=%s retCode=%s retMsg=%s",
                    symbol,
                    side,
                    qty_str,
                    ret.get("retCode"),
                    ret.get("retMsg"),
                )
                return True

            risk_manager.register_order_placed()
            insert_order(
                conn,
                symbol=symbol,
                side=side,
                order_link_id=order_link_id,
                price=price_str,
                qty=qty_str,
                status="New",
                created_at_utc=utc_now_iso(),
                exchange_order_id=(ret.get("result") or {}).get("orderId"),
            )
            log.warning(
                "Force-exit submitted: symbol=%s side=%s qty=%s price=%s tif=%s reason=%s pnl_pct=%s age=%.1fs",
                symbol,
                side,
                qty_str,
                price_str,
                force_exit_tif,
                reason,
                f"{pnl_pct:.6f}" if pnl_pct is not None else "n/a",
                age,
            )
            return True

        async def trading_loop() -> None:
            if executor is None:
                return

            while True:
                await asyncio.sleep(replace_interval_sec)

                if state.panic_requested:
                    try:
                        await executor.cancel_all_orders()
                        log.warning("PANIC: all working orders cancelled.")
                    except Exception as exc:
                        log.exception("panic cancel failed: %s", exc)
                    state.set_panic_requested(False)
                    continue

                if state.paused:
                    continue

                try:
                    await refresh_positions_from_executions()

                    resp = await executor.get_open_orders()
                    if resp.get("retCode") == 10004:
                        log.error("Stopping trading loop: invalid REST signature (retCode=10004).")
                        state.set_paused(True)
                        return
                    if resp.get("retCode") != 0:
                        log.warning(
                            "get_open_orders failed: retCode=%s retMsg=%s",
                            resp.get("retCode"),
                            resp.get("retMsg"),
                        )
                        continue

                    total_exposure = 0.0
                    symbol_exposure: dict[str, float] = {}
                    our_order_link_ids: list[tuple[str, str]] = []
                    for order in (resp.get("result") or {}).get("list") or []:
                        sym = order.get("symbol", "")
                        price = float(order.get("price") or 0)
                        qty = float(order.get("qty") or 0)
                        link = order.get("orderLinkId") or ""
                        notional = price * qty
                        total_exposure += notional
                        symbol_exposure[sym] = symbol_exposure.get(sym, 0.0) + notional
                        if link.startswith("mm-"):
                            our_order_link_ids.append((sym, link))

                    for sym, link in our_order_link_ids:
                        await executor.cancel_order(symbol=sym, order_link_id=link)

                    blocked_symbols: set[str] = set()
                    for symbol in config.symbols:
                        if await maybe_force_exit(symbol):
                            blocked_symbols.add(symbol)

                    intents = strategy.get_intents(state)
                    normal_tif = "PostOnly" if config.strategy.maker_only else "GTC"

                    for intent in intents:
                        if intent.symbol in blocked_symbols:
                            continue

                        risk = risk_manager.check_order(
                            intent.symbol,
                            intent.side,
                            intent.price,
                            intent.qty,
                            total_exposure,
                            symbol_exposure.get(intent.symbol, 0.0),
                        )
                        if not risk.allowed:
                            log.debug("Risk reject: %s", risk.reason)
                            continue

                        ret = await executor.place_order(
                            symbol=intent.symbol,
                            side=intent.side,
                            qty=_fmt_float(intent.qty),
                            price=_fmt_float(intent.price),
                            order_link_id=intent.order_link_id,
                            time_in_force=normal_tif,
                        )

                        if ret.get("retCode") == 10004:
                            log.error("Stopping trading loop: invalid REST signature on place_order (10004).")
                            state.set_paused(True)
                            return
                        if ret.get("retCode") != 0:
                            log.warning(
                                "place_order failed: symbol=%s retCode=%s retMsg=%s",
                                intent.symbol,
                                ret.get("retCode"),
                                ret.get("retMsg"),
                            )
                            continue

                        risk_manager.register_order_placed()
                        total_exposure += intent.price * intent.qty
                        symbol_exposure[intent.symbol] = (
                            symbol_exposure.get(intent.symbol, 0.0) + intent.price * intent.qty
                        )
                        insert_order(
                            conn,
                            symbol=intent.symbol,
                            side=intent.side,
                            order_link_id=intent.order_link_id,
                            price=_fmt_float(intent.price),
                            qty=_fmt_float(intent.qty),
                            status="New",
                            created_at_utc=utc_now_iso(),
                            exchange_order_id=(ret.get("result") or {}).get("orderId"),
                        )
                except Exception as exc:
                    log.exception("Trading loop error: %s", exc)

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


if __name__ == "__main__":
    main()
