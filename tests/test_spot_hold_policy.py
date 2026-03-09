from __future__ import annotations

from src.botik.risk.spot_rules import can_auto_sell_hold


def test_spot_hold_policy_blocks_recovered_without_explicit_permission() -> None:
    assert can_auto_sell_hold(hold_reason="unknown_recovered_from_exchange", auto_sell_allowed=False) is False
    assert can_auto_sell_hold(hold_reason="manual_import", auto_sell_allowed=False) is False
    assert can_auto_sell_hold(hold_reason="strategy_entry", auto_sell_allowed=False) is True
    assert can_auto_sell_hold(hold_reason="unknown_recovered_from_exchange", auto_sell_allowed=True) is True
