"""
SimpleExitPolicy — базовая политика выхода по SL/TP и таймауту.

Логика:
  - SL hit → close_all (reason='sl_hit')
  - TP hit → close_all (reason='tp_hit')
  - hold_timeout_ms истёк → close_all (reason='timeout')
  - иначе → hold

Это первая и обязательная политика. Следующие (PartialExit, Averaging, Hedge)
добавляются поверх без изменения этого файла.
"""
from __future__ import annotations

import time

from src.botik.position.base_policy import BasePositionPolicy, PolicyAction, Position, HOLD


class SimpleExitPolicy(BasePositionPolicy):
    """
    SL/TP + таймаут. Самая простая и надёжная политика.

    Параметры:
      hold_timeout_ms  — принудительное закрытие через N мс (0 = выключено)
    """

    def __init__(self, hold_timeout_ms: int = 0) -> None:
        self.hold_timeout_ms = hold_timeout_ms

    def on_tick(self, position: Position) -> PolicyAction:
        price = position.mark_price
        sl = position.stop_loss
        tp = position.take_profit
        side = position.side

        # ── SL check ──────────────────────────────────────────
        if side == "long" and price <= sl:
            return PolicyAction(action="close_all", reason="sl_hit")
        if side == "short" and price >= sl:
            return PolicyAction(action="close_all", reason="sl_hit")

        # ── TP check ──────────────────────────────────────────
        if side == "long" and price >= tp:
            return PolicyAction(action="close_all", reason="tp_hit")
        if side == "short" and price <= tp:
            return PolicyAction(action="close_all", reason="tp_hit")

        # ── Timeout check ─────────────────────────────────────
        if self.hold_timeout_ms > 0:
            elapsed = int(time.time() * 1000) - position.opened_at_ms
            if elapsed >= self.hold_timeout_ms:
                return PolicyAction(action="close_all", reason="timeout")

        return HOLD
