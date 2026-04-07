"""
FuturesPaperEngine — paper-движок для фьючерсной торговли.

Хранит открытые позиции в БД (futures_positions).
На каждом тике вызывает PositionPolicy.on_tick() и выполняет действие.
При закрытии записывает в futures_paper_trades.

Интерфейс намеренно похож на BybitRestClient чтобы в будущем
легко переключиться на реальный исполнитель.
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

log = logging.getLogger("botik.execution.futures_paper")

VIRTUAL_BALANCE_USDT = 10_000.0   # виртуальный баланс для paper


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_utc_to_ms(utc_str: str | None) -> int:
    """Конвертирует строку UTC '2026-03-21T12:00:00Z' в unix-ms. Fallback → now."""
    if not utc_str:
        return _now_ms()
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return _now_ms()


class FuturesPaperEngine:
    """
    Paper-движок фьючерсных позиций с персистентностью в БД.

    Жизненный цикл позиции:
      open_position() → запись в futures_positions (status='open')
      on_price_tick() → policy.on_tick() → если close → close_position()
      close_position() → обновить futures_positions + INSERT futures_paper_trades

    Слоты для расширения политик:
      policy можно передать снаружи — SimpleExitPolicy, PartialExitPolicy и т.д.
    """

    def __init__(
        self,
        policy: BasePositionPolicy | None = None,
        account_type: str = "PAPER",
        model_scope: str = "futures",
    ) -> None:
        self.policy = policy or SimpleExitPolicy(hold_timeout_ms=4 * 60 * 60 * 1000)  # 4ч таймаут
        self.account_type = account_type
        self.model_scope = model_scope
        self._balance = VIRTUAL_BALANCE_USDT

    # ── Public API ────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        side: str,                  # 'long' | 'short'
        entry_price: float,
        qty: float,
        stop_loss: float,
        take_profit: float,
        strategy_owner: str = "futures_spike_reversal",
        spike_direction: int = 0,
        spike_strength_bps: float = 0.0,
        impulse_bps: float = 0.0,
        entry_reason: str = "",
        model_version: str | None = None,
    ) -> str:
        """Открывает позицию. Возвращает trade_id."""
        trade_id = f"paper-{uuid.uuid4().hex[:12]}"
        now = _utc_now()

        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO futures_positions
                      (account_type, symbol, side, size, entry_price, mark_price,
                       leverage, unrealised_pnl, protection_status, strategy_owner,
                       updated_at_utc, created_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_type, symbol, side)
                    DO UPDATE SET
                      size=excluded.size, entry_price=excluded.entry_price,
                      mark_price=excluded.mark_price, unrealised_pnl=0,
                      strategy_owner=excluded.strategy_owner,
                      updated_at_utc=excluded.updated_at_utc
                    """,
                    (self.account_type, symbol, side, qty, entry_price, entry_price,
                     1.0, 0.0, "protected", strategy_owner, now, now),
                )
                # Храним trade_id и SL/TP в extra через futures_paper_trades (статус open)
                conn.execute(
                    """
                    INSERT INTO futures_paper_trades
                      (trade_id, symbol, side, entry_price, qty,
                       spike_direction, spike_strength_bps, impulse_bps,
                       entry_reason, model_scope, model_version,
                       opened_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (trade_id, symbol, side, entry_price, qty,
                     spike_direction, spike_strength_bps, impulse_bps,
                     entry_reason, self.model_scope, model_version, now),
                )
        except Exception as exc:
            log.error("open_position DB error: %s", exc)
            return ""

        log.info(
            "OPEN %s %s %s qty=%.6f entry=%.4f SL=%.4f TP=%.4f",
            trade_id[:8], symbol, side.upper(), qty, entry_price, stop_loss, take_profit,
        )
        send_alert(
            f"🟢 <b>ОТКРЫТА</b> {symbol} {side.upper()} [paper]\n"
            f"Вход: <b>${entry_price:,.4f}</b> | Кол-во: {qty:.6f}\n"
            f"SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f}"
        )
        return trade_id

    def on_price_tick(
        self,
        symbol: str,
        mark_price: float,
    ) -> list[dict[str, Any]]:
        """
        Вызывается на каждом тике с новой ценой.
        Возвращает список закрытых сделок (обычно пустой).
        """
        positions = self._load_open_positions(symbol)
        closed: list[dict[str, Any]] = []

        for row in positions:
            trade_id = row["trade_id"]
            sl = float(row.get("sl") or 0)
            tp = float(row.get("tp") or 0)

            # BUG-1 fix: берём opened_at_ms из БД, иначе timeout никогда не сработает
            row_opened_ms = _parse_utc_to_ms(row.get("opened_at_utc"))

            pos = Position(
                trade_id=trade_id,
                symbol=symbol,
                side=row["side"],
                entry_price=float(row["entry_price"]),
                qty=float(row["qty"]),
                stop_loss=sl,
                take_profit=tp,
                mark_price=mark_price,
                opened_at_ms=row_opened_ms,
            )

            self.policy.on_open(pos)
            action = self.policy.on_tick(pos)

            # Обновляем unrealized_pnl в futures_positions
            self._update_mark_price(symbol, pos.side, mark_price, pos.unrealized_pnl)

            if action.action in ("close_all", "close_partial"):
                qty_to_close = pos.qty if action.action == "close_all" else pos.qty * action.qty_pct
                result = self.close_position(
                    trade_id=trade_id,
                    symbol=symbol,
                    side=pos.side,
                    exit_price=mark_price,
                    qty_closed=qty_to_close,
                    exit_reason=action.reason,
                    entry_price=pos.entry_price,
                    qty_total=pos.qty,
                )
                self.policy.on_close(pos, action)
                closed.append(result)

        return closed

    def close_position(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        exit_price: float,
        qty_closed: float,
        exit_reason: str,
        entry_price: float,
        qty_total: float,
        opened_at_ms: int | None = None,
    ) -> dict[str, Any]:
        """Закрывает позицию, пишет итог в futures_paper_trades."""
        now = _utc_now()

        if side == "long":
            gross_pnl = (exit_price - entry_price) * qty_closed
        else:
            gross_pnl = (entry_price - exit_price) * qty_closed

        # Комиссия: 0.055% taker (bybit linear)
        fee = exit_price * qty_closed * 0.00055
        net_pnl = gross_pnl - fee
        was_profitable = 1 if net_pnl > 0 else 0

        hold_ms = None
        if opened_at_ms:
            hold_ms = _now_ms() - opened_at_ms

        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE futures_paper_trades SET
                      exit_price=?, gross_pnl=?, net_pnl=?,
                      hold_time_ms=?, exit_reason=?, was_profitable=?,
                      closed_at_utc=?
                    WHERE trade_id=?
                    """,
                    (exit_price, gross_pnl, net_pnl,
                     hold_ms, exit_reason, was_profitable, now, trade_id),
                )
                conn.execute(
                    """
                    UPDATE futures_positions SET size=0, unrealised_pnl=0,
                      updated_at_utc=?
                    WHERE account_type=? AND symbol=? AND side=?
                    """,
                    (now, self.account_type, symbol, side),
                )
        except Exception as exc:
            log.error("close_position DB error: %s", exc)

        log.info(
            "CLOSE %s %s %s exit=%.4f pnl=%.4f (%s)",
            trade_id[:8], symbol, side.upper(), exit_price, net_pnl, exit_reason,
        )
        pnl_sign = "+" if net_pnl >= 0 else ""
        pnl_pct = (net_pnl / (entry_price * qty_closed) * 100) if entry_price and qty_closed else 0.0
        send_alert(
            f"{'🔴' if net_pnl < 0 else '🟡'} <b>ЗАКРЫТА</b> {symbol} {side.upper()} [paper]\n"
            f"Выход: <b>${exit_price:,.4f}</b> | PnL: <b>{pnl_sign}{net_pnl:.2f} USDT ({pnl_sign}{pnl_pct:.1f}%)</b>\n"
            f"Причина: {exit_reason}"
        )
        return {
            "trade_id": trade_id, "symbol": symbol, "side": side,
            "exit_price": exit_price, "net_pnl": net_pnl,
            "exit_reason": exit_reason, "was_profitable": was_profitable,
        }

    def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Возвращает список открытых позиций из БД."""
        try:
            db = get_db()
            with db.connect() as conn:
                if symbol:
                    rows = conn.execute(
                        "SELECT * FROM futures_paper_trades "
                        "WHERE symbol=? AND closed_at_utc IS NULL",
                        (symbol,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM futures_paper_trades WHERE closed_at_utc IS NULL"
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log.error("get_open_positions error: %s", exc)
            return []

    def get_stats(self) -> dict[str, Any]:
        """Статистика paper-торговли из БД."""
        try:
            db = get_db()
            with db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) total,
                           SUM(CASE WHEN was_profitable=1 THEN 1 ELSE 0 END) wins,
                           SUM(net_pnl) total_pnl,
                           AVG(net_pnl) avg_pnl
                    FROM futures_paper_trades
                    WHERE closed_at_utc IS NOT NULL AND model_scope=?
                    """,
                    (self.model_scope,),
                ).fetchone()
            if not row or not row[0]:
                return {"total": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0}
            total = int(row[0] or 0)
            wins = int(row[1] or 0)
            return {
                "total": total,
                "wins": wins,
                "win_rate": round(wins / total * 100, 1) if total else 0.0,
                "total_pnl": round(float(row[3] or 0), 4),
                "avg_pnl": round(float(row[4] or 0), 4),
            }
        except Exception as exc:
            log.error("get_stats error: %s", exc)
            return {}

    # ── Internal ──────────────────────────────────────────────

    def _load_open_positions(self, symbol: str) -> list[dict[str, Any]]:
        """Загружает незакрытые позиции из futures_paper_trades."""
        try:
            db = get_db()
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT fpt.trade_id, fpt.symbol, fpt.side,
                           fpt.entry_price, fpt.qty, fpt.opened_at_utc,
                           fp.unrealised_pnl,
                           fpo.sl_price AS sl, fpo.tp_price AS tp
                    FROM futures_paper_trades fpt
                    LEFT JOIN futures_positions fp
                      ON fp.account_type=? AND fp.symbol=fpt.symbol AND fp.side=fpt.side
                    LEFT JOIN futures_protection_orders fpo
                      ON fpo.symbol=fpt.symbol AND fpo.side=fpt.side
                    WHERE fpt.symbol=? AND fpt.closed_at_utc IS NULL
                    """,
                    (self.account_type, symbol),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log.error("_load_open_positions error: %s", exc)
            return []

    def _update_mark_price(self, symbol: str, side: str,
                           mark_price: float, unrealized_pnl: float) -> None:
        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE futures_positions SET mark_price=?, unrealised_pnl=?,
                      updated_at_utc=?
                    WHERE account_type=? AND symbol=? AND side=?
                    """,
                    (mark_price, unrealized_pnl, _utc_now(),
                     self.account_type, symbol, side),
                )
        except Exception:
            pass

    def _save_protection(self, symbol: str, side: str,
                         sl: float, tp: float) -> None:
        """Записывает/обновляет SL/TP в futures_protection_orders (UPSERT по symbol+side)."""
        now = _utc_now()
        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO futures_protection_orders
                      (symbol, side, sl_price, tp_price, status, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, 'protected', ?, ?)
                    ON CONFLICT(symbol, side) DO UPDATE SET
                      sl_price=excluded.sl_price,
                      tp_price=excluded.tp_price,
                      updated_at_utc=excluded.updated_at_utc
                    """,
                    (symbol, side, sl, tp, now, now),
                )
        except Exception as exc:
            log.debug("_save_protection skipped: %s", exc)
