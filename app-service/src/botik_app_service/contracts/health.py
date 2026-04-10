from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    session_id: str
