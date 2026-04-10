import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from botik_app_service.contracts.logs import LogChannel, LogChannelSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.logs.manager import LogsManager

router = APIRouter(tags=["logs"], dependencies=[Depends(require_session_token)])


@router.get("/logs/channels", response_model=list[LogChannel])
async def list_log_channels(request: Request) -> list[LogChannel]:
    manager: LogsManager = request.app.state.logs_manager
    return manager.list_channels()


@router.get("/logs/{channel_id}", response_model=LogChannelSnapshot)
async def get_log_snapshot(channel_id: str, request: Request) -> LogChannelSnapshot:
    manager: LogsManager = request.app.state.logs_manager
    try:
        return manager.snapshot(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/logs/{channel_id}/stream")
async def stream_log_channel(channel_id: str, request: Request) -> StreamingResponse:
    manager: LogsManager = request.app.state.logs_manager

    try:
        manager.snapshot(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    async def event_generator():
        async for payload in manager.subscribe(channel_id):
            if await request.is_disconnected():
                break
            data = json.dumps(payload, ensure_ascii=True)
            yield f"event: log-entry\ndata: {data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
