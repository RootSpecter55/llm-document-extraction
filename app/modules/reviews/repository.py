from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.modules.extractions.models import Extraction
from app.modules.reviews.models import Review


class ReviewRepository(BaseRepository[Review]):
    model = Review

    async def lock_extraction(
        self, session: AsyncSession, extraction_id: UUID
    ) -> Extraction | None:
        """The extraction, row-locked so two reviewers cannot decide on it at the same time."""
        return await session.scalar(
            select(Extraction).where(Extraction.id == extraction_id).with_for_update()
        )
