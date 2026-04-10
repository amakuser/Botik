from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.bootstrap import AppSessionInfo, BootstrapPayload, UiCapabilities
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapPayload, dependencies=[Depends(require_session_token)])
async def get_bootstrap(request: Request) -> BootstrapPayload:
    settings = request.app.state.settings
    base_url = f"http://{settings.host}:{settings.port}"
    routes = ["/", "/jobs", "/logs"]
    return BootstrapPayload(
        app_name=settings.app_name,
        version=settings.version,
        session=AppSessionInfo(
            session_id=settings.session_token,
            transport_base_url=base_url,
            events_url=f"{base_url}/events",
        ),
        capabilities=UiCapabilities(
            desktop=settings.desktop_mode,
            jobs=True,
            routes=routes,
        ),
        routes=routes,
    )
