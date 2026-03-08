"""
CLI entrypoint: config, logging, WS market data, strategy, risk checks and execution.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
import time
import uuid
from typing import Any

from src.botik.config import ActionProfileConfig, load_config
from src.botik.control.telegram_bot import start_telegram_bot_in_thread
from src.botik.execution.bybit_rest import BybitRestClient
from src.botik.execution.paper import PaperTradingClient
from src.botik.marketdata.universe_discovery import discover_top_spot_symbols
from src.botik.marketdata.ws_public import BybitSpotOrderbookWS
from src.botik.learning.bandit import GaussianThompsonBandit
from src.botik.learning.policy import PolicySelector
from src.botik.learning.policy_manager import ModelBundle, load_active_model
from src.botik.risk.manager import RiskManager
from src.botik.risk.position import apply_fill, unrealized_pnl_pct
from src.botik.state.state import TradingState
from src.botik.version import get_app_version_label
from src.botik.storage.sqlite_store import get_connection, insert_fill, insert_metrics, insert_order
from src.botik.storage.lifecycle_store import (
    ensure_lifecycle_schema,
    get_signal_id_for_order_link,
    insert_execution_event,
    insert_order_event,
    insert_signal_snapshot,
    set_order_signal_map,
    upsert_signal_reward,
    upsert_outcome,
)
from src.botik.strategy.micro_spread import MicroSpreadStrategy
from src.botik.strategy.pair_admission import evaluate_pair_admission
from src.botik.strategy.symbol_scanner import pick_active_symbols
from src.botik.utils.logging import setup_logging
from src.botik.utils.time import utc_now_iso


def _fmt_float(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


_KNOWN_QUOTE_SUFFIXES = (
    "USDT",
    "USDC",
    "BTC",
    "ETH",
    "EUR",
    "TRY",
    "BRL",
    "RUB",
)


def _split_symbol_base_quote(symbol: str) -> tuple[str, str]:
    s = str(symbol or "").upper().strip()
    for quote in _KNOWN_QUOTE_SUFFIXES:
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)], quote
    return s, ""


def _fee_to_quote(symbol: str, fee: float, fee_currency: str, exec_price: float) -> float:
    fee_abs = max(float(fee or 0.0), 0.0)
    if fee_abs <= 0:
        return 0.0
    fee_ccy = str(fee_currency or "").upper().strip()
    if not fee_ccy:
        return fee_abs
    base_ccy, quote_ccy = _split_symbol_base_quote(symbol)
    if quote_ccy and fee_ccy == quote_ccy:
        return fee_abs
    if base_ccy and fee_ccy == base_ccy and exec_price > 0:
        return fee_abs * float(exec_price)
    return fee_abs


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit Spot Bot")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    app_version = get_app_version_label()
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    log = logging.getLogger("botik")
    log.info(
        "Config loaded: version=%s host=%s ws=%s symbols=%s start_paused=%s execution_mode=%s",
        app_version,
        config.bybit.host,
        config.bybit.ws_public_host,
        config.symbols,
        config.start_paused,
        config.execution.mode,
    )

    state = TradingState()
    state.paused = config.start_paused

    disable_internal_telegram = str(os.environ.get("BOTIK_DISABLE_INTERNAL_TELEGRAM", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    telegram_token = config.get_telegram_token()
    telegram_chat_id = config.get_telegram_chat_id()
    if disable_internal_telegram:
        log.info("Internal Telegram controller disabled by BOTIK_DISABLE_INTERNAL_TELEGRAM.")
    elif telegram_token:
        start_telegram_bot_in_thread(telegram_token, state, config, allowed_chat_id=telegram_chat_id)
        log.info("Telegram bot started (chat: %s)", telegram_chat_id or "any")
    else:
        log.warning("TELEGRAM_BOT_TOKEN is not set, control commands are disabled.")

    async def run_ws_metrics_trading() -> None:
        conn = get_connection(config.storage.path)
        ensure_lifecycle_schema(conn)

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

        auto_universe_enabled = bool(config.strategy.auto_universe_enabled)
        auto_universe_refresh_sec = max(float(config.strategy.auto_universe_refresh_sec), 30.0)

        if auto_universe_enabled:
            try:
                discovered = await discover_top_spot_symbols(
                    host=config.strategy.auto_universe_host,
                    quote=config.strategy.auto_universe_quote,
                    limit=config.strategy.auto_universe_size,
                    min_turnover_24h=config.strategy.auto_universe_min_turnover_24h,
                    min_raw_spread_bps=config.strategy.auto_universe_min_raw_spread_bps,
                    min_top_book_notional=config.strategy.auto_universe_min_top_book_notional,
                    exclude_st_tag_1=config.strategy.auto_universe_exclude_st_tag_1,
                )
                if discovered:
                    config.symbols = discovered
                    log.info(
                        "Auto-universe bootstrap: symbols=%s top=%s",
                        len(config.symbols),
                        ",".join(config.symbols[:8]),
                    )
                else:
                    log.warning("Auto-universe bootstrap returned empty list; using configured symbols.")
            except Exception as exc:
                log.warning("Auto-universe bootstrap failed; using configured symbols: %s", exc)

        if executor is not None:
            preflight = await executor.get_open_orders(config.symbols[0] if config.symbols else None)
            if preflight.get("retCode") != 0:
                raise RuntimeError(
                    f"Execution preflight failed: retCode={preflight.get('retCode')} retMsg={preflight.get('retMsg')}"
                )
            log.info("Execution preflight passed.")

        risk_manager = RiskManager(config.risk)
        strategy = MicroSpreadStrategy(config)
        profile_ids = [p.profile_id.strip() for p in config.strategy.action_profiles if p.profile_id.strip()]
        if not profile_ids:
            profile_ids = ["default"]
        policy_profiles = list(config.strategy.action_profiles)
        if not policy_profiles:
            policy_profiles = [
                ActionProfileConfig(
                    profile_id="default",
                    entry_tick_offset=config.strategy.entry_tick_offset,
                    order_qty_base=config.strategy.order_qty_base,
                    target_profit=config.strategy.target_profit,
                    safety_buffer=config.strategy.safety_buffer,
                    min_top_book_qty=config.strategy.min_top_book_qty,
                    stop_loss_pct=config.strategy.stop_loss_pct,
                    take_profit_pct=config.strategy.take_profit_pct,
                    hold_timeout_sec=config.strategy.position_hold_timeout_sec,
                    maker_only=config.strategy.maker_only,
                )
            ]
        bandit_enabled = bool(config.strategy.bandit_enabled)
        bandit = GaussianThompsonBandit(
            conn=conn,
            profile_ids=profile_ids,
            epsilon=float(config.strategy.bandit_epsilon),
        )
        policy_selector = PolicySelector(bandit=bandit)
        policy_mode = str(config.ml.mode).strip().lower()
        policy_model: ModelBundle | None = None
        policy_model_last_check_ts = 0.0
        policy_model_id = ""
        replace_interval_sec = config.strategy.replace_interval_ms / 1000.0
        scanner_interval_sec = max(float(config.strategy.scanner_interval_sec), 1.0)
        scanner_enabled = bool(config.strategy.scanner_enabled)
        candidate_queue: asyncio.Queue[list[str]] = asyncio.Queue(maxsize=1)
        state.set_active_symbols(list(config.symbols))
        state.set_active_profiles({symbol: profile_ids[0] for symbol in config.symbols})
        state.set_active_policy_meta(
            {
                symbol: {
                "policy_used": "Static",
                "profile_id": profile_ids[0],
                "pred_open_prob": None,
                "pred_exp_edge_bps": None,
                "active_model_id": None,
                "model_id": None,
                "reason": "startup",
            }
            for symbol in config.symbols
        }
        )
        state.set_scanner_snapshot(
            {
                "enabled": scanner_enabled,
                "selected": len(config.symbols),
                "top_symbol": "",
                "top_score_bps": 0.0,
            }
        )

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
        position_signal_id: dict[str, str | None] = {s: None for s in config.symbols}
        position_opened_wall_ms: dict[str, int | None] = {s: None for s in config.symbols}
        position_opened_at: dict[str, float | None] = {s: None for s in config.symbols}
        last_force_exit_ts: dict[str, float] = {s: 0.0 for s in config.symbols}
        symbol_hold_timeout_sec: dict[str, float] = {s: float(hold_timeout_sec) for s in config.symbols}
        symbol_stop_loss_pct: dict[str, float] = {s: float(stop_loss_pct) for s in config.symbols}
        symbol_take_profit_pct: dict[str, float] = {s: float(take_profit_pct) for s in config.symbols}
        seen_exec_ids: set[str] = set()

        def _sum_signal_fees_quote(conn_db: sqlite3.Connection, signal_id: str, symbol: str) -> float:
            rows = conn_db.execute(
                """
                SELECT exec_fee, fee_currency, exec_price
                FROM executions_raw
                WHERE signal_id = ?
                """,
                (signal_id,),
            ).fetchall()
            total = 0.0
            for exec_fee, fee_currency, exec_price in rows:
                total += _fee_to_quote(symbol, float(exec_fee or 0.0), str(fee_currency or ""), float(exec_price or 0.0))
            return total

        def _load_signal_entry_basis(conn_db: sqlite3.Connection, signal_id: str) -> tuple[float, float]:
            row = conn_db.execute(
                """
                SELECT entry_price, order_size_base
                FROM signals
                WHERE signal_id = ?
                LIMIT 1
                """,
                (signal_id,),
            ).fetchone()
            if not row:
                return 0.0, 0.0
            return float(row[0] or 0.0), float(row[1] or 0.0)

        def _maybe_refresh_policy_model(force: bool = False) -> None:
            nonlocal policy_model, policy_model_last_check_ts, policy_model_id
            if policy_mode != "predict":
                return
            now_mono = time.monotonic()
            if not force and now_mono - policy_model_last_check_ts < 30.0:
                return
            policy_model_last_check_ts = now_mono
            try:
                loaded = load_active_model(conn)
            except Exception as exc:
                if policy_model is not None:
                    log.warning("Policy model reload failed, keeping previous model: %s", exc)
                    return
                log.warning("Policy model unavailable: %s", exc)
                return
            if loaded is None:
                if policy_model is not None:
                    log.warning("Policy model disabled: no active model in registry, fallback to bandit.")
                policy_model = None
                policy_model_id = ""
                return
            if loaded.model_id != policy_model_id:
                policy_model = loaded
                policy_model_id = loaded.model_id
                log.info("Policy model loaded: model_id=%s", policy_model_id)

        async def refresh_positions_from_executions() -> None:
            if executor is None:
                return
            symbols_to_check: set[str] = set(state.get_active_symbols() or config.symbols)
            symbols_to_check.update(s for s, q in net_position_base.items() if abs(q) >= min_position_qty)
            for symbol in symbols_to_check:
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

                    order_link_id = item.get("orderLinkId")
                    signal_id = get_signal_id_for_order_link(conn, str(order_link_id) if order_link_id else None)
                    exec_fee = float(item.get("execFee") or 0.0)
                    fee_currency = str(item.get("feeCurrency") or "").upper()
                    symbol_u = symbol.upper()
                    base_ccy, _quote_ccy = _split_symbol_base_quote(symbol_u)
                    exec_time_ms = int(item.get("execTime") or 0) or int(time.time() * 1000)

                    # For spot fills with fee in base asset, wallet position changes by net base amount:
                    # buy => +qty-fee_base, sell => -(qty+fee_base).
                    effective_qty = qty
                    if base_ccy and fee_currency == base_ccy:
                        if side == "buy":
                            effective_qty = max(qty - exec_fee, 0.0)
                        else:
                            effective_qty = qty + max(exec_fee, 0.0)
                    if effective_qty <= 0:
                        continue

                    insert_execution_event(
                        conn,
                        exec_id=exec_id,
                        symbol=symbol,
                        exec_price=price,
                        exec_qty=qty,
                        order_id=item.get("orderId"),
                        order_link_id=order_link_id,
                        signal_id=signal_id,
                        side=item.get("side"),
                        order_type=item.get("orderType"),
                        exec_fee=exec_fee,
                        fee_rate=float(item.get("feeRate") or 0.0) if item.get("feeRate") else None,
                        fee_currency=item.get("feeCurrency"),
                        is_maker=str(item.get("isMaker") or "").lower() == "true",
                        exec_time_ms=exec_time_ms,
                    )

                    old_qty = net_position_base.get(symbol, 0.0)
                    old_avg = avg_entry_price.get(symbol, 0.0)
                    new_qty, new_avg = apply_fill(
                        current_qty=old_qty,
                        current_avg_entry=old_avg,
                        side=side,
                        fill_qty=effective_qty,
                        fill_price=price,
                    )
                    net_position_base[symbol] = new_qty
                    avg_entry_price[symbol] = new_avg

                    if abs(old_qty) < min_position_qty and abs(new_qty) >= min_position_qty:
                        position_opened_at[symbol] = time.monotonic()
                        position_opened_wall_ms[symbol] = exec_time_ms
                        position_signal_id[symbol] = signal_id
                    elif abs(new_qty) < min_position_qty:
                        opened_at = position_opened_at.get(symbol)
                        hold_time_ms = int((time.monotonic() - opened_at) * 1000) if opened_at else 0
                        qty_closed = abs(old_qty)
                        entry_vwap = old_avg if old_avg > 0 else price
                        exit_vwap = price
                        gross_pnl = 0.0
                        if qty_closed > 0:
                            if old_qty > 0:
                                gross_pnl = (exit_vwap - entry_vwap) * qty_closed
                            else:
                                gross_pnl = (entry_vwap - exit_vwap) * qty_closed
                        outcome_signal_id = position_signal_id.get(symbol) or signal_id
                        total_fees_quote = (
                            _sum_signal_fees_quote(conn, outcome_signal_id, symbol)
                            if outcome_signal_id
                            else _fee_to_quote(symbol, exec_fee, fee_currency, price)
                        )
                        net_pnl = gross_pnl - total_fees_quote
                        entry_basis_price, entry_basis_qty = (
                            _load_signal_entry_basis(conn, outcome_signal_id) if outcome_signal_id else (0.0, 0.0)
                        )
                        denom = entry_basis_price * entry_basis_qty if entry_basis_price > 0 and entry_basis_qty > 0 else entry_vwap * qty_closed
                        net_edge_bps = (net_pnl / denom) * 10000.0 if denom > 0 else 0.0
                        if outcome_signal_id:
                            upsert_outcome(
                                conn,
                                signal_id=outcome_signal_id,
                                symbol=symbol,
                                entry_vwap=entry_vwap,
                                exit_vwap=exit_vwap,
                                filled_qty=qty_closed,
                                hold_time_ms=hold_time_ms,
                                gross_pnl_quote=gross_pnl,
                                net_pnl_quote=net_pnl,
                                net_edge_bps=net_edge_bps,
                                max_adverse_excursion_bps=0.0,
                                max_favorable_excursion_bps=0.0,
                                was_fully_filled=True,
                                was_profitable=net_pnl > 0,
                                exit_reason="position_flat",
                            )
                            upsert_signal_reward(
                                conn,
                                signal_id=outcome_signal_id,
                                reward_net_edge_bps=net_edge_bps,
                            )
                            policy_selector.update_reward(signal_id=outcome_signal_id, reward_bps=net_edge_bps)
                        position_opened_at[symbol] = None
                        position_opened_wall_ms[symbol] = None
                        position_signal_id[symbol] = None
                        symbol_hold_timeout_sec[symbol] = float(hold_timeout_sec)
                        symbol_stop_loss_pct[symbol] = float(stop_loss_pct)
                        symbol_take_profit_pct[symbol] = float(take_profit_pct)

                    insert_order_event(
                        conn,
                        symbol=symbol,
                        order_link_id=order_link_id,
                        order_id=item.get("orderId"),
                        signal_id=signal_id,
                        side=item.get("side"),
                        order_type=item.get("orderType"),
                        price=price,
                        qty=qty,
                        order_status="Filled",
                        avg_price=price,
                        cum_exec_qty=float(item.get("execQty") or 0.0),
                        cum_exec_value=float(item.get("execValue") or 0.0) if item.get("execValue") else None,
                        created_time_ms=exec_time_ms,
                        updated_time_ms=exec_time_ms,
                    )

                    insert_fill(
                        conn,
                        symbol=symbol,
                        side="Buy" if side == "buy" else "Sell",
                        price=str(price),
                        qty=str(qty),
                        filled_at_utc=utc_now_iso(),
                        order_link_id=order_link_id,
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
            local_stop_loss = max(float(symbol_stop_loss_pct.get(symbol, stop_loss_pct)), 0.0)
            local_take_profit = max(float(symbol_take_profit_pct.get(symbol, take_profit_pct)), 0.0)
            local_hold_timeout = max(float(symbol_hold_timeout_sec.get(symbol, hold_timeout_sec)), 1.0)

            reason: str | None = None
            if pnl_exit_enabled and pnl_pct is not None:
                if local_stop_loss > 0 and pnl_pct <= -local_stop_loss:
                    reason = "stop_loss"
                elif local_take_profit > 0 and pnl_pct >= local_take_profit:
                    reason = "take_profit"

            if reason is None and age >= local_hold_timeout:
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
            set_order_signal_map(conn, order_link_id, position_signal_id.get(symbol))
            insert_order_event(
                conn,
                symbol=symbol,
                order_link_id=order_link_id,
                order_id=(ret.get("result") or {}).get("orderId"),
                signal_id=position_signal_id.get(symbol),
                side=side,
                order_type="Limit",
                time_in_force=force_exit_tif,
                price=float(price_str),
                qty=float(qty_str),
                order_status="New",
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

        async def guarded_place_order(intent: Any, time_in_force: str) -> dict[str, Any]:
            """
            Safety gateway for opening orders: pair admission + freshness + spread check.
            """
            if not config.strategy.strict_pair_filter:
                return await executor.place_order(
                    symbol=intent.symbol,
                    side=intent.side,
                    qty=_fmt_float(intent.qty),
                    price=_fmt_float(intent.price),
                    order_link_id=intent.order_link_id,
                    time_in_force=time_in_force,
                )

            snapshot = state.get_pair_filter_snapshot(intent.symbol)
            if not snapshot:
                log.info("Guarded reject: symbol=%s reason=no_filter_snapshot", intent.symbol)
                return {"retCode": 90001, "retMsg": "PAIR_FILTER_MISSING"}

            if str(snapshot.get("status", "")).upper() != "PASS":
                log.info(
                    "Guarded reject: symbol=%s reason=status_%s",
                    intent.symbol,
                    snapshot.get("status"),
                )
                return {"retCode": 90002, "retMsg": "PAIR_FILTER_NOT_PASS"}

            if bool(snapshot.get("stale_data", False)):
                log.info("Guarded reject: symbol=%s reason=stale_data", intent.symbol)
                return {"retCode": 90003, "retMsg": "STALE_DATA"}

            # Re-check filter right before sending request.
            live_decision = evaluate_pair_admission(symbol=intent.symbol, state=state, config=config)
            if live_decision.status != "PASS":
                log.info(
                    "Guarded reject: symbol=%s reason=live_%s",
                    intent.symbol,
                    live_decision.reason,
                )
                return {"retCode": 90004, "retMsg": f"LIVE_FILTER_{live_decision.status}"}

            ob = state.get_orderbook(intent.symbol)
            if ob is None or ob.mid <= 0:
                return {"retCode": 90005, "retMsg": "NO_ORDERBOOK"}

            live_spread_bps = ((ob.best_ask - ob.best_bid) / ob.mid) * 10000.0
            min_required_spread_bps = float(live_decision.metrics.get("min_required_spread_bps", 0.0))
            if live_spread_bps < min_required_spread_bps:
                log.info(
                    "Guarded reject: symbol=%s reason=spread_now_below_required spread=%.4f required=%.4f",
                    intent.symbol,
                    live_spread_bps,
                    min_required_spread_bps,
                )
                return {"retCode": 90006, "retMsg": "SPREAD_BELOW_REQUIRED"}

            if time_in_force == "PostOnly":
                if intent.side == "Buy" and intent.price >= ob.best_ask:
                    return {"retCode": 90007, "retMsg": "POSTONLY_WOULD_TAKE"}
                if intent.side == "Sell" and intent.price <= ob.best_bid:
                    return {"retCode": 90007, "retMsg": "POSTONLY_WOULD_TAKE"}

            return await executor.place_order(
                symbol=intent.symbol,
                side=intent.side,
                qty=_fmt_float(intent.qty),
                price=_fmt_float(intent.price),
                order_link_id=intent.order_link_id,
                time_in_force=time_in_force,
            )

        async def scanner_loop() -> None:
            """
            Independent worker: scans symbol universe and pushes active candidates to queue.
            """
            if not scanner_enabled:
                return

            last_pair_status_log_at = 0.0
            while True:
                await asyncio.sleep(scanner_interval_sec)
                try:
                    selected, summary = pick_active_symbols(state, config)
                    if not selected:
                        selected = list(config.symbols[: max(int(config.strategy.scanner_top_k), 1)])
                        summary["selected"] = len(selected)
                        summary["fallback"] = True
                    else:
                        summary["fallback"] = False

                    _maybe_refresh_policy_model()
                    pair_ctx = state.get_all_pair_filter_snapshots()
                    if policy_mode == "predict":
                        if policy_model is not None:
                            selected_profiles = policy_selector.select(
                                pass_symbols=selected,
                                profiles=policy_profiles,
                                ctx=pair_ctx,
                                model=policy_model,
                                eps=float(config.strategy.bandit_epsilon),
                            )
                        elif bandit_enabled:
                            selected_profiles = policy_selector.select(
                                pass_symbols=selected,
                                profiles=policy_profiles,
                                ctx=pair_ctx,
                                model=None,
                                eps=float(config.strategy.bandit_epsilon),
                            )
                        else:
                            selected_profiles = {symbol: profile_ids[0] for symbol in selected}
                    elif bandit_enabled:
                        selected_profiles = policy_selector.select(
                            pass_symbols=selected,
                            profiles=policy_profiles,
                            ctx=pair_ctx,
                            model=None,
                            eps=float(config.strategy.bandit_epsilon),
                        )
                    else:
                        selected_profiles = {symbol: profile_ids[0] for symbol in selected}
                    policy_meta = policy_selector.get_last_selection_meta()
                    for symbol in selected_profiles:
                        policy_meta.setdefault(
                            symbol,
                            {
                                "policy_used": "Bandit" if bandit_enabled else "Static",
                                "profile_id": selected_profiles[symbol],
                                "pred_open_prob": None,
                                "pred_exp_edge_bps": None,
                                "active_model_id": policy_model.model_id if policy_model is not None else None,
                                "model_id": policy_model.model_id if policy_model is not None else None,
                                "reason": "default",
                            },
                        )
                    summary["profiles"] = dict(selected_profiles)
                    summary["policy_mode"] = policy_mode
                    summary["policy_model_id"] = policy_model.model_id if policy_model is not None else ""
                    if summary.get("top_symbol"):
                        summary["top_profile"] = selected_profiles.get(str(summary["top_symbol"]), "")

                    while not candidate_queue.empty():
                        candidate_queue.get_nowait()
                    candidate_queue.put_nowait(selected)
                    state.set_active_symbols(selected)
                    state.set_active_profiles(selected_profiles)
                    state.set_active_policy_meta(policy_meta)
                    state.set_scanner_snapshot(summary)

                    now_mono = time.monotonic()
                    if now_mono - last_pair_status_log_at >= 15:
                        for symbol in config.symbols:
                            snap = state.get_pair_filter_snapshot(symbol) or {}
                            log.info(
                                "PairFilter symbol=%s status=%s reason=%s median_spread_bps=%.4f trades_per_min=%.2f p95_trade_gap_ms=%.0f depth_bid_quote=%.2f depth_ask_quote=%.2f slippage_buy_bps=%.4f slippage_sell_bps=%.4f vol_1s_bps=%.4f min_required_spread_bps=%.4f stale_data=%s data_age_ms=%s",
                                symbol,
                                snap.get("status", "NA"),
                                snap.get("reason", "NA"),
                                float(snap.get("median_spread_bps", 0.0)),
                                float(snap.get("trades_per_min", 0.0)),
                                float(snap.get("p95_trade_gap_ms", 0.0)),
                                float(snap.get("depth_bid_quote", 0.0)),
                                float(snap.get("depth_ask_quote", 0.0)),
                                float(snap.get("slippage_buy_bps", 0.0)),
                                float(snap.get("slippage_sell_bps", 0.0)),
                                float(snap.get("vol_1s_bps", 0.0)),
                                float(snap.get("min_required_spread_bps", 0.0)),
                                bool(snap.get("stale_data", True)),
                                snap.get("data_age_ms", "NA"),
                            )
                        for symbol in selected:
                            snap = state.get_pair_filter_snapshot(symbol) or {}
                            meta = policy_meta.get(symbol) or {}
                            log.info(
                                "Policy=%s, sym=%s, profile=%s, pred_open_prob=%s, pred_edge=%sbps, fee_entry=%.4f, fee_exit=%.4f, reason=%s, stale=%s",
                                str(meta.get("policy_used") or ("ML" if policy_model is not None else "Bandit")),
                                symbol,
                                str(meta.get("profile_id") or selected_profiles.get(symbol, "")),
                                "n/a" if meta.get("pred_open_prob") is None else f"{float(meta.get('pred_open_prob')):.4f}",
                                "n/a" if meta.get("pred_exp_edge_bps") is None else f"{float(meta.get('pred_exp_edge_bps')):.4f}",
                                float(snap.get("fee_entry_bps", 0.0)),
                                float(snap.get("fee_exit_bps", 0.0)),
                                str(snap.get("reason", "NA")),
                                1 if bool(snap.get("stale_data", True)) else 0,
                            )
                        last_pair_status_log_at = now_mono
                except Exception as exc:
                    log.exception("Scanner loop error: %s", exc)

        async def trading_loop() -> None:
            if executor is None:
                return

            last_paused_log_at = 0.0
            loop_no = 0
            while True:
                await asyncio.sleep(replace_interval_sec)
                loop_no += 1
                active_symbols = state.get_active_symbols() or list(config.symbols)
                if scanner_enabled:
                    while True:
                        try:
                            active_symbols = candidate_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    state.set_active_symbols(active_symbols)

                if state.panic_requested:
                    try:
                        await executor.cancel_all_orders()
                        log.warning("PANIC: all working orders cancelled.")
                    except Exception as exc:
                        log.exception("panic cancel failed: %s", exc)
                    state.set_panic_requested(False)
                    continue

                if state.paused:
                    now = time.monotonic()
                    if now - last_paused_log_at >= 10:
                        ws_books_ready = sum(1 for s in config.symbols if state.get_orderbook(s) is not None)
                        active_ws_books_ready = sum(1 for s in active_symbols if state.get_orderbook(s) is not None)
                        log.info(
                            "Trading paused: ws_books=%s/%s active_ws_books=%s/%s active_symbols=%s; resume to enable order workflow.",
                            ws_books_ready,
                            len(config.symbols),
                            active_ws_books_ready,
                            len(active_symbols),
                            ",".join(active_symbols[:8]) if active_symbols else "none",
                        )
                        last_paused_log_at = now
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
                    open_list = (resp.get("result") or {}).get("list") or []
                    for order in open_list:
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
                    managed_symbols: set[str] = set(config.symbols)
                    managed_symbols.update(s for s, q in net_position_base.items() if abs(q) >= min_position_qty)
                    for symbol in managed_symbols:
                        if await maybe_force_exit(symbol):
                            blocked_symbols.add(symbol)

                    intents = strategy.get_intents(state)
                    strategy_summary = strategy.get_last_summary()
                    risk_reject_count = 0
                    place_fail_count = 0
                    placed_count = 0

                    for intent in intents:
                        if intent.symbol in blocked_symbols:
                            continue

                        signal_id = f"sig-{intent.order_link_id}"
                        ob = state.get_orderbook(intent.symbol)
                        pair = state.get_pair_filter_snapshot(intent.symbol) or {}
                        policy_meta = state.get_active_policy_meta(intent.symbol)
                        best_bid = ob.best_bid if ob is not None else 0.0
                        best_ask = ob.best_ask if ob is not None else 0.0
                        mid = ob.mid if ob is not None else 0.0
                        spread_bps = ((best_ask - best_bid) / mid) * 10000.0 if mid > 0 and best_ask >= best_bid else 0.0
                        insert_signal_snapshot(
                            conn,
                            signal_id=signal_id,
                            ts_signal_ms=int(time.time() * 1000),
                            symbol=intent.symbol,
                            side=intent.side,
                            best_bid=best_bid,
                            best_ask=best_ask,
                            mid=mid,
                            spread_bps=spread_bps,
                            depth_bid_quote=float(pair.get("depth_bid_quote", 0.0)),
                            depth_ask_quote=float(pair.get("depth_ask_quote", 0.0)),
                            slippage_buy_bps_est=float(pair.get("slippage_buy_bps", 0.0)),
                            slippage_sell_bps_est=float(pair.get("slippage_sell_bps", 0.0)),
                            trades_per_min=float(pair.get("trades_per_min", 0.0)),
                            p95_trade_gap_ms=float(pair.get("p95_trade_gap_ms", 0.0)),
                            vol_1s_bps=float(pair.get("vol_1s_bps", 0.0)),
                            min_required_spread_bps=float(pair.get("min_required_spread_bps", 0.0)),
                            scanner_status=str(pair.get("status", "NA")),
                            model_version=str(intent.model_version or ""),
                            profile_id=intent.profile_id,
                            action_entry_tick_offset=intent.action_entry_tick_offset,
                            action_order_qty_base=intent.action_order_qty_base,
                            action_target_profit=intent.action_target_profit,
                            action_safety_buffer=intent.action_safety_buffer,
                            action_min_top_book_qty=intent.action_min_top_book_qty,
                            action_stop_loss_pct=intent.action_stop_loss_pct,
                            action_take_profit_pct=intent.action_take_profit_pct,
                            action_hold_timeout_sec=intent.action_hold_timeout_sec,
                            action_maker_only=intent.action_maker_only,
                            policy_used=str(policy_meta.get("policy_used") or ("ML" if policy_model is not None else "Bandit")),
                            pred_open_prob=(
                                float(policy_meta.get("pred_open_prob"))
                                if policy_meta.get("pred_open_prob") is not None
                                else None
                            ),
                            pred_exp_edge_bps=(
                                float(policy_meta.get("pred_exp_edge_bps"))
                                if policy_meta.get("pred_exp_edge_bps") is not None
                                else None
                            ),
                            active_model_id=str(policy_meta.get("active_model_id") or policy_model_id or ""),
                            model_id=str(
                                policy_meta.get("model_id")
                                or policy_meta.get("active_model_id")
                                or policy_model_id
                                or ""
                            ),
                            order_size_quote=float(intent.price * intent.qty),
                            order_size_base=float(intent.qty),
                            entry_price=float(intent.price),
                        )

                        risk = risk_manager.check_order(
                            intent.symbol,
                            intent.side,
                            intent.price,
                            intent.qty,
                            total_exposure,
                            symbol_exposure.get(intent.symbol, 0.0),
                        )
                        if not risk.allowed:
                            risk_reject_count += 1
                            log.debug("Risk reject: %s", risk.reason)
                            continue

                        maker_only_flag = (
                            config.strategy.maker_only
                            if intent.action_maker_only is None
                            else bool(intent.action_maker_only)
                        )
                        time_in_force = "PostOnly" if maker_only_flag else "GTC"
                        ret = await guarded_place_order(intent, time_in_force)

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
                            place_fail_count += 1
                            continue

                        placed_count += 1
                        risk_manager.register_order_placed()
                        if intent.action_hold_timeout_sec is not None:
                            symbol_hold_timeout_sec[intent.symbol] = float(max(intent.action_hold_timeout_sec, 1))
                        if intent.action_stop_loss_pct is not None:
                            symbol_stop_loss_pct[intent.symbol] = float(max(intent.action_stop_loss_pct, 0.0))
                        if intent.action_take_profit_pct is not None:
                            symbol_take_profit_pct[intent.symbol] = float(max(intent.action_take_profit_pct, 0.0))
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
                        set_order_signal_map(conn, intent.order_link_id, signal_id)
                        insert_order_event(
                            conn,
                            symbol=intent.symbol,
                            order_link_id=intent.order_link_id,
                            order_id=(ret.get("result") or {}).get("orderId"),
                            signal_id=signal_id,
                            side=intent.side,
                            order_type="Limit",
                            time_in_force=time_in_force,
                            price=float(intent.price),
                            qty=float(intent.qty),
                            order_status="New",
                        )

                    ws_books_ready = sum(1 for s in config.symbols if state.get_orderbook(s) is not None)
                    active_ws_books_ready = sum(1 for s in active_symbols if state.get_orderbook(s) is not None)
                    scanner_snapshot = state.get_scanner_snapshot()
                    log.info(
                        "Loop #%s: ws_books=%s/%s active_ws_books=%s/%s active_symbols=%s open_orders=%s mm_canceled=%s intents=%s placed=%s risk_reject=%s place_fail=%s blocked_symbols=%s scanner=%s strategy=%s",
                        loop_no,
                        ws_books_ready,
                        len(config.symbols),
                        active_ws_books_ready,
                        len(active_symbols),
                        ",".join(active_symbols[:8]) if active_symbols else "none",
                        len(open_list),
                        len(our_order_link_ids),
                        len(intents),
                        placed_count,
                        risk_reject_count,
                        place_fail_count,
                        len(blocked_symbols),
                        scanner_snapshot,
                        strategy_summary,
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

        async def universe_loop() -> None:
            if not auto_universe_enabled:
                return

            while True:
                await asyncio.sleep(auto_universe_refresh_sec)
                try:
                    discovered = await discover_top_spot_symbols(
                        host=config.strategy.auto_universe_host,
                        quote=config.strategy.auto_universe_quote,
                        limit=config.strategy.auto_universe_size,
                        min_turnover_24h=config.strategy.auto_universe_min_turnover_24h,
                        min_raw_spread_bps=config.strategy.auto_universe_min_raw_spread_bps,
                        min_top_book_notional=config.strategy.auto_universe_min_top_book_notional,
                        exclude_st_tag_1=config.strategy.auto_universe_exclude_st_tag_1,
                    )
                    if not discovered:
                        continue

                    # Keep symbols with open position in the universe to preserve exit control.
                    protected = [s for s, q in net_position_base.items() if abs(q) >= min_position_qty]
                    merged: list[str] = []
                    seen: set[str] = set()
                    for symbol in protected + discovered:
                        s = symbol.strip().upper()
                        if not s or s in seen:
                            continue
                        seen.add(s)
                        merged.append(s)

                    if not merged or merged == config.symbols:
                        continue

                    old_count = len(config.symbols)
                    config.symbols = merged
                    for s in merged:
                        net_position_base.setdefault(s, 0.0)
                        avg_entry_price.setdefault(s, 0.0)
                        position_signal_id.setdefault(s, None)
                        position_opened_wall_ms.setdefault(s, None)
                        position_opened_at.setdefault(s, None)
                        last_force_exit_ts.setdefault(s, 0.0)
                        symbol_hold_timeout_sec.setdefault(s, float(hold_timeout_sec))
                        symbol_stop_loss_pct.setdefault(s, float(stop_loss_pct))
                        symbol_take_profit_pct.setdefault(s, float(take_profit_pct))

                    await ws.update_symbols(merged)

                    # Keep current active symbols if possible, otherwise pick first scanner_top_k.
                    current_active = [s for s in state.get_active_symbols() if s in set(merged)]
                    if not current_active:
                        current_active = merged[: max(int(config.strategy.scanner_top_k), 1)]
                    state.set_active_symbols(current_active)
                    state.set_active_profiles({s: state.get_active_profile_id(s) or profile_ids[0] for s in current_active})
                    state.set_active_policy_meta(
                        {
                            s: state.get_active_policy_meta(s)
                            or {
                                "policy_used": "Static",
                                "profile_id": state.get_active_profile_id(s) or profile_ids[0],
                                "pred_open_prob": None,
                                "pred_exp_edge_bps": None,
                                "active_model_id": policy_model_id,
                                "model_id": policy_model_id,
                                "reason": "universe_refresh",
                            }
                            for s in current_active
                        }
                    )

                    log.info(
                        "Universe refreshed: old=%s new=%s top=%s",
                        old_count,
                        len(merged),
                        ",".join(merged[:8]),
                    )
                except Exception as exc:
                    log.warning("Auto-universe refresh failed: %s", exc)

        try:
            await asyncio.gather(ws.run(), metrics_loop(), scanner_loop(), universe_loop(), trading_loop())
        finally:
            conn.close()

    asyncio.run(run_ws_metrics_trading())


if __name__ == "__main__":
    main()
