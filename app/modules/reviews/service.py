from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.modules.extractions.models import Extraction, ExtractionStatus
from app.modules.extractions.repository import ExtractionRepository
from app.modules.extractions.schemas import ExtractionOut
from app.modules.reviews.corrections import apply_corrections
from app.modules.reviews.models import Review
from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.schemas import ReviewOut

# Extractions waiting for a person: valid ones to check, failed ones to fill in.
NEEDS_REVIEW = (ExtractionStatus.PENDING_REVIEW, ExtractionStatus.FAILED)


class ReviewsService:
    def __init__(
        self, db: Database, reviews: ReviewRepository, extractions: ExtractionRepository
    ) -> None:
        self._db = db
        self._reviews = reviews
        self._extractions = extractions

    async def queue(self, page: PageParams) -> tuple[list[ExtractionOut], int]:
        """Extractions needing review, oldest first, so nothing waits forever."""
        async with self._db.transaction() as session:
            rows, total = await self._extractions.list(
                session,
                Extraction.status.in_(NEEDS_REVIEW),
                order_by=Extraction.created_at,
                offset=page.offset,
                limit=page.page_size,
            )
        return [ExtractionOut.model_validate(e) for e in rows], total

    async def approve(self, extraction_id: UUID, reviewer: str) -> ReviewOut:
        async with self._db.transaction() as session:
            extraction = await self._lock(session, extraction_id)
            if extraction.status != ExtractionStatus.PENDING_REVIEW:
                raise ConflictError(
                    "Only extractions pending review can be approved "
                    f"(this one is {extraction.status})"
                )
            extraction.status = ExtractionStatus.APPROVED
            review = await self._reviews.add(
                session,
                Review(
                    extraction_id=extraction.id, action="approve", reviewer=reviewer, changes={}
                ),
            )
        return ReviewOut.model_validate(review)

    async def correct(self, extraction_id: UUID, reviewer: str, fields: dict) -> ReviewOut:
        """Applies field corrections (re-validated as a whole invoice) and records the diff."""
        async with self._db.transaction() as session:
            extraction = await self._lock(session, extraction_id)
            if extraction.status not in NEEDS_REVIEW:
                raise ConflictError(f"This extraction was already reviewed ({extraction.status})")
            corrected, changes = apply_corrections(extraction.data, fields)
            extraction.data = corrected
            extraction.status = ExtractionStatus.CORRECTED
            review = await self._reviews.add(
                session,
                Review(
                    extraction_id=extraction.id,
                    action="correct",
                    reviewer=reviewer,
                    changes=changes,
                ),
            )
        return ReviewOut.model_validate(review)

    async def history(
        self, extraction_id: UUID | None, page: PageParams
    ) -> tuple[list[ReviewOut], int]:
        filters = [Review.extraction_id == extraction_id] if extraction_id else []
        async with self._db.transaction() as session:
            rows, total = await self._reviews.list(
                session,
                *filters,
                order_by=Review.created_at.desc(),
                offset=page.offset,
                limit=page.page_size,
            )
        return [ReviewOut.model_validate(r) for r in rows], total

    async def get(self, review_id: UUID) -> ReviewOut:
        async with self._db.transaction() as session:
            review = await self._reviews.get(session, review_id)
        if review is None:
            raise NotFoundError("Review")
        return ReviewOut.model_validate(review)

    async def _lock(self, session: AsyncSession, extraction_id: UUID) -> Extraction:
        extraction = await self._reviews.lock_extraction(session, extraction_id)
        if extraction is None:
            raise NotFoundError("Extraction")
        return extraction
