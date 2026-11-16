from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.schemas import ApiModel


class ExtractionOut(ApiModel):
    id: UUID
    document_id: UUID
    status: str
    data: dict[str, Any] | None
    attempts: int
    first_errors: list[dict[str, str]] | None
    final_errors: list[dict[str, str]] | None
    raw_output: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    created_at: datetime
    updated_at: datetime
