from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile

from app.core.pagination import PageParams, page_params
from app.modules.documents.controller import DocumentsController


def documents_router(
    controller: DocumentsController, require_api_key: Callable[..., Any]
) -> APIRouter:
    router = APIRouter(
        prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)]
    )

    @router.post("", status_code=201, summary="Upload a .txt or .pdf invoice; it is extracted")
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        return await controller.upload(file)

    @router.get("", summary="List documents, newest first")
    async def list_documents(page: Annotated[PageParams, Depends(page_params)]) -> dict[str, Any]:
        return await controller.list(page)

    @router.get("/{document_id}", summary="A document with the text that was extracted from it")
    async def get(document_id: UUID) -> dict[str, Any]:
        return await controller.get(document_id)

    @router.post("/{document_id}/extractions", status_code=201, summary="Run a new extraction")
    async def extract_again(document_id: UUID) -> dict[str, Any]:
        return await controller.extract_again(document_id)

    @router.delete("/{document_id}", status_code=204, summary="Delete a document and its data")
    async def delete(document_id: UUID) -> Response:
        await controller.delete(document_id)
        return Response(status_code=204)

    return router
