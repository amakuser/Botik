from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = Field(default=None)
