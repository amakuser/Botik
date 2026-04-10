from pydantic import BaseModel


class AppSessionInfo(BaseModel):
    session_id: str
    transport_base_url: str
    events_url: str


class UiCapabilities(BaseModel):
    desktop: bool
    jobs: bool
    routes: list[str]


class BootstrapPayload(BaseModel):
    app_name: str
    version: str
    session: AppSessionInfo
    capabilities: UiCapabilities
    routes: list[str]
