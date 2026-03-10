from __future__ import annotations

import asyncio
import logging

from src.botik.main import run_reconciliation_scheduled_if_due, run_reconciliation_startup


class _ReconStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, *, trigger_source: str) -> dict:
        self.calls.append(str(trigger_source))
        return {"trigger_source": trigger_source, "status": "success"}


def test_runtime_reconciliation_autostart_and_scheduled_wiring() -> None:
    log = logging.getLogger("test.reconciliation.wiring")
    svc = _ReconStub()

    last_ts, summary = asyncio.run(run_reconciliation_startup(svc, log=log))
    assert last_ts > 0
    assert summary is not None
    assert svc.calls == ["startup"]

    # interval not reached -> no scheduled call
    last_ts_after, summary_after = asyncio.run(
        run_reconciliation_scheduled_if_due(
            svc,
            last_run_ts=last_ts,
            interval_sec=9999.0,
            log=log,
        )
    )
    assert last_ts_after == last_ts
    assert summary_after is None
    assert svc.calls == ["startup"]

    # interval reached -> scheduled call happens
    last_ts_after2, summary_after2 = asyncio.run(
        run_reconciliation_scheduled_if_due(
            svc,
            last_run_ts=0.0,
            interval_sec=1.0,
            log=log,
        )
    )
    assert last_ts_after2 > 0
    assert summary_after2 is not None
    assert svc.calls == ["startup", "scheduled"]


def test_runtime_reconciliation_helpers_handle_missing_service() -> None:
    log = logging.getLogger("test.reconciliation.none")

    last_ts, summary = asyncio.run(run_reconciliation_startup(None, log=log))
    assert last_ts == 0.0
    assert summary is None

    last_ts2, summary2 = asyncio.run(
        run_reconciliation_scheduled_if_due(
            None,
            last_run_ts=123.0,
            interval_sec=10.0,
            log=log,
        )
    )
    assert last_ts2 == 123.0
    assert summary2 is None
