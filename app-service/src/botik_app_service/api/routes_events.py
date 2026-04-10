from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from botik_app_service.infra.session import require_session_token
from botik_app_service.jobs.event_publisher import EventPublisher

router = APIRouter(tags=["events"], dependencies=[Depends(require_session_token)])


@router.get("/events")
async def stream_events(request: Request) -> StreamingResponse:
    publisher: EventPublisher = request.app.state.event_publisher

    async def event_generator():
        async for payload in publisher.subscribe():
            if await request.is_disconnected():
                break
            yield EventPublisher.encode_sse(payload)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
