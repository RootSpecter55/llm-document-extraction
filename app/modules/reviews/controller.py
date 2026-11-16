from typing import Any
from uuid import UUID

from app.core.pagination import PageParams, data_envelope, page_envelope
from app.modules.reviews.schemas import ApproveRequest, CorrectRequest
from app.modules.reviews.service import ReviewsService


class ReviewsController:
    def __init__(self, service: ReviewsService) -> None:
        self._service = service

    async def queue(self, page: PageParams) -> dict[str, Any]:
        items, total = await self._service.queue(page)
        return page_envelope([e.to_json() for e in items], total, page)

    async def approve(self, extraction_id: UUID, body: ApproveRequest) -> dict[str, Any]:
        review = await self._service.approve(extraction_id, body.reviewer)
        return data_envelope(review.to_json())

    async def correct(self, extraction_id: UUID, body: CorrectRequest) -> dict[str, Any]:
        review = await self._service.correct(extraction_id, body.reviewer, body.fields)
        return data_envelope(review.to_json())

    async def history(self, extraction_id: UUID | None, page: PageParams) -> dict[str, Any]:
        items, total = await self._service.history(extraction_id, page)
        return page_envelope([r.to_json() for r in items], total, page)

    async def get(self, review_id: UUID) -> dict[str, Any]:
        return data_envelope((await self._service.get(review_id)).to_json())
