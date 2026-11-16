from typing import Any
from uuid import UUID

from app.core.pagination import PageParams, data_envelope, page_envelope
from app.modules.extractions.service import ExtractionsService


class ExtractionsController:
    def __init__(self, service: ExtractionsService) -> None:
        self._service = service

    async def list(
        self, status: str | None, document_id: UUID | None, page: PageParams
    ) -> dict[str, Any]:
        items, total = await self._service.list(status, document_id, page)
        return page_envelope([e.to_json() for e in items], total, page)

    async def get(self, extraction_id: UUID) -> dict[str, Any]:
        return data_envelope((await self._service.get(extraction_id)).to_json())
