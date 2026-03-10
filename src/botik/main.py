"""
CLI entrypoint: config, logging, WS market data, strategy, risk checks and execution.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import importlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from src.botik.config import ActionProfileConfig, AppConfig, load_config
from src.botik.control.telegram_bot import start_telegram_bot_in_thread
from src.botik.execution.bybit_rest import BybitRestClient
from src.botik.execution.paper import PaperTradingClient
from src.botik.execution.reconciliation_service import ExchangeReconciliationService
from src.botik.marketdata.universe_discovery import discover_top_symbols_by_category
from src.botik.marketdata.ws_public import BybitPublicOrderbookWS
from src.botik.learning.bandit import GaussianThompsonBandit
from src.botik.learning.policy import PolicySelector
from src.botik.learning.policy_manager import ModelBundle, load_active_model
from src.botik.risk.futures_protection import build_futures_protection_plan, futures_entry_allowed
from src.botik.risk.futures_rules import (
    classify_futures_state,
    compute_distance_to_liq_bps,
    is_entry_blocking_futures_risk_state,
    is_blocking_protection_status,
    normalize_protection_status,
    transition_protection_status,
)
from src.botik.risk.spot_rules import can_auto_sell_hold
from src.botik.risk.manager import RiskManager
from src.botik.risk.exit_rules import decide_exit_reason
from src.botik.risk.position import apply_fill, unrealized_pnl_pct
from src.botik.state.state import TradingState
from src.botik.version import get_app_version_label
from src.botik.storage.sqlite_store import (
    get_connection,
    insert_fill,
    insert_metrics,
    insert_metrics_batch,
    insert_order,
    update_order_status,
    update_orders_entry_exit_for_signal,
)
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
from src.botik.storage.spot_store import (
    insert_spot_exit_decision,
    insert_spot_fill,
    insert_spot_position_intent,
    upsert_spot_holding,
    upsert_spot_order,
)
from src.botik.storage.core_store import insert_event_audit, upsert_strategy_run
from src.botik.storage.futures_store import (
    insert_futures_fill,
    insert_futures_position_decision,
    upsert_futures_open_order,
    upsert_futures_position,
    upsert_futures_protection,
)
from src.botik.strategy.micro_spread import MicroSpreadStrategy
from src.botik.strategy.spike_reversal import SpikeReversalStrategy
from src.botik.strategy.pair_admission import evaluate_pair_admission
from src.botik.strategy.symbol_scanner import pick_active_symbols
from src.botik.utils.logging import setup_logging
from src.botik.utils.runtime import runtime_root
from src.botik.utils.time import utc_now_iso

ROOT_DIR = runtime_root(__file__, levels_up=2)
VERSION_FILE = ROOT_DIR / "version.txt"


class RestartRequested(Exception):
    """Raised to rebuild runtime loops without canceling existing exchange orders."""


def _fmt_float(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def resolve_risk_leverage(config: AppConfig, runtime_market_category: str) -> float:
    if str(runtime_market_category or "").strip().lower() != "linear":
        return 1.0
    try:
        return max(float(getattr(config.risk, "default_leverage", 1.0)), 1.0)
    except (TypeError, ValueError):
        return 1.0


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


RECONCILIATION_ENTRY_LOCK_ISSUES = (
    "orphaned_exchange_position",
    "orphaned_exchange_order",
    "local_position_missing_on_exchange",
    "local_order_missing_on_exchange",
)


def load_reconciliation_symbol_locks(conn: sqlite3.Connection) -> dict[str, list[str]]:
    placeholders = ",".join("?" for _ in RECONCILIATION_ENTRY_LOCK_ISSUES)
    rows = conn.execute(
        f"""
        SELECT UPPER(COALESCE(symbol, '')), COALESCE(issue_type, '')
        FROM reconciliation_issues
        WHERE status='open'
          AND issue_type IN ({placeholders})
          AND COALESCE(symbol, '') <> ''
        ORDER BY created_at_utc DESC
        """,
        tuple(RECONCILIATION_ENTRY_LOCK_ISSUES),
    ).fetchall()
    by_symbol: dict[str, set[str]] = {}
    for symbol, issue_type in rows:
        symbol_u = str(symbol or "").upper().strip()
        issue = str(issue_type or "").strip()
        if not symbol_u or not issue:
            continue
        by_symbol.setdefault(symbol_u, set()).add(issue)
    return {symbol: sorted(issues) for symbol, issues in by_symbol.items()}


def get_reconciliation_entry_block_reason(
    conn: sqlite3.Connection,
    *,
    symbol: str,
) -> str | None:
    symbol_u = str(symbol or "").upper().strip()
    if not symbol_u:
        return None
    lock_map = load_reconciliation_symbol_locks(conn)
    issues = lock_map.get(symbol_u) or []
    if not issues:
        return None
    return ",".join(issues)


def get_futures_blocking_protection_status(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    account_type: str = "UNIFIED",
) -> str | None:
    row = conn.execute(
        """
        SELECT LOWER(COALESCE(protection_status, ''))
        FROM futures_positions
        WHERE account_type=?
          AND symbol=?
          AND ABS(COALESCE(qty, 0)) > 0
        ORDER BY updated_at_utc DESC
        LIMIT 1
        """,
        (str(account_type), str(symbol or "").upper()),
    ).fetchone()
    if not row:
        return None
    status = normalize_protection_status(row[0] if row else "")
    if not is_blocking_protection_status(status):
        return None
    return status


def evaluate_futures_symbol_risk(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    account_type: str = "UNIFIED",
    fallback_mark_price: float | None = None,
) -> dict[str, Any]:
    symbol_u = str(symbol or "").upper().strip()
    row = conn.execute(
        """
        SELECT
            COALESCE(side, ''),
            ABS(COALESCE(qty, 0)),
            COALESCE(entry_price, 0),
            COALESCE(mark_price, 0),
            COALESCE(liq_price, 0),
            COALESCE(protection_status, ''),
            COALESCE(updated_at_utc, '')
        FROM futures_positions
        WHERE account_type=?
          AND symbol=?
          AND ABS(COALESCE(qty, 0)) > 0
        ORDER BY updated_at_utc DESC
        LIMIT 1
        """,
        (str(account_type), symbol_u),
    ).fetchone()
    if not row:
        return {
            "symbol": symbol_u,
            "risk_state": "unknown",
            "protection_status": "",
            "distance_to_liq_bps": None,
            "unrealized_pnl_pct": None,
            "position_side": "",
            "position_qty": 0.0,
            "entry_price": None,
            "mark_price": None,
            "liq_price": None,
            "updated_at_utc": "",
        }
    side = str(row[0] or "")
    qty_abs = float(row[1] or 0.0)
    qty_signed = qty_abs if side.strip().lower() in {"buy", "long"} else -qty_abs
    entry_price = float(row[2] or 0.0)
    mark_price_db = float(row[3] or 0.0)
    liq_price = float(row[4] or 0.0)
    protection_status = normalize_protection_status(row[5] or "")
    updated_at_utc = str(row[6] or "")

    mark_price = mark_price_db if mark_price_db > 0 else float(fallback_mark_price or 0.0)
    if mark_price <= 0:
        mark_price = 0.0

    pnl_pct: float | None = None
    if qty_abs > 0 and entry_price > 0 and mark_price > 0:
        pnl_pct = unrealized_pnl_pct(
            position_qty=qty_signed,
            avg_entry_price=entry_price,
            mark_price=mark_price,
        )

    distance_to_liq_bps = compute_distance_to_liq_bps(
        side=side,
        mark_price=(mark_price if mark_price > 0 else None),
        liq_price=(liq_price if liq_price > 0 else None),
    )
    risk_state = classify_futures_state(
        protection_status=protection_status,
        unrealized_pnl_pct=pnl_pct,
        distance_to_liq_bps=distance_to_liq_bps,
    )
    return {
        "symbol": symbol_u,
        "risk_state": str(risk_state),
        "protection_status": protection_status,
        "distance_to_liq_bps": distance_to_liq_bps,
        "unrealized_pnl_pct": pnl_pct,
        "position_side": side,
        "position_qty": qty_abs,
        "entry_price": (entry_price if entry_price > 0 else None),
        "mark_price": (mark_price if mark_price > 0 else None),
        "liq_price": (liq_price if liq_price > 0 else None),
        "updated_at_utc": updated_at_utc,
    }


def futures_entry_risk_gate(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    account_type: str = "UNIFIED",
    fallback_mark_price: float | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    risk_view = evaluate_futures_symbol_risk(
        conn,
        symbol=symbol,
        account_type=account_type,
        fallback_mark_price=fallback_mark_price,
    )
    risk_state = str(risk_view.get("risk_state") or "").strip().lower()
    if is_entry_blocking_futures_risk_state(risk_state):
        return False, f"symbol_risk_state_{risk_state}", risk_view
    return True, "ok", risk_view


def futures_force_exit_reason_from_risk_state(
    *,
    current_reason: str | None,
    risk_state: str | None,
) -> str | None:
    risk = str(risk_state or "").strip().lower()
    if risk == "hard_failure":
        return current_reason or "futures_hard_failure"
    if risk == "unprotected_position":
        return current_reason or "futures_unprotected_position"
    return current_reason


def write_runtime_order_legacy_and_domain(
    conn: sqlite3.Connection,
    *,
    market_category: str,
    symbol: str,
    side: str,
    order_link_id: str,
    price: float,
    qty: float,
    status: str,
    created_at_utc: str,
    log: logging.Logger,
    exchange_order_id: str | None = None,
    order_type: str = "Limit",
    time_in_force: str | None = None,
    strategy_owner: str | None = None,
    filled_qty: float = 0.0,
) -> int:
    row_id = insert_order(
        conn,
        symbol=symbol,
        side=side,
        order_link_id=order_link_id,
        price=_fmt_float(float(price)),
        qty=_fmt_float(float(qty)),
        status=str(status),
        created_at_utc=created_at_utc,
        exchange_order_id=exchange_order_id,
    )
    try:
        if str(market_category or "").strip().lower() == "linear":
            upsert_futures_open_order(
                conn,
                account_type="UNIFIED",
                symbol=str(symbol).upper(),
                side=str(side),
                status=str(status),
                order_link_id=(order_link_id or None),
                order_id=exchange_order_id,
                order_type=order_type,
                time_in_force=time_in_force,
                price=float(price),
                qty=float(qty),
                reduce_only=(True if str(order_link_id or "").startswith("px-") else None),
                strategy_owner=strategy_owner,
            )
        else:
            upsert_spot_order(
                conn,
                account_type="UNIFIED",
                symbol=str(symbol).upper(),
                side=str(side),
                status=str(status),
                order_link_id=(order_link_id or None),
                order_id=exchange_order_id,
                order_type=order_type,
                time_in_force=time_in_force,
                price=float(price),
                qty=float(qty),
                filled_qty=float(filled_qty),
                strategy_owner=strategy_owner,
            )
    except Exception as exc:
        log.warning(
            "Domain order mirror failed: category=%s symbol=%s side=%s link=%s status=%s err=%s",
            market_category,
            symbol,
            side,
            order_link_id,
            status,
            exc,
        )
    return int(row_id or 0)


def write_runtime_fill_legacy_and_domain(
    conn: sqlite3.Connection,
    *,
    market_category: str,
    symbol: str,
    side: str,
    exec_id: str,
    price: float,
    qty: float,
    filled_at_utc: str,
    log: logging.Logger,
    order_link_id: str | None = None,
    exchange_order_id: str | None = None,
    fee: float | None = None,
    fee_currency: str | None = None,
    is_maker: bool | None = None,
    exec_time_ms: int | None = None,
) -> None:
    insert_fill(
        conn,
        symbol=symbol,
        side=side,
        price=str(price),
        qty=str(qty),
        filled_at_utc=filled_at_utc,
        order_link_id=order_link_id,
        exchange_order_id=exchange_order_id,
        fee=("" if fee is None else str(fee)),
        fee_currency=fee_currency,
        liquidity="Maker" if bool(is_maker) else "Taker",
    )
    try:
        if str(market_category or "").strip().lower() == "linear":
            insert_futures_fill(
                conn,
                account_type="UNIFIED",
                symbol=str(symbol).upper(),
                side=str(side),
                exec_id=str(exec_id),
                order_id=exchange_order_id,
                order_link_id=order_link_id,
                price=float(price),
                qty=float(qty),
                exec_fee=(float(fee) if fee is not None else None),
                fee_currency=fee_currency,
                is_maker=is_maker,
                exec_time_ms=exec_time_ms,
            )
        else:
            insert_spot_fill(
                conn,
                account_type="UNIFIED",
                symbol=str(symbol).upper(),
                side=str(side),
                exec_id=str(exec_id),
                order_id=exchange_order_id,
                order_link_id=order_link_id,
                price=float(price),
                qty=float(qty),
                fee=(float(fee) if fee is not None else None),
                fee_currency=fee_currency,
                is_maker=is_maker,
                exec_time_ms=exec_time_ms,
            )
    except Exception as exc:
        log.warning(
            "Domain fill mirror failed: category=%s symbol=%s side=%s exec_id=%s err=%s",
            market_category,
            symbol,
            side,
            exec_id,
            exc,
        )


def write_spot_position_intent_safe(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    order_link_id: str,
    strategy_owner: str,
    profile_id: str | None,
    signal_id: str | None,
    log: logging.Logger,
) -> None:
    try:
        insert_spot_position_intent(
            conn,
            intent_id=f"sp-intent-{order_link_id}",
            account_type="UNIFIED",
            symbol=str(symbol).upper(),
            side=str(side),
            intended_qty=float(abs(qty)),
            intended_price=float(price),
            strategy_owner=strategy_owner,
            profile_id=profile_id,
            signal_id=signal_id,
            status="accepted_for_send",
        )
    except Exception as exc:
        log.warning(
            "spot_position_intent write failed: symbol=%s side=%s link=%s err=%s",
            symbol,
            side,
            order_link_id,
            exc,
        )


def write_spot_exit_decision_safe(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    decision_type: str,
    reason: str,
    pnl_pct: float | None,
    payload: dict[str, Any],
    applied: bool,
    log: logging.Logger,
) -> None:
    try:
        insert_spot_exit_decision(
            conn,
            account_type="UNIFIED",
            symbol=str(symbol).upper(),
            decision_type=str(decision_type),
            reason=str(reason),
            policy_name="runtime",
            pnl_pct=pnl_pct,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            applied=applied,
        )
    except Exception as exc:
        log.warning(
            "spot_exit_decision write failed: symbol=%s decision=%s reason=%s err=%s",
            symbol,
            decision_type,
            reason,
            exc,
        )


async def verify_futures_protection_from_exchange(
    executor: Any,
    *,
    symbol: str,
    side: str,
    position_idx: int = 0,
) -> tuple[str, dict[str, Any]]:
    get_positions = getattr(executor, "get_positions", None)
    if not callable(get_positions):
        return "failed", {"verify_reason": "positions_api_unsupported"}
    try:
        resp = await get_positions(symbol=str(symbol).upper())
    except Exception as exc:
        return "failed", {"verify_reason": "positions_api_error", "error": str(exc)}
    if resp.get("retCode") != 0:
        return "failed", {
            "verify_reason": "positions_api_rejected",
            "retCode": resp.get("retCode"),
            "retMsg": resp.get("retMsg"),
        }
    items = (resp.get("result") or {}).get("list") or []
    symbol_u = str(symbol or "").upper().strip()
    side_u = str(side or "").strip()
    candidate: dict[str, Any] | None = None
    for item in items:
        item_symbol = str(item.get("symbol") or "").upper().strip()
        if item_symbol != symbol_u:
            continue
        qty = float(item.get("size") or item.get("qty") or 0.0)
        if abs(qty) <= 0:
            continue
        item_side = str(item.get("side") or "").strip()
        item_idx = int(item.get("positionIdx") or 0)
        if item_side == side_u and item_idx == int(position_idx):
            candidate = dict(item)
            break
        if candidate is None:
            candidate = dict(item)

    if candidate is None:
        return "closed", {"verify_reason": "position_not_found"}

    stop_loss = float(candidate.get("stopLoss") or 0.0)
    take_profit = float(candidate.get("takeProfit") or 0.0)
    trailing = float(candidate.get("trailingStop") or 0.0)
    if stop_loss > 0 and take_profit > 0:
        return "protected", {
            "verify_reason": "confirmed_on_exchange",
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop": trailing,
            "position_idx": int(candidate.get("positionIdx") or 0),
            "qty": float(candidate.get("size") or candidate.get("qty") or 0.0),
        }
    return "unprotected", {
        "verify_reason": "missing_stop_or_take_on_exchange",
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trailing_stop": trailing,
        "position_idx": int(candidate.get("positionIdx") or 0),
        "qty": float(candidate.get("size") or candidate.get("qty") or 0.0),
    }


def executor_supports_capability(
    executor: Any | None,
    capability: str,
    *,
    market_category: str | None = None,
) -> bool:
    if executor is None:
        return False
    capability_key = str(capability or "").strip().lower()
    if not capability_key:
        return False

    caps = getattr(executor, "capabilities", None)
    if isinstance(caps, dict) and capability_key in caps:
        return bool(caps.get(capability_key))

    explicit_attr = f"supports_{capability_key}"
    if hasattr(executor, explicit_attr):
        return bool(getattr(executor, explicit_attr))

    if capability_key == "reconciliation":
        required = ["get_wallet_balance", "get_open_orders", "get_execution_list"]
        if str(market_category or "").strip().lower() == "linear":
            required.append("get_positions")
        return all(callable(getattr(executor, name, None)) for name in required)
    if capability_key == "protection":
        required = ["set_trading_stop", "get_positions"]
        return all(callable(getattr(executor, name, None)) for name in required)
    if capability_key == "positions":
        return callable(getattr(executor, "get_positions", None))
    if capability_key == "wallet_balance":
        return callable(getattr(executor, "get_wallet_balance", None))
    if capability_key == "trading_stop":
        return callable(getattr(executor, "set_trading_stop", None))
    return False


async def run_reconciliation_startup(
    service: ExchangeReconciliationService | None,
    *,
    log: logging.Logger,
) -> tuple[float, dict[str, Any] | None]:
    if service is None:
        return 0.0, None
    summary = await service.run(trigger_source="startup")
    log.info("Reconciliation startup summary: %s", summary)
    return time.monotonic(), summary


async def run_reconciliation_scheduled_if_due(
    service: ExchangeReconciliationService | None,
    *,
    last_run_ts: float,
    interval_sec: float,
    log: logging.Logger,
) -> tuple[float, dict[str, Any] | None]:
    if service is None:
        return last_run_ts, None
    now_ts = time.monotonic()
    if (now_ts - float(last_run_ts)) < float(interval_sec):
        return last_run_ts, None
    summary = await service.run(trigger_source="scheduled")
    log.info("Reconciliation scheduled summary: %s", summary)
    return now_ts, summary


def _git_head(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()
    except Exception:
        return ""


def _resolve_runtime_version() -> str:
    v = _git_head(ROOT_DIR)
    if v:
        return v
    if VERSION_FILE.exists():
        try:
            return VERSION_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _hot_reload_runtime_modules() -> None:
    module_names = [
        "src.botik.config",
        "src.botik.execution.bybit_rest",
        "src.botik.execution.paper",
        "src.botik.execution.reconciliation_service",
        "src.botik.marketdata.universe_discovery",
        "src.botik.marketdata.ws_public",
        "src.botik.learning.bandit",
        "src.botik.learning.policy",
        "src.botik.learning.policy_manager",
        "src.botik.risk.manager",
        "src.botik.risk.exit_rules",
        "src.botik.risk.futures_protection",
        "src.botik.risk.futures_rules",
        "src.botik.risk.spot_rules",
        "src.botik.risk.position",
        "src.botik.storage.sqlite_store",
        "src.botik.storage.lifecycle_store",
        "src.botik.storage.core_store",
        "src.botik.storage.spot_store",
        "src.botik.storage.futures_store",
        "src.botik.strategy.micro_spread",
        "src.botik.strategy.spike_reversal",
        "src.botik.strategy.pair_admission",
        "src.botik.strategy.symbol_scanner",
        "src.botik.utils.logging",
        "src.botik.utils.time",
    ]
    for name in module_names:
        if name in sys.modules:
            importlib.reload(sys.modules[name])

    # Rebind imported symbols used by runtime loop.
    from src.botik.config import ActionProfileConfig as _ActionProfileConfig, load_config as _load_config
    from src.botik.execution.bybit_rest import BybitRestClient as _BybitRestClient
    from src.botik.execution.paper import PaperTradingClient as _PaperTradingClient
    from src.botik.execution.reconciliation_service import ExchangeReconciliationService as _ExchangeReconciliationService
    from src.botik.learning.bandit import GaussianThompsonBandit as _GaussianThompsonBandit
    from src.botik.learning.policy import PolicySelector as _PolicySelector
    from src.botik.learning.policy_manager import ModelBundle as _ModelBundle, load_active_model as _load_active_model
    from src.botik.marketdata.universe_discovery import discover_top_symbols_by_category as _discover_top_symbols_by_category
    from src.botik.marketdata.ws_public import BybitPublicOrderbookWS as _BybitPublicOrderbookWS
    from src.botik.risk.manager import RiskManager as _RiskManager
    from src.botik.risk.exit_rules import decide_exit_reason as _decide_exit_reason
    from src.botik.risk.futures_protection import (
        build_futures_protection_plan as _build_futures_protection_plan,
        futures_entry_allowed as _futures_entry_allowed,
    )
    from src.botik.risk.futures_rules import (
        classify_futures_state as _classify_futures_state,
        compute_distance_to_liq_bps as _compute_distance_to_liq_bps,
        is_entry_blocking_futures_risk_state as _is_entry_blocking_futures_risk_state,
        is_blocking_protection_status as _is_blocking_protection_status,
        normalize_protection_status as _normalize_protection_status,
        transition_protection_status as _transition_protection_status,
    )
    from src.botik.risk.spot_rules import can_auto_sell_hold as _can_auto_sell_hold
    from src.botik.risk.position import apply_fill as _apply_fill, unrealized_pnl_pct as _unrealized_pnl_pct
    from src.botik.storage.lifecycle_store import (
        ensure_lifecycle_schema as _ensure_lifecycle_schema,
        get_signal_id_for_order_link as _get_signal_id_for_order_link,
        insert_execution_event as _insert_execution_event,
        insert_order_event as _insert_order_event,
        insert_signal_snapshot as _insert_signal_snapshot,
        set_order_signal_map as _set_order_signal_map,
        upsert_outcome as _upsert_outcome,
        upsert_signal_reward as _upsert_signal_reward,
    )
    from src.botik.storage.sqlite_store import (
        get_connection as _get_connection,
        insert_fill as _insert_fill,
        insert_metrics as _insert_metrics,
        insert_metrics_batch as _insert_metrics_batch,
        insert_order as _insert_order,
        update_orders_entry_exit_for_signal as _update_orders_entry_exit_for_signal,
    )
    from src.botik.storage.spot_store import (
        insert_spot_exit_decision as _insert_spot_exit_decision,
        insert_spot_fill as _insert_spot_fill,
        insert_spot_position_intent as _insert_spot_position_intent,
        upsert_spot_holding as _upsert_spot_holding,
        upsert_spot_order as _upsert_spot_order,
    )
    from src.botik.storage.core_store import (
        insert_event_audit as _insert_event_audit,
        upsert_strategy_run as _upsert_strategy_run,
    )
    from src.botik.storage.futures_store import (
        insert_futures_fill as _insert_futures_fill,
        insert_futures_position_decision as _insert_futures_position_decision,
        upsert_futures_open_order as _upsert_futures_open_order,
        upsert_futures_position as _upsert_futures_position,
        upsert_futures_protection as _upsert_futures_protection,
    )
    from src.botik.strategy.micro_spread import MicroSpreadStrategy as _MicroSpreadStrategy
    from src.botik.strategy.spike_reversal import SpikeReversalStrategy as _SpikeReversalStrategy
    from src.botik.strategy.pair_admission import evaluate_pair_admission as _evaluate_pair_admission
    from src.botik.strategy.symbol_scanner import pick_active_symbols as _pick_active_symbols
    from src.botik.utils.logging import setup_logging as _setup_logging
    from src.botik.utils.time import utc_now_iso as _utc_now_iso

    globals()["ActionProfileConfig"] = _ActionProfileConfig
    globals()["load_config"] = _load_config
    globals()["BybitRestClient"] = _BybitRestClient
    globals()["PaperTradingClient"] = _PaperTradingClient
    globals()["ExchangeReconciliationService"] = _ExchangeReconciliationService
    globals()["discover_top_symbols_by_category"] = _discover_top_symbols_by_category
    globals()["BybitPublicOrderbookWS"] = _BybitPublicOrderbookWS
    globals()["GaussianThompsonBandit"] = _GaussianThompsonBandit
    globals()["PolicySelector"] = _PolicySelector
    globals()["ModelBundle"] = _ModelBundle
    globals()["load_active_model"] = _load_active_model
    globals()["RiskManager"] = _RiskManager
    globals()["decide_exit_reason"] = _decide_exit_reason
    globals()["build_futures_protection_plan"] = _build_futures_protection_plan
    globals()["futures_entry_allowed"] = _futures_entry_allowed
    globals()["normalize_protection_status"] = _normalize_protection_status
    globals()["is_blocking_protection_status"] = _is_blocking_protection_status
    globals()["compute_distance_to_liq_bps"] = _compute_distance_to_liq_bps
    globals()["classify_futures_state"] = _classify_futures_state
    globals()["is_entry_blocking_futures_risk_state"] = _is_entry_blocking_futures_risk_state
    globals()["transition_protection_status"] = _transition_protection_status
    globals()["can_auto_sell_hold"] = _can_auto_sell_hold
    globals()["apply_fill"] = _apply_fill
    globals()["unrealized_pnl_pct"] = _unrealized_pnl_pct
    globals()["get_connection"] = _get_connection
    globals()["insert_fill"] = _insert_fill
    globals()["insert_metrics"] = _insert_metrics
    globals()["insert_metrics_batch"] = _insert_metrics_batch
    globals()["insert_order"] = _insert_order
    globals()["update_orders_entry_exit_for_signal"] = _update_orders_entry_exit_for_signal
    globals()["insert_spot_exit_decision"] = _insert_spot_exit_decision
    globals()["insert_spot_fill"] = _insert_spot_fill
    globals()["insert_spot_position_intent"] = _insert_spot_position_intent
    globals()["upsert_spot_holding"] = _upsert_spot_holding
    globals()["upsert_spot_order"] = _upsert_spot_order
    globals()["insert_event_audit"] = _insert_event_audit
    globals()["upsert_strategy_run"] = _upsert_strategy_run
    globals()["insert_futures_fill"] = _insert_futures_fill
    globals()["insert_futures_position_decision"] = _insert_futures_position_decision
    globals()["upsert_futures_open_order"] = _upsert_futures_open_order
    globals()["upsert_futures_position"] = _upsert_futures_position
    globals()["upsert_futures_protection"] = _upsert_futures_protection
    globals()["ensure_lifecycle_schema"] = _ensure_lifecycle_schema
    globals()["get_signal_id_for_order_link"] = _get_signal_id_for_order_link
    globals()["insert_execution_event"] = _insert_execution_event
    globals()["insert_order_event"] = _insert_order_event
    globals()["insert_signal_snapshot"] = _insert_signal_snapshot
    globals()["set_order_signal_map"] = _set_order_signal_map
    globals()["upsert_signal_reward"] = _upsert_signal_reward
    globals()["upsert_outcome"] = _upsert_outcome
    globals()["MicroSpreadStrategy"] = _MicroSpreadStrategy
    globals()["SpikeReversalStrategy"] = _SpikeReversalStrategy
    globals()["evaluate_pair_admission"] = _evaluate_pair_admission
    globals()["pick_active_symbols"] = _pick_active_symbols
    globals()["setup_logging"] = _setup_logging
    globals()["utc_now_iso"] = _utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit Bot")
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
        "Config loaded: version=%s host=%s ws=%s category=%s strategy=%s symbols=%s start_paused=%s execution_mode=%s",
        app_version,
        config.bybit.host,
        config.bybit.ws_public_host,
        config.bybit.market_category,
        config.strategy.runtime_strategy,
        config.symbols,
        config.start_paused,
        config.execution.mode,
    )

    state = TradingState()
    state.paused = config.start_paused
    state.set_current_version(_resolve_runtime_version())

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

        runtime_market_category = str(config.bybit.market_category or "spot").strip().lower()
        if runtime_market_category not in {"spot", "linear"}:
            log.warning("Unknown bybit.market_category=%s, fallback to spot", runtime_market_category)
            runtime_market_category = "spot"
        runtime_strategy_mode = str(config.strategy.runtime_strategy or "spread_maker").strip().lower()
        if runtime_strategy_mode not in {"spread_maker", "spike_reversal"}:
            log.warning("Unknown strategy.runtime_strategy=%s, fallback to spread_maker", runtime_strategy_mode)
            runtime_strategy_mode = "spread_maker"

        executor: Any | None = None
        mode = config.execution.mode.lower().strip()
        if mode == "paper":
            executor = PaperTradingClient(
                state=state,
                fill_on_cross=config.execution.paper_fill_on_cross,
                category=runtime_market_category,
            )
            log.info("Execution mode: paper (no real exchange orders).")
        elif api_key and (api_secret or rsa_private_key_path):
            executor = BybitRestClient(
                base_url=f"https://{config.bybit.host}",
                api_key=api_key,
                api_secret=api_secret,
                rsa_private_key_path=rsa_private_key_path,
                category=runtime_market_category,
            )
            log.info(
                "Execution mode: live auth=%s host=%s category=%s recv_window=%s",
                executor.auth_mode,
                config.bybit.host,
                runtime_market_category,
                executor.recv_window,
            )
        else:
            log.warning("Execution is disabled: set execution.mode=paper or BYBIT credentials for live mode.")

        auto_universe_enabled = bool(config.strategy.auto_universe_enabled)
        auto_universe_refresh_sec = max(float(config.strategy.auto_universe_refresh_sec), 30.0)

        if auto_universe_enabled:
            try:
                discovered = await discover_top_symbols_by_category(
                    runtime_market_category,
                    host=config.strategy.auto_universe_host,
                    quote=config.strategy.auto_universe_quote,
                    limit=config.strategy.auto_universe_size,
                    min_symbols=config.strategy.auto_universe_min_symbols,
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
        if runtime_strategy_mode == "spike_reversal":
            strategy = SpikeReversalStrategy(config)
            if runtime_market_category != "linear":
                log.warning(
                    "runtime_strategy=spike_reversal is designed for linear futures, current market_category=%s",
                    runtime_market_category,
                )
        else:
            strategy = MicroSpreadStrategy(config)
        log.info(
            "Runtime strategy: mode=%s class=%s market_category=%s",
            runtime_strategy_mode,
            strategy.__class__.__name__,
            runtime_market_category,
        )
        strategy_run_id = f"run-{uuid.uuid4().hex[:16]}"
        strategy_run_started_at = utc_now_iso()
        upsert_strategy_run(
            conn,
            strategy_run_id=strategy_run_id,
            strategy_name=strategy.__class__.__name__,
            market_category=runtime_market_category,
            status="running",
            started_at_utc=strategy_run_started_at,
            config_payload={
                "runtime_strategy_mode": runtime_strategy_mode,
                "symbols": list(config.symbols),
                "execution_mode": mode,
            },
        )
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
        policy_ml_enabled = policy_mode in {"predict", "online"}
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
        min_active_position_usdt = max(float(getattr(config.strategy, "min_active_position_usdt", 1.0) or 1.0), 0.0)
        spot_notional_floor_enabled = runtime_market_category == "spot"
        hold_timeout_sec = config.strategy.position_hold_timeout_sec
        force_exit_enabled = config.strategy.force_exit_enabled
        force_exit_tif = config.strategy.force_exit_time_in_force
        force_exit_use_market = bool(config.strategy.force_exit_use_market)
        allow_taker_exit = bool(config.strategy.allow_taker_exit)
        force_exit_cooldown_sec = config.strategy.force_exit_cooldown_sec
        force_exit_dust_cooldown_sec = max(float(config.strategy.force_exit_dust_cooldown_sec), float(force_exit_cooldown_sec))
        execution_refresh_interval_sec = max(float(config.strategy.execution_refresh_interval_sec), 1.0)
        execution_refresh_max_symbols = max(int(config.strategy.execution_refresh_max_symbols), 1)
        execution_refresh_concurrency = max(int(config.strategy.execution_refresh_concurrency), 1)
        reconciliation_enabled = bool(getattr(config.strategy, "reconciliation_enabled", True))
        reconciliation_interval_sec = max(float(getattr(config.strategy, "reconciliation_interval_sec", 120) or 120), 15.0)
        reconciliation_symbols_limit = max(int(getattr(config.strategy, "reconciliation_symbols_limit", 120) or 120), 1)
        fast_reprice_on_send = bool(config.strategy.fast_reprice_on_send)
        quote_max_book_age_ms = max(int(config.strategy.quote_max_book_age_ms), 100)
        stop_loss_pct = max(config.strategy.stop_loss_pct, 0.0)
        take_profit_pct = max(config.strategy.take_profit_pct, 0.0)
        pnl_exit_enabled = config.strategy.pnl_exit_enabled
        fallback_stoploss_bps = max(float(config.strategy.fallback_stoploss_bps), 0.0)
        fallback_breakeven_bps = max(float(config.strategy.fallback_breakeven_bps), 0.0)
        fallback_trailing_bps = max(float(config.strategy.fallback_trailing_bps), 0.0)
        fallback_trailing_activation_bps = max(float(config.strategy.fallback_trailing_activation_bps), 0.0)
        log.info(
            "Execution refresh tuning: interval=%.1fs max_symbols=%s concurrency=%s dust_cooldown=%.0fs fast_reprice=%s quote_max_age_ms=%s min_active_usdt=%.4f spot_notional_floor=%s",
            execution_refresh_interval_sec,
            execution_refresh_max_symbols,
            execution_refresh_concurrency,
            force_exit_dust_cooldown_sec,
            1 if fast_reprice_on_send else 0,
            quote_max_book_age_ms,
            min_active_position_usdt,
            1 if spot_notional_floor_enabled else 0,
        )

        net_position_base: dict[str, float] = {s: 0.0 for s in config.symbols}
        avg_entry_price: dict[str, float] = {s: 0.0 for s in config.symbols}
        position_signal_id: dict[str, str | None] = {s: None for s in config.symbols}
        position_opened_wall_ms: dict[str, int | None] = {s: None for s in config.symbols}
        position_opened_at: dict[str, float | None] = {s: None for s in config.symbols}
        last_force_exit_ts: dict[str, float] = {s: 0.0 for s in config.symbols}
        symbol_hold_timeout_sec: dict[str, float] = {s: float(hold_timeout_sec) for s in config.symbols}
        symbol_stop_loss_pct: dict[str, float] = {s: float(stop_loss_pct) for s in config.symbols}
        symbol_take_profit_pct: dict[str, float] = {s: float(take_profit_pct) for s in config.symbols}
        symbol_target_profit_ratio: dict[str, float] = {s: float(max(config.strategy.target_profit, 0.0)) for s in config.symbols}
        symbol_safety_buffer_ratio: dict[str, float] = {s: float(max(config.strategy.safety_buffer, 0.0)) for s in config.symbols}
        symbol_peak_pnl_bps: dict[str, float] = {s: 0.0 for s in config.symbols}
        symbol_position_floor: dict[str, float] = {s: float(min_position_qty) for s in config.symbols}
        symbol_position_notional_floor: dict[str, float] = {s: float(min_active_position_usdt) for s in config.symbols}
        dust_exit_suppressed_until: dict[str, float] = {s: 0.0 for s in config.symbols}
        seen_exec_ids: set[str] = set()
        last_executions_sync_ts = 0.0
        last_position_status_log_at = 0.0
        last_reconciliation_run_ts = 0.0
        last_protection_apply_ts: dict[str, float] = {s: 0.0 for s in config.symbols}
        # Spot wallet holdings: base coins (e.g. "BTC", "ETH") with non-dust balance.
        # Refreshed periodically from the exchange wallet-balance API.
        # This is the ground-truth for spot: a filled buy has NO open order,
        # it simply lives in the wallet until we sell it.
        wallet_held_base_symbols: set[str] = set()
        last_wallet_balance_check_at: float = 0.0

        reconciliation_service: ExchangeReconciliationService | None = None
        if executor is not None and reconciliation_enabled:
            if executor_supports_capability(
                executor,
                "reconciliation",
                market_category=runtime_market_category,
            ):
                def _reconciliation_symbols() -> list[str]:
                    merged: set[str] = set(state.get_active_symbols() or [])
                    merged.update(config.symbols)
                    merged.update(
                        symbol
                        for symbol, qty in net_position_base.items()
                        if abs(float(qty)) >= _position_floor(symbol)
                    )
                    return sorted(s for s in merged if str(s).strip())

                reconciliation_service = ExchangeReconciliationService(
                    conn=conn,
                    executor=executor,
                    market_category=runtime_market_category,
                    account_type="UNIFIED",
                    managed_symbols=_reconciliation_symbols,
                    symbols_limit=reconciliation_symbols_limit,
                    service_name=str(strategy.__class__.__name__),
                )
                log.info(
                    "Reconciliation enabled: interval=%ss symbols_limit=%s",
                    int(reconciliation_interval_sec),
                    reconciliation_symbols_limit,
                )
            else:
                log.warning(
                    "Reconciliation is enabled in config but unsupported by executor=%s; "
                    "runtime reconciliation loop is disabled for safety.",
                    executor.__class__.__name__,
                )
                insert_event_audit(
                    conn,
                    event_type="reconciliation_unsupported",
                    domain="shared",
                    payload={
                        "executor": executor.__class__.__name__,
                        "market_category": runtime_market_category,
                        "action": "disabled_runtime_reconciliation",
                    },
                )

        async def _resolve_position_floor(symbol: str) -> float:
            symbol_u = str(symbol or "").upper().strip()
            if not symbol_u:
                return float(min_position_qty)
            cached = symbol_position_floor.get(symbol_u)
            if cached is not None:
                return float(cached)

            floor = float(min_position_qty)
            getter = getattr(executor, "get_symbol_min_qty", None)
            if callable(getter):
                try:
                    exchange_min = await getter(symbol_u)
                    if exchange_min and float(exchange_min) > 0:
                        floor = max(floor, float(exchange_min))
                except Exception as exc:
                    log.debug("get_symbol_min_qty failed for %s: %s", symbol_u, exc)
            symbol_position_floor[symbol_u] = float(floor)
            return float(floor)

        def _position_floor(symbol: str) -> float:
            symbol_u = str(symbol or "").upper().strip()
            return float(symbol_position_floor.get(symbol_u, float(min_position_qty)))

        async def _resolve_position_notional_floor(symbol: str) -> float:
            symbol_u = str(symbol or "").upper().strip()
            if not symbol_u:
                return float(min_active_position_usdt)
            cached = symbol_position_notional_floor.get(symbol_u)
            if cached is not None:
                return float(cached)

            floor = float(min_active_position_usdt)
            if spot_notional_floor_enabled:
                getter = getattr(executor, "get_symbol_min_notional_quote", None)
                if callable(getter):
                    try:
                        exchange_min = await getter(symbol_u)
                        if exchange_min and float(exchange_min) > 0:
                            floor = max(floor, float(exchange_min))
                    except Exception as exc:
                        log.debug("get_symbol_min_notional_quote failed for %s: %s", symbol_u, exc)
            symbol_position_notional_floor[symbol_u] = float(floor)
            return float(floor)

        def _position_notional_floor(symbol: str) -> float:
            symbol_u = str(symbol or "").upper().strip()
            return float(symbol_position_notional_floor.get(symbol_u, float(min_active_position_usdt)))

        def _blocking_futures_protection_status(symbol: str) -> str | None:
            if runtime_market_category != "linear":
                return None
            return get_futures_blocking_protection_status(
                conn,
                symbol=str(symbol or "").upper(),
                account_type="UNIFIED",
            )

        def _spot_sell_blocked_by_hold_policy(symbol: str, side: str) -> tuple[bool, str]:
            if runtime_market_category != "spot":
                return False, ""
            if str(side or "").strip().lower() != "sell":
                return False, ""
            row = conn.execute(
                """
                SELECT hold_reason, auto_sell_allowed, COALESCE(free_qty, 0), COALESCE(locked_qty, 0)
                FROM spot_holdings
                WHERE account_type=? AND symbol=?
                LIMIT 1
                """,
                ("UNIFIED", str(symbol or "").upper()),
            ).fetchone()
            if not row:
                return False, ""
            hold_reason = str(row[0] or "")
            auto_sell_allowed = bool(int(row[1] or 0))
            qty = float(row[2] or 0.0) + float(row[3] or 0.0)
            if qty <= 0:
                return False, ""
            if can_auto_sell_hold(hold_reason=hold_reason, auto_sell_allowed=auto_sell_allowed):
                return False, ""
            return True, hold_reason

        def _record_futures_decision(
            *,
            symbol: str,
            side: str,
            decision_type: str,
            reason: str,
            payload: dict[str, Any] | None = None,
            applied: bool = False,
        ) -> None:
            if runtime_market_category != "linear":
                return
            try:
                insert_futures_position_decision(
                    conn,
                    account_type="UNIFIED",
                    symbol=str(symbol or "").upper(),
                    side=side,
                    position_idx=0,
                    decision_type=decision_type,
                    reason=reason,
                    policy_name="runtime",
                    payload=payload or {},
                    applied=applied,
                )
            except Exception as exc:
                log.debug("record_futures_decision failed for %s: %s", symbol, exc)

        async def _ensure_futures_protection(
            *,
            symbol: str,
            position_qty: float,
            entry_price: float,
        ) -> None:
            if runtime_market_category != "linear" or executor is None:
                return
            if abs(position_qty) < max(_position_floor(symbol), 1e-12):
                return
            if entry_price <= 0:
                return
            now_mono = time.monotonic()
            if (now_mono - float(last_protection_apply_ts.get(symbol, 0.0))) < 8.0:
                return
            last_protection_apply_ts[symbol] = now_mono

            side = "Buy" if position_qty > 0 else "Sell"
            symbol_u = str(symbol).upper()
            current_status_row = conn.execute(
                """
                SELECT LOWER(COALESCE(protection_status, ''))
                FROM futures_positions
                WHERE account_type=?
                  AND symbol=?
                  AND side=?
                  AND position_idx=0
                  AND ABS(COALESCE(qty, 0)) > 0
                ORDER BY updated_at_utc DESC
                LIMIT 1
                """,
                ("UNIFIED", symbol_u, side),
            ).fetchone()
            current_status = normalize_protection_status(current_status_row[0] if current_status_row else "pending")
            sl_pct = float(symbol_stop_loss_pct.get(symbol, stop_loss_pct))
            tp_pct = float(symbol_take_profit_pct.get(symbol, take_profit_pct))
            plan = build_futures_protection_plan(
                entry_price=float(entry_price),
                position_qty=float(position_qty),
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
            )
            if plan is None:
                failed_status = transition_protection_status(
                    current_status=current_status,
                    apply_attempted=True,
                    apply_success=False,
                    verify_status="failed",
                )
                upsert_futures_position(
                    conn,
                    account_type="UNIFIED",
                    symbol=symbol_u,
                    side=side,
                    position_idx=0,
                    margin_mode="",
                    leverage=None,
                    qty=float(abs(position_qty)),
                    entry_price=float(entry_price),
                    mark_price=None,
                    liq_price=None,
                    unrealized_pnl=None,
                    realized_pnl=None,
                    take_profit=None,
                    stop_loss=None,
                    trailing_stop=None,
                    protection_status=failed_status,
                    strategy_owner=strategy.__class__.__name__,
                    source_of_truth="runtime",
                    recovered_from_exchange=False,
                )
                upsert_futures_protection(
                    conn,
                    account_type="UNIFIED",
                    symbol=symbol_u,
                    side=side,
                    position_idx=0,
                    status=failed_status,
                    source_of_truth="runtime",
                    stop_loss=None,
                    take_profit=None,
                    trailing_stop=None,
                    details={
                        "reason": "invalid_protection_params",
                        "stop_loss_pct": sl_pct,
                        "take_profit_pct": tp_pct,
                    },
                )
                _record_futures_decision(
                    symbol=symbol,
                    side=side,
                    decision_type="protection_plan_failed",
                    reason="invalid_protection_params",
                    payload={"stop_loss_pct": sl_pct, "take_profit_pct": tp_pct},
                    applied=False,
                )
                insert_event_audit(
                    conn,
                    event_type="protection_failure",
                    domain="futures",
                    symbol=symbol_u,
                    payload={
                        "reason": "invalid_protection_params",
                        "stop_loss_pct": sl_pct,
                        "take_profit_pct": tp_pct,
                    },
                )
                return

            protection_apply_phase = (
                "repairing"
                if current_status in {"repairing", "unprotected", "failed"}
                else "pending"
            )
            upsert_futures_position(
                conn,
                account_type="UNIFIED",
                symbol=symbol_u,
                side=side,
                position_idx=0,
                margin_mode="",
                leverage=None,
                qty=float(abs(position_qty)),
                entry_price=float(entry_price),
                mark_price=None,
                liq_price=None,
                unrealized_pnl=None,
                realized_pnl=None,
                take_profit=plan.take_profit,
                stop_loss=plan.stop_loss,
                trailing_stop=plan.trailing_stop,
                protection_status=protection_apply_phase,
                strategy_owner=strategy.__class__.__name__,
                source_of_truth="runtime",
                recovered_from_exchange=False,
            )
            upsert_futures_protection(
                conn,
                account_type="UNIFIED",
                symbol=symbol_u,
                side=side,
                position_idx=0,
                status=protection_apply_phase,
                source_of_truth="runtime",
                stop_loss=plan.stop_loss,
                take_profit=plan.take_profit,
                trailing_stop=plan.trailing_stop,
                details={
                    "phase": protection_apply_phase,
                    "stop_loss_pct": sl_pct,
                    "take_profit_pct": tp_pct,
                },
            )

            set_stop = getattr(executor, "set_trading_stop", None)
            _PROTECTION_MAX_RETRIES = 3
            apply_attempted = False
            apply_success = False
            verify_status: str | None = None
            verify_payload: dict[str, Any] = {}
            set_stop_resp: dict[str, Any] = {}

            if not executor_supports_capability(executor, "protection", market_category=runtime_market_category):
                apply_attempted = True
                apply_success = False
                verify_status = "failed"
                verify_payload = {"verify_reason": "protection_api_unsupported"}
                log.warning(
                    "Protection apply unsupported: symbol=%s executor=%s",
                    symbol_u,
                    executor.__class__.__name__,
                )
            elif callable(set_stop):
                apply_attempted = True
                for _retry_idx in range(_PROTECTION_MAX_RETRIES):
                    try:
                        resp = await set_stop(
                            symbol=symbol_u,
                            position_idx=0,
                            stop_loss=plan.stop_loss,
                            take_profit=plan.take_profit,
                            trailing_stop=plan.trailing_stop,
                        )
                        set_stop_resp = dict(resp or {})
                        if set_stop_resp.get("retCode") == 0:
                            apply_success = True
                            break
                        log.warning(
                            "set_trading_stop attempt %d/%d failed: symbol=%s retCode=%s retMsg=%s",
                            _retry_idx + 1,
                            _PROTECTION_MAX_RETRIES,
                            symbol,
                            set_stop_resp.get("retCode"),
                            set_stop_resp.get("retMsg"),
                        )
                    except Exception as exc:
                        set_stop_resp = {"retCode": -1, "retMsg": str(exc)}
                        log.warning(
                            "set_trading_stop attempt %d/%d error for %s: %s",
                            _retry_idx + 1,
                            _PROTECTION_MAX_RETRIES,
                            symbol,
                            exc,
                        )
                    if _retry_idx < _PROTECTION_MAX_RETRIES - 1:
                        await asyncio.sleep(0.5 * (_retry_idx + 1))
            else:
                apply_attempted = True
                apply_success = False
                verify_status = "failed"
                verify_payload = {"verify_reason": "set_trading_stop_not_callable"}

            if apply_success:
                verify_status, verify_payload = await verify_futures_protection_from_exchange(
                    executor,
                    symbol=symbol_u,
                    side=side,
                    position_idx=0,
                )
            final_status = transition_protection_status(
                current_status=protection_apply_phase,
                apply_attempted=apply_attempted,
                apply_success=apply_success,
                verify_status=verify_status,
            )

            if final_status != "protected":
                if verify_status is None:
                    verify_status = "failed"
                    verify_payload = {
                        "verify_reason": "set_trading_stop_failed",
                        "retCode": set_stop_resp.get("retCode"),
                        "retMsg": set_stop_resp.get("retMsg"),
                    }
                if apply_attempted and apply_success and normalize_protection_status(verify_status) == "unprotected":
                    log.error(
                        "Protection verify failed after trading-stop apply: symbol=%s verify=%s",
                        symbol_u,
                        verify_payload,
                    )
                elif apply_attempted and not apply_success:
                    verify_reason = str(verify_payload.get("verify_reason") or "")
                    if verify_reason in {"protection_api_unsupported", "set_trading_stop_not_callable"}:
                        log.error(
                            "Protection unsupported for %s; position remains %s and new entries will be blocked.",
                            symbol_u,
                            final_status,
                        )
                    else:
                        log.error(
                            "CRITICAL: All %d set_trading_stop retries failed for %s. "
                            "Market-closing position to prevent unprotected exposure.",
                            _PROTECTION_MAX_RETRIES,
                            symbol,
                        )
                        close_side = "Sell" if position_qty > 0 else "Buy"
                        try:
                            close_resp = await executor.place_order(
                                symbol=symbol_u,
                                side=close_side,
                                qty=_fmt_float(abs(position_qty)),
                                price="0",
                                order_link_id=f"prot-fail-{symbol}-{uuid.uuid4().hex[:8]}",
                                time_in_force="GTC",
                                order_type="Market",
                            )
                            if close_resp.get("retCode") == 0:
                                log.warning(
                                    "Emergency market-close sent for %s (protection failure fallback).",
                                    symbol,
                                )
                                _reset_symbol_runtime_state(symbol)
                            else:
                                log.error(
                                    "Emergency market-close ALSO failed for %s: retCode=%s retMsg=%s",
                                    symbol,
                                    close_resp.get("retCode"),
                                    close_resp.get("retMsg"),
                                )
                        except Exception as close_exc:
                            log.error(
                                "Emergency market-close exception for %s: %s",
                                symbol,
                                close_exc,
                            )

            upsert_futures_position(
                conn,
                account_type="UNIFIED",
                symbol=symbol_u,
                side=side,
                position_idx=0,
                margin_mode="",
                leverage=None,
                qty=float(abs(position_qty)),
                entry_price=float(entry_price),
                mark_price=None,
                liq_price=None,
                unrealized_pnl=None,
                realized_pnl=None,
                take_profit=plan.take_profit,
                stop_loss=plan.stop_loss,
                trailing_stop=plan.trailing_stop,
                protection_status=final_status,
                strategy_owner=strategy.__class__.__name__,
                source_of_truth="runtime",
                recovered_from_exchange=False,
            )
            upsert_futures_protection(
                conn,
                account_type="UNIFIED",
                symbol=symbol_u,
                side=side,
                position_idx=0,
                status=final_status,
                source_of_truth="runtime",
                stop_loss=plan.stop_loss,
                take_profit=plan.take_profit,
                trailing_stop=plan.trailing_stop,
                details={
                    "stop_loss_pct": sl_pct,
                    "take_profit_pct": tp_pct,
                    "verify_status": verify_status,
                    "verify_payload": verify_payload,
                    "apply_attempted": apply_attempted,
                    "apply_success": apply_success,
                },
            )
            _record_futures_decision(
                symbol=symbol,
                side=side,
                decision_type=(
                    "protection_confirmed"
                    if final_status == "protected"
                    else (
                        "protection_repair_failed"
                        if protection_apply_phase == "repairing"
                        else "protection_apply_failed"
                    )
                ),
                reason=("verify_confirmed" if final_status == "protected" else str(verify_status or "failed")),
                payload={
                    "stop_loss": plan.stop_loss,
                    "take_profit": plan.take_profit,
                    "status": final_status,
                    "verify_status": verify_status,
                    "verify_payload": verify_payload,
                },
                applied=(final_status == "protected"),
            )
            if final_status == "protected":
                insert_event_audit(
                    conn,
                    event_type="protection_plan_created",
                    domain="futures",
                    symbol=symbol_u,
                    payload={"status": final_status, "verify": verify_status},
                )
            else:
                insert_event_audit(
                    conn,
                    event_type="protection_failure",
                    domain="futures",
                    symbol=symbol_u,
                    payload={
                        "status": final_status,
                        "verify_status": verify_status,
                        "verify_payload": verify_payload,
                    },
                )

        def _reset_symbol_runtime_state(symbol: str) -> None:
            net_position_base[symbol] = 0.0
            avg_entry_price[symbol] = 0.0
            position_opened_at[symbol] = None
            position_opened_wall_ms[symbol] = None
            position_signal_id[symbol] = None
            symbol_hold_timeout_sec[symbol] = float(hold_timeout_sec)
            symbol_stop_loss_pct[symbol] = float(stop_loss_pct)
            symbol_take_profit_pct[symbol] = float(take_profit_pct)
            symbol_target_profit_ratio[symbol] = float(max(config.strategy.target_profit, 0.0))
            symbol_safety_buffer_ratio[symbol] = float(max(config.strategy.safety_buffer, 0.0))
            symbol_peak_pnl_bps[symbol] = 0.0

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

        def _sync_signal_outcome_from_executions(
            conn_db: sqlite3.Connection,
            signal_id: str | None,
            symbol_hint: str | None = None,
        ) -> None:
            if not signal_id:
                return

            rows = conn_db.execute(
                """
                SELECT symbol, lower(COALESCE(side, '')), COALESCE(exec_price, 0.0), COALESCE(exec_qty, 0.0),
                       COALESCE(exec_fee, 0.0), COALESCE(fee_currency, ''), COALESCE(exec_time_ms, 0)
                FROM executions_raw
                WHERE signal_id = ?
                ORDER BY exec_time_ms ASC
                """,
                (signal_id,),
            ).fetchall()
            if not rows:
                return

            symbol = str(rows[0][0] or symbol_hint or "").upper().strip()
            if not symbol:
                return

            buy_qty = 0.0
            buy_notional = 0.0
            sell_qty = 0.0
            sell_notional = 0.0
            total_fees_quote = 0.0
            first_buy_ms: int | None = None
            last_sell_ms: int | None = None

            for row in rows:
                row_symbol = str(row[0] or "").upper().strip()
                if row_symbol:
                    symbol = row_symbol
                side = str(row[1] or "").lower()
                exec_price = float(row[2] or 0.0)
                exec_qty = float(row[3] or 0.0)
                exec_fee = float(row[4] or 0.0)
                fee_currency = str(row[5] or "")
                exec_time_ms = int(row[6] or 0)
                if exec_price <= 0 or exec_qty <= 0:
                    continue

                if side == "buy":
                    buy_qty += exec_qty
                    buy_notional += exec_price * exec_qty
                    if first_buy_ms is None or (exec_time_ms > 0 and exec_time_ms < first_buy_ms):
                        first_buy_ms = exec_time_ms if exec_time_ms > 0 else first_buy_ms
                elif side == "sell":
                    sell_qty += exec_qty
                    sell_notional += exec_price * exec_qty
                    if exec_time_ms > 0 and (last_sell_ms is None or exec_time_ms > last_sell_ms):
                        last_sell_ms = exec_time_ms

                total_fees_quote += _fee_to_quote(symbol, exec_fee, fee_currency, exec_price)

            if buy_qty <= 0 or buy_notional <= 0:
                return

            entry_vwap = buy_notional / buy_qty
            exit_vwap = (sell_notional / sell_qty) if sell_qty > 0 and sell_notional > 0 else None
            update_orders_entry_exit_for_signal(
                conn_db,
                signal_id=signal_id,
                entry_price=entry_vwap,
                exit_price=exit_vwap,
                updated_at_utc=utc_now_iso(),
            )

            if exit_vwap is None:
                return

            matched_qty = min(buy_qty, sell_qty)
            if matched_qty <= 0:
                return

            hold_time_ms = 0
            if first_buy_ms and last_sell_ms and last_sell_ms >= first_buy_ms:
                hold_time_ms = int(last_sell_ms - first_buy_ms)

            gross_pnl = (exit_vwap - entry_vwap) * matched_qty
            net_pnl = gross_pnl - total_fees_quote

            # Use realized filled notional as denominator to avoid distorted edge on qty mismatches.
            denom = entry_vwap * matched_qty
            if denom <= 0:
                entry_basis_price, entry_basis_qty = _load_signal_entry_basis(conn_db, signal_id)
                if entry_basis_price > 0 and entry_basis_qty > 0:
                    denom = entry_basis_price * entry_basis_qty
            net_edge_bps = (net_pnl / denom) * 10000.0 if denom > 0 else 0.0

            upsert_outcome(
                conn_db,
                signal_id=signal_id,
                symbol=symbol,
                entry_vwap=entry_vwap,
                exit_vwap=exit_vwap,
                filled_qty=matched_qty,
                hold_time_ms=hold_time_ms,
                gross_pnl_quote=gross_pnl,
                net_pnl_quote=net_pnl,
                net_edge_bps=net_edge_bps,
                max_adverse_excursion_bps=0.0,
                max_favorable_excursion_bps=0.0,
                was_fully_filled=sell_qty >= (buy_qty - 1e-9),
                was_profitable=net_pnl > 0,
                exit_reason="signal_roundtrip",
            )
            upsert_signal_reward(
                conn_db,
                signal_id=signal_id,
                reward_net_edge_bps=net_edge_bps,
            )
            policy_selector.update_reward(signal_id=signal_id, reward_bps=net_edge_bps)

        def _maybe_refresh_policy_model(force: bool = False) -> None:
            nonlocal policy_model, policy_model_last_check_ts, policy_model_id
            if not policy_ml_enabled:
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

        def _ordered_symbols_for_execution_sync(open_order_symbols: set[str] | None = None) -> list[str]:
            selected: list[str] = []
            seen: set[str] = set()

            def _push(symbol: str) -> None:
                s = str(symbol or "").upper().strip()
                if not s or s in seen:
                    return
                seen.add(s)
                selected.append(s)

            for symbol, qty in net_position_base.items():
                if abs(qty) >= _position_floor(symbol):
                    _push(symbol)
            for symbol in open_order_symbols or set():
                _push(symbol)
            for symbol in state.get_active_symbols() or []:
                _push(symbol)
            for symbol in config.symbols:
                if len(selected) >= execution_refresh_max_symbols:
                    break
                _push(symbol)
            return selected[:execution_refresh_max_symbols]

        async def refresh_wallet_balance() -> None:
            """
            Query Bybit wallet balance and update wallet_held_base_symbols.
            On spot, a filled buy has NO open order â€” the coin just sits in the wallet.
            This is the only reliable way to know how many symbols we're holding.
            Runs at most once every 15 seconds to avoid rate-limit pressure.
            """
            nonlocal wallet_held_base_symbols, last_wallet_balance_check_at
            if executor is None:
                return
            now = time.monotonic()
            if now - last_wallet_balance_check_at < 15.0:
                return
            last_wallet_balance_check_at = now
            try:
                resp = await executor.get_wallet_balance(account_type="UNIFIED")
                if resp.get("retCode") != 0:
                    log.debug("refresh_wallet_balance: retCode=%s", resp.get("retCode"))
                    return
                accounts = (resp.get("result") or {}).get("list") or []
                held: set[str] = set()
                for account in accounts:
                    for coin_info in (account.get("coin") or []):
                        coin = str(coin_info.get("coin") or "").upper().strip()
                        if not coin or coin in ("USDT", "USDC", "BUSD"):
                            continue
                        balance = float(coin_info.get("walletBalance") or 0.0)
                        if balance > 0.0:
                            held.add(coin)
                wallet_held_base_symbols = held
                log.debug("Wallet held base coins: %s", held)
            except Exception as exc:
                log.warning("refresh_wallet_balance failed: %s", exc)

        async def refresh_positions_from_executions(
            open_order_symbols: set[str] | None = None,
            force: bool = False,
        ) -> None:
            nonlocal last_executions_sync_ts
            if executor is None:
                return
            now_mono = time.monotonic()
            if not force and (now_mono - last_executions_sync_ts) < execution_refresh_interval_sec:
                return

            symbols_to_check = _ordered_symbols_for_execution_sync(open_order_symbols=open_order_symbols)
            if not symbols_to_check:
                last_executions_sync_ts = now_mono
                return

            sem = asyncio.Semaphore(execution_refresh_concurrency)

            async def _fetch_symbol(symbol: str) -> tuple[str, dict[str, Any] | None, str | None]:
                async with sem:
                    try:
                        response = await executor.get_execution_list(symbol=symbol, limit=100)
                        return symbol, response, None
                    except Exception as exc:
                        return symbol, None, str(exc)

            fetch_results = await asyncio.gather(*[_fetch_symbol(symbol) for symbol in symbols_to_check])
            last_executions_sync_ts = time.monotonic()

            for symbol, resp, fetch_error in fetch_results:
                symbol_floor = await _resolve_position_floor(symbol)
                symbol_notional_floor = await _resolve_position_notional_floor(symbol)
                if fetch_error is not None:
                    log.warning("get_execution_list failed for %s: %s", symbol, fetch_error)
                    continue
                if not resp:
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

                    abs_new_qty = abs(new_qty)
                    new_notional_quote = abs_new_qty * float(price)
                    new_is_effective = abs_new_qty >= symbol_floor and (
                        not spot_notional_floor_enabled or symbol_notional_floor <= 0 or new_notional_quote >= symbol_notional_floor
                    )
                    if runtime_market_category == "linear" and new_is_effective:
                        await _ensure_futures_protection(
                            symbol=symbol,
                            position_qty=new_qty,
                            entry_price=(new_avg if new_avg > 0 else price),
                        )
                    if runtime_market_category == "spot":
                        base_asset, _ = _split_symbol_base_quote(symbol.upper())
                        if base_asset:
                            if new_is_effective and new_qty > 0:
                                upsert_spot_holding(
                                    conn,
                                    account_type="UNIFIED",
                                    symbol=symbol,
                                    base_asset=base_asset,
                                    free_qty=abs_new_qty,
                                    locked_qty=0.0,
                                    avg_entry_price=(new_avg if new_avg > 0 else price),
                                    hold_reason="strategy_entry",
                                    source_of_truth="runtime_fills",
                                    recovered_from_exchange=False,
                                    strategy_owner=strategy.__class__.__name__,
                                    auto_sell_allowed=True,
                                )
                            elif not new_is_effective:
                                upsert_spot_holding(
                                    conn,
                                    account_type="UNIFIED",
                                    symbol=symbol,
                                    base_asset=base_asset,
                                    free_qty=0.0,
                                    locked_qty=0.0,
                                    avg_entry_price=None,
                                    hold_reason="strategy_entry",
                                    source_of_truth="runtime_fills",
                                    recovered_from_exchange=False,
                                    strategy_owner=strategy.__class__.__name__,
                                    auto_sell_allowed=True,
                                )

                    if abs(old_qty) < symbol_floor and new_is_effective:
                        position_opened_at[symbol] = time.monotonic()
                        position_opened_wall_ms[symbol] = exec_time_ms
                        position_signal_id[symbol] = signal_id
                        symbol_peak_pnl_bps[symbol] = 0.0
                    elif not new_is_effective:
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
                        denom = entry_vwap * qty_closed
                        if denom <= 0 and outcome_signal_id:
                            entry_basis_price, entry_basis_qty = _load_signal_entry_basis(conn, outcome_signal_id)
                            if entry_basis_price > 0 and entry_basis_qty > 0:
                                denom = entry_basis_price * entry_basis_qty
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
                            update_orders_entry_exit_for_signal(
                                conn,
                                signal_id=outcome_signal_id,
                                entry_price=entry_vwap,
                                exit_price=exit_vwap,
                                updated_at_utc=utc_now_iso(),
                            )
                            policy_selector.update_reward(signal_id=outcome_signal_id, reward_bps=net_edge_bps)
                        if runtime_market_category == "linear":
                            closed_side = "Buy" if old_qty > 0 else "Sell"
                            upsert_futures_position(
                                conn,
                                account_type="UNIFIED",
                                symbol=str(symbol).upper(),
                                side=closed_side,
                                position_idx=0,
                                margin_mode="",
                                leverage=None,
                                qty=0.0,
                                entry_price=(entry_vwap if entry_vwap > 0 else None),
                                mark_price=float(price),
                                liq_price=None,
                                unrealized_pnl=0.0,
                                realized_pnl=None,
                                take_profit=None,
                                stop_loss=None,
                                trailing_stop=None,
                                protection_status="closed",
                                strategy_owner=strategy.__class__.__name__,
                                source_of_truth="runtime_fills",
                                recovered_from_exchange=False,
                            )
                            upsert_futures_protection(
                                conn,
                                account_type="UNIFIED",
                                symbol=str(symbol).upper(),
                                side=closed_side,
                                position_idx=0,
                                status="closed",
                                source_of_truth="runtime_fills",
                                stop_loss=None,
                                take_profit=None,
                                trailing_stop=None,
                                details={
                                    "reason": "position_flat",
                                    "signal_id": outcome_signal_id,
                                },
                            )
                            _record_futures_decision(
                                symbol=symbol,
                                side=closed_side,
                                decision_type="position_closed",
                                reason="position_flat",
                                payload={
                                    "signal_id": outcome_signal_id,
                                    "net_pnl_quote": net_pnl,
                                },
                                applied=True,
                            )
                        position_opened_at[symbol] = None
                        position_opened_wall_ms[symbol] = None
                        position_signal_id[symbol] = None
                        _reset_symbol_runtime_state(symbol)

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

                    write_runtime_fill_legacy_and_domain(
                        conn,
                        market_category=runtime_market_category,
                        symbol=symbol,
                        side="Buy" if side == "buy" else "Sell",
                        exec_id=exec_id,
                        price=float(price),
                        qty=float(qty),
                        filled_at_utc=utc_now_iso(),
                        log=log,
                        order_link_id=(str(order_link_id) if order_link_id else None),
                        exchange_order_id=(str(item.get("orderId")) if item.get("orderId") else None),
                        fee=float(item.get("execFee") or 0.0),
                        fee_currency=(str(item.get("feeCurrency") or "") or None),
                        is_maker=(str(item.get("isMaker") or "").lower() == "true"),
                        exec_time_ms=exec_time_ms,
                    )

                    if order_link_id:
                        update_order_status(
                            conn,
                            order_link_id=str(order_link_id),
                            status="Filled",
                            updated_at_utc=utc_now_iso(),
                            exchange_order_id=item.get("orderId"),
                        )
                    _sync_signal_outcome_from_executions(conn, signal_id, symbol_hint=symbol)

        async def maybe_force_exit(symbol: str) -> bool:
            if executor is None:
                return False
            if time.monotonic() < dust_exit_suppressed_until.get(symbol, 0.0):
                return False
            pos_qty = net_position_base.get(symbol, 0.0)
            pos_floor = await _resolve_position_floor(symbol)
            if abs(pos_qty) < pos_floor:
                return False

            notional_floor = await _resolve_position_notional_floor(symbol)
            if spot_notional_floor_enabled and notional_floor > 0:
                entry_ref_price = max(float(avg_entry_price.get(symbol, 0.0)), 0.0)
                if entry_ref_price > 0 and (abs(pos_qty) * entry_ref_price) < notional_floor:
                    dust_exit_suppressed_until[symbol] = time.monotonic() + force_exit_dust_cooldown_sec
                    _reset_symbol_runtime_state(symbol)
                    log.info(
                        "Position treated as dust (entry notional floor): symbol=%s qty=%.12f entry=%.10f notional=%.8f floor=%.8f",
                        symbol,
                        abs(pos_qty),
                        entry_ref_price,
                        abs(pos_qty) * entry_ref_price,
                        notional_floor,
                    )
                    return False

            opened_at = position_opened_at.get(symbol)
            if opened_at is None:
                # First time seeing this position in this session.
                # If entry price is unknown (wallet-recovered without a DB fill record),
                # treat it as already timed-out â†’ triggers immediate force-exit below.
                # Otherwise start the clock now and fall through to SL/TP/timeout checks.
                if avg_entry_price.get(symbol, 0.0) <= 0:
                    position_opened_at[symbol] = time.monotonic() - float(hold_timeout_sec) - 1.0
                    log.warning(
                        "Position with unknown entry â€” forcing immediate timeout exit: "
                        "symbol=%s qty=%.8f", symbol, pos_qty,
                    )
                else:
                    position_opened_at[symbol] = time.monotonic()
                opened_at = position_opened_at[symbol]
                # Do NOT return â€” fall through to SL/TP/timeout logic.

            ob = state.get_orderbook(symbol)
            if ob is None:
                return True

            mark_price = ob.best_bid if pos_qty > 0 else ob.best_ask
            if spot_notional_floor_enabled and notional_floor > 0 and (abs(pos_qty) * float(mark_price)) < notional_floor:
                dust_exit_suppressed_until[symbol] = time.monotonic() + force_exit_dust_cooldown_sec
                _reset_symbol_runtime_state(symbol)
                log.info(
                    "Position treated as dust (mark notional floor): symbol=%s qty=%.12f mark=%.10f notional=%.8f floor=%.8f",
                    symbol,
                    abs(pos_qty),
                    float(mark_price),
                    abs(pos_qty) * float(mark_price),
                    notional_floor,
                )
                return False

            pnl_pct = unrealized_pnl_pct(
                position_qty=pos_qty,
                avg_entry_price=avg_entry_price.get(symbol, 0.0),
                mark_price=mark_price,
            )
            age = time.monotonic() - opened_at
            local_stop_loss = max(float(symbol_stop_loss_pct.get(symbol, stop_loss_pct)), 0.0)
            local_take_profit = max(float(symbol_take_profit_pct.get(symbol, take_profit_pct)), 0.0)
            local_hold_timeout = max(float(symbol_hold_timeout_sec.get(symbol, hold_timeout_sec)), 1.0)
            reason, updated_peak = decide_exit_reason(
                pnl_pct=pnl_pct,
                age_sec=age,
                hold_timeout_sec=local_hold_timeout,
                pnl_exit_enabled=bool(pnl_exit_enabled),
                stop_loss_pct=local_stop_loss,
                take_profit_pct=local_take_profit,
                fallback_stoploss_bps=fallback_stoploss_bps,
                fallback_breakeven_bps=fallback_breakeven_bps,
                fallback_trailing_bps=fallback_trailing_bps,
                fallback_trailing_activation_bps=fallback_trailing_activation_bps,
                peak_pnl_bps=float(symbol_peak_pnl_bps.get(symbol, 0.0)),
            )
            symbol_peak_pnl_bps[symbol] = updated_peak
            futures_risk_view: dict[str, Any] = {}
            if runtime_market_category == "linear":
                futures_risk_view = evaluate_futures_symbol_risk(
                    conn,
                    symbol=symbol,
                    account_type="UNIFIED",
                    fallback_mark_price=float(mark_price),
                )
                futures_risk_state = str(futures_risk_view.get("risk_state") or "").strip().lower()
                if futures_risk_state and futures_risk_state != "unknown":
                    _record_futures_decision(
                        symbol=symbol,
                        side=("Sell" if pos_qty > 0 else "Buy"),
                        decision_type="risk_state_observed",
                        reason=futures_risk_state,
                        payload=futures_risk_view,
                        applied=False,
                    )
                reason = futures_force_exit_reason_from_risk_state(
                    current_reason=reason,
                    risk_state=futures_risk_state,
                )

            # Symbol has an open position: block opening additional inventory.
            if reason is None:
                return True

            insert_event_audit(
                conn,
                event_type="forced_exit_decision",
                domain=("futures" if runtime_market_category == "linear" else "spot"),
                symbol=symbol,
                ref_id=position_signal_id.get(symbol),
                payload={
                    "reason": reason,
                    "pnl_pct": pnl_pct,
                    "age_sec": age,
                    "qty": pos_qty,
                    "futures_risk_state": futures_risk_view.get("risk_state") if futures_risk_view else None,
                    "distance_to_liq_bps": (
                        futures_risk_view.get("distance_to_liq_bps") if futures_risk_view else None
                    ),
                },
            )
            if runtime_market_category == "spot":
                write_spot_exit_decision_safe(
                    conn,
                    symbol=symbol,
                    decision_type="forced_exit_decision",
                    reason=str(reason),
                    pnl_pct=(float(pnl_pct) if pnl_pct is not None else None),
                    payload={
                        "age_sec": age,
                        "qty": pos_qty,
                        "entry_price": float(avg_entry_price.get(symbol, 0.0)),
                        "mark_price": float(mark_price),
                    },
                    applied=False,
                    log=log,
                )
            else:
                _record_futures_decision(
                    symbol=symbol,
                    side=("Sell" if pos_qty > 0 else "Buy"),
                    decision_type="forced_exit_decision",
                    reason=str(reason),
                    payload={
                        "pnl_pct": pnl_pct,
                        "age_sec": age,
                        "qty": pos_qty,
                    },
                    applied=False,
                )

            if not force_exit_enabled:
                log.warning(
                    "Exit rule triggered but force_exit_enabled=false: symbol=%s reason=%s qty=%s pnl_pct=%s age=%.1fs",
                    symbol,
                    reason,
                    pos_qty,
                    f"{pnl_pct:.6f}" if pnl_pct is not None else "n/a",
                    age,
                )
                if runtime_market_category == "spot":
                    write_spot_exit_decision_safe(
                        conn,
                        symbol=symbol,
                        decision_type="forced_exit_skipped",
                        reason="force_exit_disabled",
                        pnl_pct=(float(pnl_pct) if pnl_pct is not None else None),
                        payload={"trigger_reason": str(reason)},
                        applied=False,
                        log=log,
                    )
                return True

            if time.monotonic() - last_force_exit_ts.get(symbol, 0.0) < force_exit_cooldown_sec:
                return True

            side = "Sell" if pos_qty > 0 else "Buy"
            exit_price = ob.best_bid if side == "Sell" else ob.best_ask
            qty_str = _fmt_float(abs(pos_qty))
            price_str = _fmt_float(exit_price)
            order_link_id = f"force-exit-{symbol}-{uuid.uuid4().hex[:10]}"
            exit_tif = force_exit_tif if allow_taker_exit else "PostOnly"

            # Use Market order for emergency exits (stop-loss/timeout) â€” guaranteed fill on spot
            # Limit+IOC at stale book price may silently cancel if market moved
            use_market = force_exit_use_market and reason in ("stop_loss", "fallback_stoploss", "hold_timeout")
            exit_order_type = "Market" if use_market else "Limit"

            ret = await executor.place_order(
                symbol=symbol,
                side=side,
                qty=qty_str,
                price=price_str,
                order_link_id=order_link_id,
                time_in_force=exit_tif,
                order_type=exit_order_type,
            )
            last_force_exit_ts[symbol] = time.monotonic()

            if ret.get("retCode") != 0:
                if ret.get("retCode") == -2 and str(ret.get("retMsg") or "") == "invalid_qty_after_normalization":
                    dust_exit_suppressed_until[symbol] = time.monotonic() + force_exit_dust_cooldown_sec
                    _reset_symbol_runtime_state(symbol)
                    log.warning(
                        "Force-exit skipped as dust: symbol=%s side=%s qty=%s cooldown=%.0fs",
                        symbol,
                        side,
                        qty_str,
                        force_exit_dust_cooldown_sec,
                    )
                    return False
                log.warning(
                    "Force-exit failed: symbol=%s side=%s qty=%s order_type=%s retCode=%s retMsg=%s",
                    symbol,
                    side,
                    qty_str,
                    exit_order_type,
                    ret.get("retCode"),
                    ret.get("retMsg"),
                )
                insert_event_audit(
                    conn,
                    event_type="forced_exit_submission_failed",
                    domain=("futures" if runtime_market_category == "linear" else "spot"),
                    symbol=symbol,
                    ref_id=order_link_id,
                    payload={
                        "reason": reason,
                        "retCode": ret.get("retCode"),
                        "retMsg": ret.get("retMsg"),
                    },
                )
                if runtime_market_category == "spot":
                    write_spot_exit_decision_safe(
                        conn,
                        symbol=symbol,
                        decision_type="forced_exit_submission_failed",
                        reason=str(reason),
                        pnl_pct=(float(pnl_pct) if pnl_pct is not None else None),
                        payload={
                            "retCode": ret.get("retCode"),
                            "retMsg": ret.get("retMsg"),
                            "order_link_id": order_link_id,
                        },
                        applied=False,
                        log=log,
                    )
                else:
                    _record_futures_decision(
                        symbol=symbol,
                        side=side,
                        decision_type="forced_exit_submission_failed",
                        reason=str(reason),
                        payload={
                            "retCode": ret.get("retCode"),
                            "retMsg": ret.get("retMsg"),
                            "order_link_id": order_link_id,
                        },
                        applied=False,
                    )
                return True

            risk_manager.register_order_placed()
            write_runtime_order_legacy_and_domain(
                conn,
                market_category=runtime_market_category,
                symbol=symbol,
                side=side,
                order_link_id=order_link_id,
                price=float(price_str),
                qty=float(qty_str),
                status="New",
                created_at_utc=utc_now_iso(),
                log=log,
                exchange_order_id=(ret.get("result") or {}).get("orderId"),
                order_type=exit_order_type,
                time_in_force=exit_tif,
                strategy_owner=strategy.__class__.__name__,
            )
            set_order_signal_map(conn, order_link_id, position_signal_id.get(symbol))
            insert_order_event(
                conn,
                symbol=symbol,
                order_link_id=order_link_id,
                order_id=(ret.get("result") or {}).get("orderId"),
                signal_id=position_signal_id.get(symbol),
                side=side,
                order_type=exit_order_type,
                time_in_force=force_exit_tif,
                price=float(price_str),
                qty=float(qty_str),
                order_status="New",
            )
            log.warning(
                "Force-exit submitted: symbol=%s side=%s qty=%s price=%s tif=%s order_type=%s reason=%s pnl_pct=%s age=%.1fs",
                symbol,
                side,
                qty_str,
                price_str,
                exit_tif,
                exit_order_type,
                reason,
                f"{pnl_pct:.6f}" if pnl_pct is not None else "n/a",
                age,
            )
            insert_event_audit(
                conn,
                event_type="forced_exit_submitted",
                domain=("futures" if runtime_market_category == "linear" else "spot"),
                symbol=symbol,
                ref_id=order_link_id,
                    payload={"reason": reason, "side": side, "qty": qty_str, "price": price_str},
            )
            if runtime_market_category == "spot":
                write_spot_exit_decision_safe(
                    conn,
                    symbol=symbol,
                    decision_type="forced_exit_submitted",
                    reason=str(reason),
                    pnl_pct=(float(pnl_pct) if pnl_pct is not None else None),
                    payload={
                        "order_link_id": order_link_id,
                        "side": side,
                        "qty": qty_str,
                        "price": price_str,
                        "order_type": exit_order_type,
                    },
                    applied=True,
                    log=log,
                )
            else:
                _record_futures_decision(
                    symbol=symbol,
                    side=side,
                    decision_type="forced_exit_submitted",
                    reason=str(reason),
                    payload={
                        "order_link_id": order_link_id,
                        "qty": qty_str,
                        "price": price_str,
                        "order_type": exit_order_type,
                    },
                    applied=True,
                )
            return True

        def _planned_exit_price(symbol: str, position_qty: float, orderbook: Any) -> float | None:
            entry = float(avg_entry_price.get(symbol, 0.0))
            if entry <= 0:
                entry = float(orderbook.mid or 0.0)
            if entry <= 0:
                return None

            target_ratio = max(float(symbol_target_profit_ratio.get(symbol, config.strategy.target_profit)), 0.0)
            safety_ratio = max(float(symbol_safety_buffer_ratio.get(symbol, config.strategy.safety_buffer)), 0.0)
            fee_ratio = max(float(config.fees.maker_rate), 0.0)
            required_ratio = target_ratio + safety_ratio + (2.0 * fee_ratio)

            if position_qty > 0:
                raw = entry * (1.0 + required_ratio)
                raw = max(raw, float(orderbook.best_ask))
            else:
                raw = entry * (1.0 - required_ratio)
                raw = min(raw, float(orderbook.best_bid))
            if raw <= 0:
                return None
            return raw

        async def maybe_place_position_exit_quote(
            symbol: str,
            open_position_orders: dict[str, list[dict[str, Any]]],
        ) -> bool:
            """
            Keep a live PostOnly exit quote for an opened position.
            This makes exit intent explicit and continuously repriced.
            """
            if executor is None:
                return False
            if time.monotonic() - last_force_exit_ts.get(symbol, 0.0) < force_exit_cooldown_sec:
                return False

            pos_qty = float(net_position_base.get(symbol, 0.0))
            pos_floor = await _resolve_position_floor(symbol)
            if abs(pos_qty) < pos_floor:
                return False
            notional_floor = await _resolve_position_notional_floor(symbol)

            ob = state.get_orderbook(symbol)
            if ob is None or ob.best_bid <= 0 or ob.best_ask <= 0 or ob.best_ask <= ob.best_bid:
                return False

            planned = _planned_exit_price(symbol, pos_qty, ob)
            if planned is None:
                return False

            tick_size = state.get_tick_size(symbol) or config.strategy.default_tick_size
            tick_size = max(float(tick_size), 1e-12)
            planned_price = round(planned / tick_size) * tick_size
            if pos_qty > 0 and planned_price <= ob.best_bid:
                planned_price = ob.best_ask
            if pos_qty < 0 and planned_price >= ob.best_ask:
                planned_price = ob.best_bid
            if planned_price <= 0:
                return False

            side = "Sell" if pos_qty > 0 else "Buy"
            qty = abs(pos_qty)
            if spot_notional_floor_enabled and notional_floor > 0 and (qty * planned_price) < notional_floor:
                dust_exit_suppressed_until[symbol] = time.monotonic() + force_exit_dust_cooldown_sec
                _reset_symbol_runtime_state(symbol)
                log.info(
                    "Position-exit quote skipped as dust (notional floor): symbol=%s side=%s qty=%.12f planned=%.10f notional=%.8f floor=%.8f",
                    symbol,
                    side,
                    qty,
                    planned_price,
                    qty * planned_price,
                    notional_floor,
                )
                return False

            existing_orders = open_position_orders.get(symbol, [])
            for existing in existing_orders:
                if str(existing.get("side") or "").strip().lower() != side.lower():
                    continue
                ex_price = float(existing.get("price") or 0.0)
                ex_qty = float(existing.get("qty") or 0.0)
                if abs(ex_price - planned_price) <= tick_size and abs(ex_qty - qty) <= max(pos_floor, 1e-9):
                    return False

            for existing in existing_orders:
                link = str(existing.get("orderLinkId") or "").strip()
                ex_symbol = str(existing.get("symbol") or symbol).strip().upper() or symbol
                if not link:
                    continue
                await executor.cancel_order(symbol=ex_symbol, order_link_id=link)

            qty_str = _fmt_float(qty)
            price_str = _fmt_float(planned_price)
            order_link_id = f"px-{symbol}-{uuid.uuid4().hex[:10]}"
            ret = await executor.place_order(
                symbol=symbol,
                side=side,
                qty=qty_str,
                price=price_str,
                order_link_id=order_link_id,
                time_in_force="PostOnly",
            )
            if ret.get("retCode") != 0:
                if ret.get("retCode") == -2 and str(ret.get("retMsg") or "") == "invalid_qty_after_normalization":
                    dust_exit_suppressed_until[symbol] = time.monotonic() + force_exit_dust_cooldown_sec
                    _reset_symbol_runtime_state(symbol)
                log.info(
                    "Position-exit quote skipped: symbol=%s side=%s qty=%s price=%s retCode=%s retMsg=%s",
                    symbol,
                    side,
                    qty_str,
                    price_str,
                    ret.get("retCode"),
                    ret.get("retMsg"),
                )
                return False

            risk_manager.register_order_placed()
            write_runtime_order_legacy_and_domain(
                conn,
                market_category=runtime_market_category,
                symbol=symbol,
                side=side,
                order_link_id=order_link_id,
                price=float(price_str),
                qty=float(qty_str),
                status="New",
                created_at_utc=utc_now_iso(),
                log=log,
                exchange_order_id=(ret.get("result") or {}).get("orderId"),
                order_type="Limit",
                time_in_force="PostOnly",
                strategy_owner=strategy.__class__.__name__,
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
                time_in_force="PostOnly",
                price=float(price_str),
                qty=float(qty_str),
                order_status="New",
            )
            log.info(
                "Position-exit quote: symbol=%s side=%s qty=%s planned_exit=%s entry=%.8f mark=%.8f",
                symbol,
                side,
                qty_str,
                price_str,
                float(avg_entry_price.get(symbol, 0.0)),
                float(ob.best_bid if pos_qty > 0 else ob.best_ask),
            )
            return True

        def _prepare_intent_for_send(intent: Any, maker_only: bool) -> Any | None:
            """
            Recompute quote from latest top-of-book right before sending.
            Maker entries keep safe price inside spread; taker entries cross at best price.
            """
            if not fast_reprice_on_send:
                return intent

            ob = state.get_orderbook(intent.symbol)
            if ob is None or ob.best_bid <= 0 or ob.best_ask <= 0 or ob.best_ask <= ob.best_bid:
                return None

            now_ms = int(time.time() * 1000)
            book_ts = state.get_last_book_update_ms(intent.symbol)
            if book_ts is None or (now_ms - int(book_ts)) > quote_max_book_age_ms:
                return None

            tick_size = state.get_tick_size(intent.symbol) or config.strategy.default_tick_size
            tick_size = max(float(tick_size), 1e-12)
            tick_offset = max(int(getattr(intent, "action_entry_tick_offset", None) or config.strategy.entry_tick_offset), 0)
            tick = tick_size * tick_offset

            if str(intent.side).upper() == "BUY":
                if maker_only:
                    target_price = ob.best_bid + tick
                    if target_price >= ob.best_ask:
                        target_price = ob.best_bid
                else:
                    target_price = ob.best_ask + tick
            else:
                if maker_only:
                    target_price = ob.best_ask - tick
                    if target_price <= ob.best_bid:
                        target_price = ob.best_ask
                else:
                    target_price = ob.best_bid - tick

            snapped_price = round(target_price / tick_size) * tick_size
            if snapped_price <= 0:
                return None
            return replace(intent, price=float(snapped_price))

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
                if state.restart_requested:
                    raise RestartRequested("restart_requested")
                await asyncio.sleep(scanner_interval_sec)
                try:
                    selected, summary = pick_active_symbols(state, config)
                    if not selected:
                        if config.strategy.strict_pair_filter:
                            # With strict pair filter enabled, forcing fallback symbols only creates
                            # guaranteed guarded rejects (PAIR_FILTER_NOT_PASS). Keep list empty.
                            selected = []
                            summary["selected"] = 0
                            summary["fallback"] = False
                            summary["no_pass_symbols"] = True
                        else:
                            selected = list(config.symbols[: max(int(config.strategy.scanner_top_k), 1)])
                            summary["selected"] = len(selected)
                            summary["fallback"] = True
                    else:
                        summary["fallback"] = False

                    _maybe_refresh_policy_model()
                    pair_ctx = state.get_all_pair_filter_snapshots()
                    if policy_ml_enabled:
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
                                "PairFilter symbol=%s status=%s reason=%s median_spread_bps=%.4f trades_per_min=%.2f p95_trade_gap_ms=%.0f depth_bid_quote=%.2f depth_ask_quote=%.2f slippage_buy_bps=%.4f slippage_sell_bps=%.4f vol_1s_bps=%.4f min_required_spread_bps=%.4f impulse_bps=%.4f spike_dir=%s spike_strength_bps=%.4f stale_data=%s data_age_ms=%s",
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
                                float(snap.get("impulse_bps", 0.0)),
                                int(float(snap.get("spike_direction", 0.0) or 0.0)),
                                float(snap.get("spike_strength_bps", 0.0)),
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

        async def recover_positions_on_startup() -> None:
            """
            On bot startup or soft-restart: reconstruct open positions from:
              1. Local DB (executions_raw, last 24h) â€” fast, no API call.
              2. Exchange get_execution_list() â€” catches fills not yet in DB.
            Seeds seen_exec_ids so the regular refresh loop won't double-count.
            After recovery, any position past its SL/TP/timeout will be closed
            by maybe_force_exit() on the very first trading loop iteration.
            """
            log.info("Startup position recovery: scanning DB executions_raw (last 24h)...")
            cutoff_ms = int((time.time() - 86400) * 1000)  # 24 hours ago

            # --- Step 1: Replay fills from local DB ---
            try:
                rows = conn.execute(
                    """
                    SELECT exec_id, symbol, side, exec_qty, exec_price, exec_fee, fee_currency
                    FROM executions_raw
                    WHERE exec_time_ms > ?
                    ORDER BY exec_time_ms ASC
                    """,
                    (cutoff_ms,),
                ).fetchall()
            except Exception as exc:
                log.warning("Startup recovery: DB query failed, skipping DB replay: %s", exc)
                rows = []

            db_replayed = 0
            for row in rows:
                exec_id, symbol, side, exec_qty, exec_price, exec_fee, fee_currency = row
                if not exec_id:
                    continue
                seen_exec_ids.add(exec_id)  # pre-seed to avoid double-counting

                if not symbol or not side:
                    continue
                qty = float(exec_qty or 0.0)
                price = float(exec_price or 0.0)
                side_l = str(side).lower()
                if qty <= 0 or side_l not in {"buy", "sell"}:
                    continue

                base_ccy, _ = _split_symbol_base_quote(symbol.upper())
                fee = float(exec_fee or 0.0)
                fee_ccy = str(fee_currency or "").upper()
                effective_qty = qty
                if base_ccy and fee_ccy == base_ccy:
                    effective_qty = max(qty - fee, 0.0) if side_l == "buy" else qty + max(fee, 0.0)
                if effective_qty <= 0:
                    continue

                net_position_base.setdefault(symbol, 0.0)
                avg_entry_price.setdefault(symbol, 0.0)
                old_qty = net_position_base[symbol]
                old_avg = avg_entry_price[symbol]
                new_qty, new_avg = apply_fill(
                    current_qty=old_qty,
                    current_avg_entry=old_avg,
                    side=side_l,
                    fill_qty=effective_qty,
                    fill_price=price,
                )
                net_position_base[symbol] = new_qty
                avg_entry_price[symbol] = new_avg
                db_replayed += 1

            log.info("Startup recovery: replayed %d fills from DB.", db_replayed)

            # --- Step 2: Exchange API â€” catch fills not yet written to DB ---
            if executor is not None:
                all_symbols: set[str] = set(config.symbols)
                all_symbols.update(s for s, q in net_position_base.items() if abs(q) > 0)
                for symbol in all_symbols:
                    try:
                        resp = await executor.get_execution_list(symbol=symbol, limit=200)
                    except Exception as exc:
                        log.warning("Startup recovery: get_execution_list failed for %s: %s", symbol, exc)
                        continue
                    if resp.get("retCode") != 0:
                        continue
                    items = (resp.get("result") or {}).get("list") or []
                    for item in reversed(items):
                        exec_id = str(
                            item.get("execId")
                            or f"{item.get('orderId')}:{item.get('execTime')}:{item.get('execQty')}:{item.get('symbol')}"
                        )
                        if exec_id in seen_exec_ids:
                            continue  # already replayed from DB or previous run
                        seen_exec_ids.add(exec_id)

                        side = str(item.get("side") or "").lower()
                        qty = float(item.get("execQty") or item.get("qty") or 0.0)
                        price = float(item.get("execPrice") or item.get("price") or 0.0)
                        if qty <= 0 or side not in {"buy", "sell"}:
                            continue

                        base_ccy, _ = _split_symbol_base_quote(symbol.upper())
                        exec_fee = float(item.get("execFee") or 0.0)
                        fee_ccy = str(item.get("feeCurrency") or "").upper()
                        effective_qty = qty
                        if base_ccy and fee_ccy == base_ccy:
                            effective_qty = max(qty - exec_fee, 0.0) if side == "buy" else qty + max(exec_fee, 0.0)
                        if effective_qty <= 0:
                            continue

                        net_position_base.setdefault(symbol, 0.0)
                        avg_entry_price.setdefault(symbol, 0.0)
                        old_qty = net_position_base[symbol]
                        old_avg = avg_entry_price[symbol]
                        new_qty, new_avg = apply_fill(
                            current_qty=old_qty,
                            current_avg_entry=old_avg,
                            side=side,
                            fill_qty=effective_qty,
                            fill_price=price,
                        )
                        net_position_base[symbol] = new_qty
                        avg_entry_price[symbol] = new_avg

            # --- Step 3: Wallet balance cross-check (spot ground truth) ---
            # On spot, a filled buy has NO open order â€” coin just sits in wallet.
            # If DB/API replay missed any fills, wallet balance is the last safety net.
            if executor is not None:
                try:
                    wb_resp = await executor.get_wallet_balance(account_type="UNIFIED")
                    if wb_resp.get("retCode") == 0:
                        for account in (wb_resp.get("result") or {}).get("list") or []:
                            for coin_info in (account.get("coin") or []):
                                coin = str(coin_info.get("coin") or "").upper().strip()
                                if not coin or coin in ("USDT", "USDC", "BUSD"):
                                    continue
                                wb_qty = float(coin_info.get("walletBalance") or 0.0)
                                if wb_qty <= 0:
                                    continue
                                sym = f"{coin}USDT"
                                tracked = abs(float(net_position_base.get(sym, 0.0)))
                                if tracked < wb_qty * 0.5:
                                    # We hold this coin but DB/API replay missed it.
                                    # Mark it so the timeout exit fires quickly.
                                    log.warning(
                                        "Startup recovery: wallet holds %s=%.8f but net_position_base=%.8f â€” "
                                        "importing as recovered holding (auto-sell disabled).",
                                        sym, wb_qty, tracked,
                                    )
                                    upsert_spot_holding(
                                        conn,
                                        account_type="UNIFIED",
                                        symbol=sym,
                                        base_asset=coin,
                                        free_qty=wb_qty,
                                        locked_qty=0.0,
                                        avg_entry_price=None,
                                        hold_reason="unknown_recovered_from_exchange",
                                        source_of_truth="startup_wallet_recovery",
                                        recovered_from_exchange=True,
                                        strategy_owner=None,
                                        auto_sell_allowed=False,
                                    )
                except Exception as exc:
                    log.warning("Startup recovery: wallet balance check failed: %s", exc)

            # --- Step 4: Report and mark recovered positions ---
            open_positions = {
                s: q for s, q in net_position_base.items() if abs(q) >= _position_floor(s)
            }
            if open_positions:
                log.warning(
                    "Startup recovery: found %d open position(s) â€” will apply exit checks immediately: %s",
                    len(open_positions),
                    ", ".join(
                        f"{s}=qty:{q:.8f} avg_entry:{avg_entry_price.get(s, 0.0):.6f}"
                        for s, q in open_positions.items()
                    ),
                )
                # Mark positions as opened so maybe_force_exit() processes them
                for s, q in open_positions.items():
                    if position_opened_at.get(s) is None:
                        # Use current time â€” age=0, so only SL/TP triggers (not timeout yet)
                        # This is safe: timeout will trigger after hold_timeout_sec from now
                        position_opened_at[s] = time.monotonic()
                        symbol_peak_pnl_bps[s] = 0.0
            else:
                log.info("Startup recovery: no open positions found â€” starting clean.")

        async def trading_loop() -> None:
            nonlocal last_position_status_log_at, last_reconciliation_run_ts
            if executor is None:
                return

            last_reconciliation_run_ts, _ = await run_reconciliation_startup(
                reconciliation_service,
                log=log,
            )

            # Cancel ALL open orders before recovery so we start from a clean slate.
            # This prevents stale SPREAD/spike quotes from accumulating across restarts.
            try:
                log.warning("Startup: cancelling all open orders before position recovery...")
                cancel_resp = await executor.cancel_all_orders()
                if cancel_resp.get("retCode") == 0:
                    log.warning("Startup: all open orders cancelled successfully.")
                else:
                    log.warning(
                        "Startup: cancel_all_orders returned retCode=%s retMsg=%s",
                        cancel_resp.get("retCode"),
                        cancel_resp.get("retMsg"),
                    )
            except Exception as exc:
                log.warning("Startup: cancel_all_orders failed: %s", exc)

            await recover_positions_on_startup()

            last_paused_log_at = 0.0
            loop_no = 0
            while True:
                if state.restart_requested:
                    log.info("Restart requested: rebuilding trading runtime without cancel-all.")
                    raise RestartRequested("restart_requested")
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

                last_reconciliation_run_ts, _ = await run_reconciliation_scheduled_if_due(
                    reconciliation_service,
                    last_run_ts=last_reconciliation_run_ts,
                    interval_sec=reconciliation_interval_sec,
                    log=log,
                )

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
                    our_mm_order_link_ids: list[tuple[str, str]] = []
                    open_position_orders: dict[str, list[dict[str, Any]]] = {}
                    open_list = (resp.get("result") or {}).get("list") or []
                    open_order_symbols: set[str] = {
                        str(order.get("symbol") or "").upper()
                        for order in open_list
                        if str(order.get("symbol") or "").strip()
                    }
                    await refresh_positions_from_executions(open_order_symbols=open_order_symbols)
                    await refresh_wallet_balance()
                    newly_placed_symbols: set[str] = set()  # symbols with orders placed THIS iteration
                    for order in open_list:
                        sym = order.get("symbol", "")
                        price = float(order.get("price") or 0)
                        qty = float(order.get("qty") or 0)
                        link = order.get("orderLinkId") or ""
                        notional = price * qty
                        total_exposure += notional
                        symbol_exposure[sym] = symbol_exposure.get(sym, 0.0) + notional
                        if link.startswith("mm-") or link.startswith("spk-"):
                            our_mm_order_link_ids.append((sym, link))
                        elif link.startswith("px-"):
                            open_position_orders.setdefault(sym, []).append(order)

                    for sym, link in our_mm_order_link_ids:
                        await executor.cancel_order(symbol=sym, order_link_id=link)

                    blocked_symbols: set[str] = set()
                    managed_symbols: set[str] = set(config.symbols)
                    managed_symbols.update(s for s, q in net_position_base.items() if abs(q) >= _position_floor(s))
                    for symbol in managed_symbols:
                        if await maybe_force_exit(symbol):
                            blocked_symbols.add(symbol)

                    position_exit_quotes = 0
                    for symbol in managed_symbols:
                        if await maybe_place_position_exit_quote(symbol, open_position_orders):
                            position_exit_quotes += 1

                    now_pos_log = time.monotonic()
                    if now_pos_log - last_position_status_log_at >= 10:
                        for symbol in managed_symbols:
                            pos_qty = float(net_position_base.get(symbol, 0.0))
                            pos_floor = _position_floor(symbol)
                            if abs(pos_qty) < pos_floor:
                                continue
                            ob = state.get_orderbook(symbol)
                            if ob is None:
                                continue
                            planned = _planned_exit_price(symbol, pos_qty, ob)
                            mark_price = ob.best_bid if pos_qty > 0 else ob.best_ask
                            log.info(
                                "PositionWatch symbol=%s qty=%.8f entry=%.8f mark=%.8f planned_exit=%s side=%s",
                                symbol,
                                pos_qty,
                                float(avg_entry_price.get(symbol, 0.0)),
                                float(mark_price),
                                "n/a" if planned is None else _fmt_float(float(planned)),
                                "Sell" if pos_qty > 0 else "Buy",
                            )
                        last_position_status_log_at = now_pos_log

                    intents = strategy.get_intents(state)
                    strategy_summary = strategy.get_last_summary()
                    risk_reject_count = 0
                    place_fail_count = 0
                    placed_count = 0
                    fast_reprice_reject_count = 0

                    for intent in intents:
                        if intent.symbol in blocked_symbols:
                            continue
                        maker_only_entry = (
                            bool(intent.action_maker_only)
                            if intent.action_maker_only is not None
                            else runtime_strategy_mode != "spike_reversal"
                        )
                        time_in_force = "PostOnly" if maker_only_entry else "IOC"
                        intent_to_send = _prepare_intent_for_send(intent, maker_only=maker_only_entry)
                        if intent_to_send is None:
                            fast_reprice_reject_count += 1
                            continue
                        if intent_to_send.action_maker_only is None:
                            intent_to_send = replace(intent_to_send, action_maker_only=maker_only_entry)

                        signal_id = f"sig-{intent_to_send.order_link_id}"
                        ob = state.get_orderbook(intent_to_send.symbol)
                        pair = state.get_pair_filter_snapshot(intent_to_send.symbol) or {}
                        policy_meta = state.get_active_policy_meta(intent_to_send.symbol)
                        best_bid = ob.best_bid if ob is not None else 0.0
                        best_ask = ob.best_ask if ob is not None else 0.0
                        mid = ob.mid if ob is not None else 0.0
                        spread_bps = ((best_ask - best_bid) / mid) * 10000.0 if mid > 0 and best_ask >= best_bid else 0.0
                        insert_signal_snapshot(
                            conn,
                            signal_id=signal_id,
                            ts_signal_ms=int(time.time() * 1000),
                            symbol=intent_to_send.symbol,
                            side=intent_to_send.side,
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
                            impulse_bps=float(pair.get("impulse_bps", 0.0)),
                            spike_direction=int(float(pair.get("spike_direction", 0.0) or 0.0)),
                            spike_strength_bps=float(pair.get("spike_strength_bps", 0.0)),
                            min_required_spread_bps=float(pair.get("min_required_spread_bps", 0.0)),
                            scanner_status=str(pair.get("status", "NA")),
                            model_version=str(intent_to_send.model_version or ""),
                            profile_id=intent_to_send.profile_id,
                            action_entry_tick_offset=intent_to_send.action_entry_tick_offset,
                            action_order_qty_base=intent_to_send.action_order_qty_base,
                            action_target_profit=intent_to_send.action_target_profit,
                            action_safety_buffer=intent_to_send.action_safety_buffer,
                            action_min_top_book_qty=intent_to_send.action_min_top_book_qty,
                            action_stop_loss_pct=intent_to_send.action_stop_loss_pct,
                            action_take_profit_pct=intent_to_send.action_take_profit_pct,
                            action_hold_timeout_sec=intent_to_send.action_hold_timeout_sec,
                            action_maker_only=intent_to_send.action_maker_only,
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
                            order_size_quote=float(intent_to_send.price * intent_to_send.qty),
                            order_size_base=float(intent_to_send.qty),
                            entry_price=float(intent_to_send.price),
                        )
                        if runtime_market_category == "spot":
                            write_spot_position_intent_safe(
                                conn,
                                symbol=intent_to_send.symbol,
                                side=intent_to_send.side,
                                qty=float(intent_to_send.qty),
                                price=float(intent_to_send.price),
                                order_link_id=intent_to_send.order_link_id,
                                strategy_owner=strategy.__class__.__name__,
                                profile_id=(str(intent_to_send.profile_id) if intent_to_send.profile_id else None),
                                signal_id=signal_id,
                                log=log,
                            )

                        reconciliation_block_reason = get_reconciliation_entry_block_reason(
                            conn,
                            symbol=intent_to_send.symbol,
                        )
                        if reconciliation_block_reason:
                            risk_reject_count += 1
                            log.warning(
                                "Entry blocked by reconciliation lock: symbol=%s issues=%s order_link_id=%s",
                                intent_to_send.symbol,
                                reconciliation_block_reason,
                                intent_to_send.order_link_id,
                            )
                            insert_event_audit(
                                conn,
                                event_type="entry_blocked_reconciliation_lock",
                                domain=("futures" if runtime_market_category == "linear" else "spot"),
                                symbol=intent_to_send.symbol,
                                ref_id=intent_to_send.order_link_id,
                                payload={
                                    "issues": reconciliation_block_reason,
                                    "signal_id": signal_id,
                                },
                            )
                            if runtime_market_category == "linear":
                                _record_futures_decision(
                                    symbol=intent_to_send.symbol,
                                    side=intent_to_send.side,
                                    decision_type="entry_rejected",
                                    reason="reconciliation_lock",
                                    payload={
                                        "issues": reconciliation_block_reason,
                                        "order_link_id": intent_to_send.order_link_id,
                                    },
                                    applied=False,
                                )
                            continue

                        spot_blocked, blocked_reason = _spot_sell_blocked_by_hold_policy(
                            intent_to_send.symbol,
                            intent_to_send.side,
                        )
                        if spot_blocked:
                            risk_reject_count += 1
                            log.warning(
                                "Spot sell rejected by hold policy: symbol=%s hold_reason=%s order_link_id=%s",
                                intent_to_send.symbol,
                                blocked_reason,
                                intent_to_send.order_link_id,
                            )
                            continue

                        if runtime_market_category == "linear":
                            gate_mark_price = float(ob.mid) if ob is not None and float(ob.mid or 0.0) > 0 else None
                            risk_gate_allowed, risk_gate_reason, risk_gate_view = futures_entry_risk_gate(
                                conn,
                                symbol=intent_to_send.symbol,
                                account_type="UNIFIED",
                                fallback_mark_price=gate_mark_price,
                            )
                            if not risk_gate_allowed:
                                risk_reject_count += 1
                                _record_futures_decision(
                                    symbol=intent_to_send.symbol,
                                    side=intent_to_send.side,
                                    decision_type="entry_rejected",
                                    reason=risk_gate_reason,
                                    payload={
                                        "order_link_id": intent_to_send.order_link_id,
                                        "risk_gate": risk_gate_view,
                                    },
                                    applied=False,
                                )
                                log.warning(
                                    "Futures entry rejected by symbol risk gate: symbol=%s reason=%s risk_state=%s distance_to_liq_bps=%s",
                                    intent_to_send.symbol,
                                    risk_gate_reason,
                                    risk_gate_view.get("risk_state"),
                                    risk_gate_view.get("distance_to_liq_bps"),
                                )
                                continue

                            entry_sl_pct = (
                                float(intent_to_send.action_stop_loss_pct)
                                if intent_to_send.action_stop_loss_pct is not None
                                else float(symbol_stop_loss_pct.get(intent_to_send.symbol, stop_loss_pct))
                            )
                            entry_tp_pct = (
                                float(intent_to_send.action_take_profit_pct)
                                if intent_to_send.action_take_profit_pct is not None
                                else float(symbol_take_profit_pct.get(intent_to_send.symbol, take_profit_pct))
                            )
                            blocking_status = _blocking_futures_protection_status(intent_to_send.symbol)
                            if blocking_status:
                                risk_reject_count += 1
                                _record_futures_decision(
                                    symbol=intent_to_send.symbol,
                                    side=intent_to_send.side,
                                    decision_type="entry_rejected",
                                    reason=f"symbol_has_blocking_protection_status:{blocking_status}",
                                    payload={
                                        "protection_status": blocking_status,
                                        "order_link_id": intent_to_send.order_link_id,
                                    },
                                    applied=False,
                                )
                                log.warning(
                                    "Futures entry rejected: symbol=%s blocking_protection_status=%s",
                                    intent_to_send.symbol,
                                    blocking_status,
                                )
                                continue
                            entry_allowed, entry_reason = futures_entry_allowed(
                                stop_loss_pct=entry_sl_pct,
                                take_profit_pct=entry_tp_pct,
                                has_unprotected_position=False,
                            )
                            if not entry_allowed:
                                risk_reject_count += 1
                                _record_futures_decision(
                                    symbol=intent_to_send.symbol,
                                    side=intent_to_send.side,
                                    decision_type="entry_rejected",
                                    reason=entry_reason,
                                    payload={
                                        "stop_loss_pct": entry_sl_pct,
                                        "take_profit_pct": entry_tp_pct,
                                        "order_link_id": intent_to_send.order_link_id,
                                    },
                                    applied=False,
                                )
                                log.warning(
                                    "Futures entry rejected: symbol=%s reason=%s stop_loss_pct=%.6f take_profit_pct=%.6f",
                                    intent_to_send.symbol,
                                    entry_reason,
                                    entry_sl_pct,
                                    entry_tp_pct,
                                )
                                continue

                        # Count unique symbols we're "in" â€” three independent sources:
                        # 1. net_position_base: fills tracked via WS execution stream
                        # 2. open_order_symbols: pending orders fetched from exchange this loop
                        # 3. wallet_held_base_symbols â†’ {coin}USDT: actual wallet holdings
                        #    (ground truth for spot â€” a filled buy has NO open order, coin is just held)
                        # 4. newly_placed_symbols: orders placed earlier in THIS loop iteration
                        #    (open_order_symbols is stale â€” fetched at start of loop, before new placements)
                        _filled_pos_symbols = {
                            s for s, q in net_position_base.items() if abs(q) >= _position_floor(s)
                        }
                        _wallet_symbols = {f"{c}USDT" for c in wallet_held_base_symbols}
                        _all_active_symbols = (
                            _filled_pos_symbols | open_order_symbols | _wallet_symbols | newly_placed_symbols
                        ) - {intent_to_send.symbol}
                        current_open_pos_count = len(_all_active_symbols)
                        _risk_leverage = resolve_risk_leverage(config, runtime_market_category)
                        risk = risk_manager.check_order(
                            intent_to_send.symbol,
                            intent_to_send.side,
                            intent_to_send.price,
                            intent_to_send.qty,
                            total_exposure,
                            symbol_exposure.get(intent_to_send.symbol, 0.0),
                            current_open_positions=current_open_pos_count,
                            leverage=_risk_leverage,
                        )
                        if not risk.allowed:
                            risk_reject_count += 1
                            log.debug("Risk reject: %s", risk.reason)
                            continue

                        ret = await guarded_place_order(intent_to_send, time_in_force)

                        if ret.get("retCode") == 10004:
                            log.error("Stopping trading loop: invalid REST signature on place_order (10004).")
                            state.set_paused(True)
                            return
                        if ret.get("retCode") != 0:
                            log.warning(
                                "place_order failed: symbol=%s retCode=%s retMsg=%s",
                                intent_to_send.symbol,
                                ret.get("retCode"),
                                ret.get("retMsg"),
                            )
                            place_fail_count += 1
                            continue

                        placed_count += 1
                        newly_placed_symbols.add(intent_to_send.symbol)  # track intra-iteration placements
                        risk_manager.register_order_placed()
                        if intent_to_send.action_hold_timeout_sec is not None:
                            symbol_hold_timeout_sec[intent_to_send.symbol] = float(max(intent_to_send.action_hold_timeout_sec, 1))
                        if intent_to_send.action_stop_loss_pct is not None:
                            symbol_stop_loss_pct[intent_to_send.symbol] = float(max(intent_to_send.action_stop_loss_pct, 0.0))
                        if intent_to_send.action_take_profit_pct is not None:
                            symbol_take_profit_pct[intent_to_send.symbol] = float(max(intent_to_send.action_take_profit_pct, 0.0))
                        if intent_to_send.action_target_profit is not None:
                            symbol_target_profit_ratio[intent_to_send.symbol] = float(max(intent_to_send.action_target_profit, 0.0))
                        if intent_to_send.action_safety_buffer is not None:
                            symbol_safety_buffer_ratio[intent_to_send.symbol] = float(max(intent_to_send.action_safety_buffer, 0.0))
                        total_exposure += intent_to_send.price * intent_to_send.qty
                        symbol_exposure[intent_to_send.symbol] = (
                            symbol_exposure.get(intent_to_send.symbol, 0.0) + intent_to_send.price * intent_to_send.qty
                        )
                        write_runtime_order_legacy_and_domain(
                            conn,
                            market_category=runtime_market_category,
                            symbol=intent_to_send.symbol,
                            side=intent_to_send.side,
                            order_link_id=intent_to_send.order_link_id,
                            price=float(intent_to_send.price),
                            qty=float(intent_to_send.qty),
                            status="New",
                            created_at_utc=utc_now_iso(),
                            log=log,
                            exchange_order_id=(ret.get("result") or {}).get("orderId"),
                            order_type="Limit",
                            time_in_force=time_in_force,
                            strategy_owner=strategy.__class__.__name__,
                        )
                        set_order_signal_map(conn, intent_to_send.order_link_id, signal_id)
                        insert_order_event(
                            conn,
                            symbol=intent_to_send.symbol,
                            order_link_id=intent_to_send.order_link_id,
                            order_id=(ret.get("result") or {}).get("orderId"),
                            signal_id=signal_id,
                            side=intent_to_send.side,
                            order_type="Limit",
                            time_in_force=time_in_force,
                            price=float(intent_to_send.price),
                            qty=float(intent_to_send.qty),
                            order_status="New",
                        )
                        if runtime_market_category == "linear":
                            side = "Buy" if str(intent_to_send.side).lower() == "buy" else "Sell"
                            sl_pct = (
                                float(intent_to_send.action_stop_loss_pct)
                                if intent_to_send.action_stop_loss_pct is not None
                                else float(symbol_stop_loss_pct.get(intent_to_send.symbol, stop_loss_pct))
                            )
                            tp_pct = (
                                float(intent_to_send.action_take_profit_pct)
                                if intent_to_send.action_take_profit_pct is not None
                                else float(symbol_take_profit_pct.get(intent_to_send.symbol, take_profit_pct))
                            )
                            planned = build_futures_protection_plan(
                                entry_price=float(intent_to_send.price),
                                position_qty=(float(intent_to_send.qty) if side == "Buy" else -float(intent_to_send.qty)),
                                stop_loss_pct=sl_pct,
                                take_profit_pct=tp_pct,
                            )
                            if planned is not None:
                                upsert_futures_protection(
                                    conn,
                                    account_type="UNIFIED",
                                    symbol=str(intent_to_send.symbol).upper(),
                                    side=side,
                                    position_idx=0,
                                    status="pending",
                                    source_of_truth="strategy_entry_plan",
                                    stop_loss=planned.stop_loss,
                                    take_profit=planned.take_profit,
                                    trailing_stop=planned.trailing_stop,
                                    details={
                                        "order_link_id": intent_to_send.order_link_id,
                                        "stop_loss_pct": sl_pct,
                                        "take_profit_pct": tp_pct,
                                    },
                                )
                                _record_futures_decision(
                                    symbol=intent_to_send.symbol,
                                    side=side,
                                    decision_type="protection_plan_created",
                                    reason="entry_order_placed",
                                    payload={
                                        "order_link_id": intent_to_send.order_link_id,
                                        "stop_loss": planned.stop_loss,
                                        "take_profit": planned.take_profit,
                                    },
                                    applied=False,
                                )
                            _record_futures_decision(
                                symbol=intent_to_send.symbol,
                                side=side,
                                decision_type="entry_submitted",
                                reason="entry_order_accepted",
                                payload={
                                    "order_link_id": intent_to_send.order_link_id,
                                    "time_in_force": time_in_force,
                                },
                                applied=True,
                            )

                    ws_books_ready = sum(1 for s in config.symbols if state.get_orderbook(s) is not None)
                    active_ws_books_ready = sum(1 for s in active_symbols if state.get_orderbook(s) is not None)
                    scanner_snapshot = state.get_scanner_snapshot()
                    log.info(
                        "Loop #%s: ws_books=%s/%s active_ws_books=%s/%s active_symbols=%s open_orders=%s mm_canceled=%s pos_exit_quotes=%s intents=%s placed=%s risk_reject=%s place_fail=%s fast_reprice_reject=%s blocked_symbols=%s scanner=%s strategy=%s",
                        loop_no,
                        ws_books_ready,
                        len(config.symbols),
                        active_ws_books_ready,
                        len(active_symbols),
                        ",".join(active_symbols[:8]) if active_symbols else "none",
                        len(open_list),
                        len(our_mm_order_link_ids),
                        position_exit_quotes,
                        len(intents),
                        placed_count,
                        risk_reject_count,
                        place_fail_count,
                        fast_reprice_reject_count,
                        len(blocked_symbols),
                        scanner_snapshot,
                        strategy_summary,
                    )
                except Exception as exc:
                    log.exception("Trading loop error: %s", exc)

        ws = BybitPublicOrderbookWS(
            ws_host=config.bybit.ws_public_host,
            symbols=config.symbols,
            depth=config.ws_depth,
            state=state,
            tick_size=config.strategy.default_tick_size,
            category=runtime_market_category,
        )
        interval = config.storage.metrics_interval_sec

        async def metrics_loop() -> None:
            while True:
                if state.restart_requested:
                    raise RestartRequested("restart_requested")
                await asyncio.sleep(interval)
                ts = utc_now_iso()
                metric_rows: list[tuple[str, str, float | None, float | None, float | None, int | None, float | None]] = []
                for symbol in config.symbols:
                    ob = state.get_orderbook(symbol)
                    if ob is None:
                        continue
                    metric_rows.append(
                        (
                            symbol,
                            ts,
                            ob.best_bid,
                            ob.best_ask,
                            ob.mid,
                            ob.spread_ticks,
                            ob.imbalance_top_n,
                        )
                    )
                if not metric_rows:
                    continue
                try:
                    insert_metrics_batch(conn, metric_rows)
                except sqlite3.OperationalError as exc:
                    # Metrics are best-effort; skip this slice on lock contention and keep trading loop alive.
                    log.warning("metrics_loop write skipped: %s", exc)

        async def universe_loop() -> None:
            if not auto_universe_enabled:
                return

            while True:
                if state.restart_requested:
                    raise RestartRequested("restart_requested")
                await asyncio.sleep(auto_universe_refresh_sec)
                try:
                    discovered = await discover_top_symbols_by_category(
                        runtime_market_category,
                        host=config.strategy.auto_universe_host,
                        quote=config.strategy.auto_universe_quote,
                        limit=config.strategy.auto_universe_size,
                        min_symbols=config.strategy.auto_universe_min_symbols,
                        min_turnover_24h=config.strategy.auto_universe_min_turnover_24h,
                        min_raw_spread_bps=config.strategy.auto_universe_min_raw_spread_bps,
                        min_top_book_notional=config.strategy.auto_universe_min_top_book_notional,
                        exclude_st_tag_1=config.strategy.auto_universe_exclude_st_tag_1,
                    )
                    if not discovered:
                        continue

                    # Keep symbols with open position in the universe to preserve exit control.
                    protected = [s for s, q in net_position_base.items() if abs(q) >= _position_floor(s)]
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
                        dust_exit_suppressed_until.setdefault(s, 0.0)
                        symbol_hold_timeout_sec.setdefault(s, float(hold_timeout_sec))
                        symbol_stop_loss_pct.setdefault(s, float(stop_loss_pct))
                        symbol_take_profit_pct.setdefault(s, float(take_profit_pct))
                        symbol_target_profit_ratio.setdefault(s, float(max(config.strategy.target_profit, 0.0)))
                        symbol_safety_buffer_ratio.setdefault(s, float(max(config.strategy.safety_buffer, 0.0)))
                        symbol_peak_pnl_bps.setdefault(s, 0.0)
                        symbol_position_floor.setdefault(s, float(min_position_qty))
                        symbol_position_notional_floor.setdefault(s, float(min_active_position_usdt))

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
            upsert_strategy_run(
                conn,
                strategy_run_id=strategy_run_id,
                strategy_name=strategy.__class__.__name__,
                market_category=runtime_market_category,
                status="stopped",
                started_at_utc=strategy_run_started_at,
                finished_at_utc=utc_now_iso(),
                config_payload={
                    "runtime_strategy_mode": runtime_strategy_mode,
                    "symbols": list(config.symbols),
                    "execution_mode": mode,
                },
            )
            conn.close()

    while True:
        config = load_config(args.config)
        try:
            asyncio.run(run_ws_metrics_trading())
            break
        except RestartRequested:
            # /update requested soft restart: keep exchange orders alive and reconnect runtime loops.
            try:
                _hot_reload_runtime_modules()
            except Exception as exc:
                log.warning("Runtime hot-reload failed, continue with current module objects: %s", exc)
            state.set_restart_requested(False)
            state.set_update_in_progress(False, "restart_applied")
            refreshed_version = _resolve_runtime_version()
            if refreshed_version:
                state.set_current_version(refreshed_version)
            log.info("Runtime soft restart applied. version=%s", state.get_current_version()[:12])
            continue


if __name__ == "__main__":
    main()
