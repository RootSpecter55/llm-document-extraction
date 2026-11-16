from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiModel


class ApproveRequest(ApiModel):
    reviewer: str = Field(min_length=1, max_length=100)


class CorrectRequest(ApiModel):
    reviewer: str = Field(min_length=1, max_length=100)
    # Only the fields being changed; snake_case invoice field names, e.g. {"total": 125.5}.
    fields: dict[str, Any] = Field(min_length=1)


class ReviewOut(ApiModel):
    id: UUID
    extraction_id: UUID
    action: str
    reviewer: str
    changes: dict[str, Any]
    created_at: datetime
