from typing import Any
from uuid import UUID

from fastapi import UploadFile

from app.core.pagination import PageParams, data_envelope, page_envelope
from app.modules.documents.service import DocumentsService


class DocumentsController:
    def __init__(self, service: DocumentsService) -> None:
        self._service = service

    async def upload(self, file: UploadFile) -> dict[str, Any]:
        data = await file.read()
        result = await self._service.upload(
            file.filename or "upload.txt", file.content_type or "application/octet-stream", data
        )
        return data_envelope(result.to_json())

    async def extract_again(self, document_id: UUID) -> dict[str, Any]:
        return data_envelope((await self._service.extract_again(document_id)).to_json())

    async def list(self, page: PageParams) -> dict[str, Any]:
        items, total = await self._service.list(page)
        return page_envelope([d.to_json() for d in items], total, page)

    async def get(self, document_id: UUID) -> dict[str, Any]:
        return data_envelope((await self._service.get(document_id)).to_json())

    async def delete(self, document_id: UUID) -> None:
        await self._service.delete(document_id)
