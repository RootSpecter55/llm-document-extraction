from collections.abc import Callable
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.pagination import PageParams, page_params
from app.modules.extractions.controller import ExtractionsController

Status = Literal["pending_review", "failed", "approved", "corrected"]


def extractions_router(
    controller: ExtractionsController, require_api_key: Callable[..., Any]
) -> APIRouter:
    router = APIRouter(
        prefix="/extractions", tags=["extractions"], dependencies=[Depends(require_api_key)]
    )

    @router.get("", summary="List extractions, newest first")
    async def list_extractions(
        page: Annotated[PageParams, Depends(page_params)],
        status: Status | None = None,
        document_id: Annotated[UUID | None, Query(alias="documentId")] = None,
    ) -> dict[str, Any]:
        return await controller.list(status, document_id, page)

    @router.get("/{extraction_id}", summary="One extraction with its data and any errors")
    async def get(extraction_id: UUID) -> dict[str, Any]:
        return await controller.get(extraction_id)

    return router
