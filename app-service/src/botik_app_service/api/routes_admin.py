import os
import signal
import threading
import time

from fastapi import APIRouter, Depends, Request

from botik_app_service.infra.session import require_session_token

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_session_token)])


def _delayed_sigterm(delay_seconds: float) -> None:
    time.sleep(delay_seconds)
    os.kill(os.getpid(), signal.SIGTERM)


@router.post("/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    await request.app.state.job_manager.shutdown()
    request.app.state.event_publisher.stop()
    threading.Thread(target=_delayed_sigterm, args=(0.25,), daemon=True).start()
    return {"status": "shutting_down"}
