"""
SpotPaperEngine — paper-движок для спот торговли.

Хранит холдинги в spot_holdings, сделки в spot_orders/spot_fills.
На каждом тике цены обновляет unrealized_pnl и проверяет выход через policy.

Отличие от FuturesPaperEngine:
  - Нет коротких позиций (только buy/sell)
  - Нет плеча
  - Выход = продажа базового актива
  - PnL рассчитывается как: (exit_price - avg_entry) * qty - fees
  - Комиссия: 0.1% taker (Bybit spot)
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.botik.control.notifier import send_alert
from src.botik.position.base_policy import BasePositionPolicy, Position, PolicyAction
from src.botik.position.simple_exit import SimpleExitPolicy
from src.botik.storage.db import get_db

log = logging.getLogger("botik.execution.spot_paper")

SPOT_FEE_RATE = 0.001   # 0.1% taker (Bybit spot)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ms() -> int:
    return int(time.time() * 1000)


class SpotPaperEngine:
    """
    Paper-движок спот позиций.

    Жизненный цикл холдинга:
      buy()           → INSERT spot_holdings (account_type='SPOT_PAPER')
                        INSERT spot_orders (side='Buy')
      on_price_tick() → обновляет unrealized_pnl в spot_holdings
                        вызывает policy.on_tick() → если 'close_all' → sell()
      sell()          → UPDATE spot_holdings (free_qty -= qty)
                        INSERT spot_fills
                        если free_qty == 0 → DELETE spot_holdings

    Использует SimpleExitPolicy по умолчанию (SL/TP/timeout).
    """

    ACCOUNT_TYPE = "SPOT_PAPER"

    def __init__(
        self,
        policy: BasePositionPolicy | None = None,
        model_scope: str = "spot",
        balance_usdt: float = 10_000.0,
    ) -> None:
        self.policy = policy or SimpleExitPolicy(hold_timeout_ms=8 * 60 * 60 * 1000)  # 8ч таймаут
        self.model_scope = model_scope
        self._balance = balance_usdt          # свободный USDT
        self._initial_balance = balance_usdt

        # Кэш открытых холдингов: symbol → dict
        self._holdings: dict[str, dict[str, Any]] = {}

        # SL/TP кэш: (symbol) → (sl, tp)
        self._protection: dict[str, tuple[float, float]] = {}

        self._load_holdings_from_db()

    # ── Public API ────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        qty: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        entry_reason: str = "",
    ) -> str | None:
        """
        Открываем покупку (long spot).
        Возвращает order_link_id или None если уже есть холдинг / нет денег.
        """
        if symbol in self._holdings:
            log.debug("buy: уже есть холдинг %s", symbol)
            return None

        cost = entry_price * qty
        fee = cost * SPOT_FEE_RATE
        total_cost = cost + fee

        if total_cost > self._balance:
            log.debug("buy: недостаточно баланса (need=%.2f, have=%.2f)", total_cost, self._balance)
            return None

        trade_id = str(uuid.uuid4())
        now = _utc_now()
        now_ms = _now_ms()

        base_asset = symbol.replace("USDT", "").replace("BTC", "BTC") if "USDT" in symbol else symbol[:3]

        holding = {
            "trade_id": trade_id,
            "symbol": symbol,
            "base_asset": base_asset,
            "qty": qty,
            "avg_entry_price": entry_price,
            "current_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_fee": fee,
            "purchase_value_usdt": cost,
            "opened_at_ms": now_ms,
            "entry_reason": entry_reason,
        }
        self._holdings[symbol] = holding
        self._protection[symbol] = (stop_loss, take_profit)
        self._balance -= total_cost

        try:
            db = get_db()
            with db.connect() as conn:
                # Холдинг
                conn.execute(
                    """
                    INSERT INTO spot_holdings
                      (account_type, symbol, base_asset,
                       free_qty, locked_qty, avg_entry_price, current_price,
                       purchase_value_usdt, current_value_usdt, unrealized_pnl, unrealized_pnl_pct,
                       hold_reason, source_of_truth, auto_sell_allowed,
                       strategy_owner, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, 0, 0, ?, 'PAPER', 1, ?, ?, ?)
                    ON CONFLICT(account_type, symbol, base_asset) DO UPDATE SET
                      free_qty=excluded.free_qty,
                      avg_entry_price=excluded.avg_entry_price,
                      purchase_value_usdt=excluded.purchase_value_usdt,
                      hold_reason=excluded.hold_reason,
                      updated_at_utc=excluded.updated_at_utc
                    """,
                    (self.ACCOUNT_TYPE, symbol, base_asset, qty,
                     entry_price, entry_price, cost, cost,
                     f"entry={entry_price:.4f} sl={stop_loss:.4f} tp={take_profit:.4f}",
                     self.model_scope, now, now),
                )
                # Ордер
                conn.execute(
                    """
                    INSERT INTO spot_orders
                      (account_type, symbol, order_id, order_link_id,
                       side, order_type, price, qty, filled_qty, status,
                       is_maker, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, 'Buy', 'Market', ?, ?, ?, 'Filled', 0, ?, ?)
                    """,
                    (self.ACCOUNT_TYPE, symbol, trade_id, trade_id,
                     entry_price, qty, qty, now, now),
                )
        except Exception as exc:
            log.warning("buy DB error: %s", exc)

        log.debug("BUY %s qty=%.6f @ %.4f sl=%.4f tp=%.4f", symbol, qty, entry_price, stop_loss, take_profit)
        send_alert(
            f"🟢 <b>КУПЛЕНО</b> {symbol} [spot paper]\n"
            f"Цена: <b>${entry_price:,.4f}</b> | Кол-во: {qty:.6f}\n"
            f"SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f}"
        )
        return trade_id

    def sell(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str = "manual",
    ) -> dict[str, Any] | None:
        """
        Закрываем холдинг (продаём весь объём).
        Возвращает dict с результатом сделки или None если нет холдинга.
        """
        holding = self._holdings.pop(symbol, None)
        if holding is None:
            return None

        self._protection.pop(symbol, None)

        qty = holding["qty"]
        avg_entry = holding["avg_entry_price"]
        gross = exit_price * qty
        sell_fee = gross * SPOT_FEE_RATE
        net_proceeds = gross - sell_fee
        cost_basis = avg_entry * qty + holding["entry_fee"]
        net_pnl = net_proceeds - cost_basis

        hold_ms = _now_ms() - holding["opened_at_ms"]
        self._balance += net_proceeds
        now = _utc_now()
        exec_id = str(uuid.uuid4())

        try:
            db = get_db()
            with db.connect() as conn:
                # Удаляем холдинг
                conn.execute(
                    "DELETE FROM spot_holdings WHERE account_type=? AND symbol=? AND base_asset=?",
                    (self.ACCOUNT_TYPE, symbol, holding["base_asset"]),
                )
                # Ордер продажи
                sell_order_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO spot_orders
                      (account_type, symbol, order_id, order_link_id,
                       side, order_type, price, qty, filled_qty, status,
                       is_maker, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, 'Sell', 'Market', ?, ?, ?, 'Filled', 0, ?, ?)
                    """,
                    (self.ACCOUNT_TYPE, symbol, sell_order_id, sell_order_id,
                     exit_price, qty, qty, now, now),
                )
                # Fill
                conn.execute(
                    """
                    INSERT OR IGNORE INTO spot_fills
                      (exec_id, order_id, order_link_id, symbol, side,
                       exec_price, exec_qty, exec_fee, fee_currency,
                       is_maker, exec_time_ms, recorded_at_utc)
                    VALUES (?, ?, ?, ?, 'Sell', ?, ?, ?, 'USDT', 0, ?, ?)
                    """,
                    (exec_id, sell_order_id, sell_order_id, symbol,
                     exit_price, qty, sell_fee, _now_ms(), now),
                )
        except Exception as exc:
            log.warning("sell DB error: %s", exc)

        result = {
            "symbol": symbol,
            "side": "buy",
            "entry_price": avg_entry,
            "exit_price": exit_price,
            "qty": qty,
            "net_pnl": net_pnl,
            "hold_time_ms": hold_ms,
            "exit_reason": exit_reason,
            "model_scope": self.model_scope,
        }
        log.debug(
            "SELL %s qty=%.6f @ %.4f pnl=%+.4f [%s]",
            symbol, qty, exit_price, net_pnl, exit_reason,
        )
        pnl_sign = "+" if net_pnl >= 0 else ""
        pnl_pct = (net_pnl / (avg_entry * qty) * 100) if avg_entry and qty else 0.0
        send_alert(
            f"{'🔴' if net_pnl < 0 else '🟡'} <b>ПРОДАНО</b> {symbol} [spot paper]\n"
            f"Выход: <b>${exit_price:,.4f}</b> | PnL: <b>{pnl_sign}{net_pnl:.2f} USDT ({pnl_sign}{pnl_pct:.1f}%)</b>\n"
            f"Причина: {exit_reason}"
        )
        return result

    def on_price_tick(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """
        Обновляем текущую цену и проверяем выход.
        Возвращает список закрытых сделок.
        """
        holding = self._holdings.get(symbol)
        if holding is None:
            return []

        holding["current_price"] = price

        # Обновляем unrealized PnL в БД каждый тик (не слишком часто)
        self._update_holding_pnl(symbol, price, holding)

        # Создаём Position для policy
        sl, tp = self._protection.get(symbol, (0.0, 0.0))
        pos = Position(
            trade_id=holding["trade_id"],
            symbol=symbol,
            side="long",
            entry_price=holding["avg_entry_price"],
            qty=holding["qty"],
            stop_loss=sl,
            take_profit=tp,
            mark_price=price,
            opened_at_ms=holding["opened_at_ms"],
        )
        action: PolicyAction = self.policy.on_tick(pos)

        closed = []
        if action.action == "close_all":
            result = self.sell(symbol, price, exit_reason=action.reason)
            if result:
                self.policy.on_close(pos, action)
                closed.append(result)

        return closed

    def get_holdings(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Возвращает текущие открытые холдинги."""
        if symbol:
            h = self._holdings.get(symbol)
            return [h] if h else []
        return list(self._holdings.values())

    def get_stats(self) -> dict[str, Any]:
        """Статистика по всем сделкам из БД."""
        try:
            db = get_db()
            with db.connect() as conn:
                # Считаем только sell fills
                rows = conn.execute(
                    """
                    SELECT sf.exec_price, sf.exec_qty, so.price as entry_price
                    FROM spot_fills sf
                    JOIN spot_orders so ON so.order_link_id = sf.order_link_id
                    WHERE sf.side='Sell' AND sf.recorded_at_utc IS NOT NULL
                    ORDER BY sf.exec_time_ms DESC LIMIT 500
                    """,
                ).fetchall()
        except Exception:
            rows = []

        if not rows:
            return {"total": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0}

        wins = 0
        total_pnl = 0.0
        for row in rows:
            exit_p, qty, entry_p = float(row[0]), float(row[1]), float(row[2] or 0)
            if entry_p > 0:
                pnl = (exit_p - entry_p) * qty
                total_pnl += pnl
                if pnl > 0:
                    wins += 1

        total = len(rows)
        return {
            "total": total,
            "wins": wins,
            "win_rate": wins / total * 100 if total else 0.0,
            "total_pnl": total_pnl,
        }

    def get_balance(self) -> float:
        return self._balance

    # ── Internal ──────────────────────────────────────────────

    def _update_holding_pnl(self, symbol: str, price: float, holding: dict) -> None:
        """Обновляет unrealized_pnl в БД."""
        qty = holding["qty"]
        avg_entry = holding["avg_entry_price"]
        current_value = price * qty
        cost_basis = avg_entry * qty
        pnl = current_value - cost_basis
        pnl_pct = pnl / cost_basis if cost_basis > 0 else 0.0

        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE spot_holdings
                    SET current_price=?, current_value_usdt=?,
                        unrealized_pnl=?, unrealized_pnl_pct=?,
                        updated_at_utc=?
                    WHERE account_type=? AND symbol=? AND base_asset=?
                    """,
                    (price, current_value, pnl, pnl_pct, _utc_now(),
                     self.ACCOUNT_TYPE, symbol, holding["base_asset"]),
                )
        except Exception:
            pass

    def _load_holdings_from_db(self) -> None:
        """Загружает открытые холдинги при старте."""
        try:
            db = get_db()
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT symbol, base_asset, free_qty, avg_entry_price,
                           current_price, purchase_value_usdt, hold_reason, created_at_utc
                    FROM spot_holdings
                    WHERE account_type=?
                    """,
                    (self.ACCOUNT_TYPE,),
                ).fetchall()
        except Exception:
            rows = []

        for row in rows:
            sym, base, qty, avg_entry, cur_price, pv, reason, created = row
            opened_ms = _now_ms()  # approx
            self._holdings[sym] = {
                "trade_id": str(uuid.uuid4()),
                "symbol": sym,
                "base_asset": base,
                "qty": float(qty or 0),
                "avg_entry_price": float(avg_entry or 0),
                "current_price": float(cur_price or avg_entry or 0),
                "entry_fee": float(pv or 0) * SPOT_FEE_RATE,
                "purchase_value_usdt": float(pv or 0),
                "opened_at_ms": opened_ms,
                "entry_reason": reason or "",
            }
            log.info("Loaded holding %s qty=%.6f entry=%.4f", sym, qty, avg_entry)

        if self._holdings:
            log.info("SpotPaperEngine: загружено %d холдингов из БД", len(self._holdings))
