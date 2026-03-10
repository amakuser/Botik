from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.botik.main import verify_futures_protection_from_exchange
from src.botik.risk.futures_rules import transition_protection_status


@dataclass
class _PositionsStub:
    ret_code: int
    ret_msg: str
    stop_loss: float
    take_profit: float

    async def get_positions(self, symbol: str | None = None) -> dict:
        if self.ret_code != 0:
            return {"retCode": self.ret_code, "retMsg": self.ret_msg, "result": {"list": []}}
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": str(symbol or "BTCUSDT"),
                        "side": "Buy",
                        "positionIdx": 0,
                        "size": "0.1",
                        "stopLoss": str(self.stop_loss),
                        "takeProfit": str(self.take_profit),
                        "trailingStop": "0",
                    }
                ]
            },
        }


def test_verify_futures_protection_and_transition_state_machine() -> None:
    protected_status, _ = asyncio.run(
        verify_futures_protection_from_exchange(
            _PositionsStub(ret_code=0, ret_msg="OK", stop_loss=62000.0, take_profit=65000.0),
            symbol="BTCUSDT",
            side="Buy",
            position_idx=0,
        )
    )
    assert protected_status == "protected"

    unprotected_status, _ = asyncio.run(
        verify_futures_protection_from_exchange(
            _PositionsStub(ret_code=0, ret_msg="OK", stop_loss=0.0, take_profit=65000.0),
            symbol="BTCUSDT",
            side="Buy",
            position_idx=0,
        )
    )
    assert unprotected_status == "unprotected"

    failed_status, _ = asyncio.run(
        verify_futures_protection_from_exchange(
            _PositionsStub(ret_code=-2, ret_msg="unsupported", stop_loss=0.0, take_profit=0.0),
            symbol="BTCUSDT",
            side="Buy",
            position_idx=0,
        )
    )
    assert failed_status == "failed"

    assert (
        transition_protection_status(
            current_status="pending",
            apply_attempted=True,
            apply_success=True,
            verify_status="protected",
        )
        == "protected"
    )
    assert (
        transition_protection_status(
            current_status="pending",
            apply_attempted=True,
            apply_success=True,
            verify_status="unprotected",
        )
        == "unprotected"
    )
    assert (
        transition_protection_status(
            current_status="repairing",
            apply_attempted=True,
            apply_success=True,
            verify_status="unprotected",
        )
        == "failed"
    )
    assert (
        transition_protection_status(
            current_status="repairing",
            apply_attempted=True,
            apply_success=True,
            verify_status="protected",
        )
        == "protected"
    )
