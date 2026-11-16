from uuid import UUID

from app.core.db import Database
from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.modules.extractions.extractor import InvoiceExtractor, invoice_to_json
from app.modules.extractions.models import Extraction, ExtractionStatus
from app.modules.extractions.repository import ExtractionRepository
from app.modules.extractions.schemas import ExtractionOut


class ExtractionsService:
    def __init__(
        self, db: Database, extractions: ExtractionRepository, extractor: InvoiceExtractor
    ) -> None:
        self._db = db
        self._extractions = extractions
        self._extractor = extractor

    async def run(self, document_id: UUID, text: str) -> ExtractionOut:
        """Extracts the invoice and stores the result. Valid or not, it goes to review."""
        outcome = await self._extractor.extract(text)
        extraction = Extraction(
            document_id=document_id,
            status=ExtractionStatus.PENDING_REVIEW if outcome.invoice else ExtractionStatus.FAILED,
            data=invoice_to_json(outcome.invoice) if outcome.invoice else None,
            attempts=outcome.attempts,
            first_errors=outcome.first_errors,
            final_errors=outcome.final_errors,
            raw_output=outcome.raw_output,
            provider=self._extractor.provider_name,
            model=outcome.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        )
        async with self._db.transaction() as session:
            saved = await self._extractions.add(session, extraction)
        return ExtractionOut.model_validate(saved)

    async def list(
        self, status: str | None, document_id: UUID | None, page: PageParams
    ) -> tuple[list[ExtractionOut], int]:
        filters = []
        if status:
            filters.append(Extraction.status == status)
        if document_id:
            filters.append(Extraction.document_id == document_id)
        async with self._db.transaction() as session:
            rows, total = await self._extractions.list(
                session,
                *filters,
                order_by=Extraction.created_at.desc(),
                offset=page.offset,
                limit=page.page_size,
            )
        return [ExtractionOut.model_validate(e) for e in rows], total

    async def get(self, extraction_id: UUID) -> ExtractionOut:
        async with self._db.transaction() as session:
            extraction = await self._extractions.get(session, extraction_id)
        if extraction is None:
            raise NotFoundError("Extraction")
        return ExtractionOut.model_validate(extraction)
