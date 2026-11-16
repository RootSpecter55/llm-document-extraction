from datetime import datetime
from uuid import UUID

from app.core.schemas import ApiModel
from app.modules.extractions.schemas import ExtractionOut


class DocumentOut(ApiModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    text: str


class UploadResult(ApiModel):
    document: DocumentOut
    extraction: ExtractionOut
