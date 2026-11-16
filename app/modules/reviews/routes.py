from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.pagination import PageParams, page_params
from app.modules.reviews.controller import ReviewsController
from app.modules.reviews.schemas import ApproveRequest, CorrectRequest


def reviews_router(controller: ReviewsController, require_api_key: Callable[..., Any]) -> APIRouter:
    router = APIRouter(tags=["reviews"], dependencies=[Depends(require_api_key)])
    Page = Annotated[PageParams, Depends(page_params)]

    @router.get("/reviews/queue", summary="Extractions waiting for review, oldest first")
    async def queue(page: Page) -> dict[str, Any]:
        return await controller.queue(page)

    @router.post(
        "/extractions/{extraction_id}/approve",
        status_code=201,
        summary="Approve an extraction as correct",
    )
    async def approve(extraction_id: UUID, body: ApproveRequest) -> dict[str, Any]:
        return await controller.approve(extraction_id, body)

    @router.post(
        "/extractions/{extraction_id}/corrections",
        status_code=201,
        summary="Correct fields; the whole invoice is re-validated and the diff recorded",
    )
    async def correct(extraction_id: UUID, body: CorrectRequest) -> dict[str, Any]:
        return await controller.correct(extraction_id, body)

    @router.get("/reviews", summary="Review history, newest first")
    async def history(
        page: Page,
        extraction_id: Annotated[UUID | None, Query(alias="extractionId")] = None,
    ) -> dict[str, Any]:
        return await controller.history(extraction_id, page)

    @router.get("/reviews/{review_id}", summary="One review with its recorded changes")
    async def get(review_id: UUID) -> dict[str, Any]:
        return await controller.get(review_id)

    return router
