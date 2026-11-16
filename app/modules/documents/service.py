import asyncio
import re
import uuid
from uuid import UUID

from app.core.db import Database
from app.core.errors import AppError, BadRequestError, NotFoundError
from app.core.pagination import PageParams
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import DocumentDetail, DocumentOut, UploadResult
from app.modules.documents.text_extraction import read_text
from app.modules.extractions.schemas import ExtractionOut
from app.modules.extractions.service import ExtractionsService
from app.providers.storage.base import StorageProvider


def safe_filename(name: str) -> str:
    """Keeps letters, digits, dots, dashes and underscores; never a path."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:200] or "upload"


class DocumentsService:
    def __init__(
        self,
        db: Database,
        documents: DocumentRepository,
        storage: StorageProvider,
        extractions: ExtractionsService,
        *,
        max_bytes: int,
        max_chars: int,
    ) -> None:
        self._db = db
        self._documents = documents
        self._storage = storage
        self._extractions = extractions
        self._max_bytes = max_bytes
        self._max_chars = max_chars

    async def upload(self, filename: str, content_type: str, data: bytes) -> UploadResult:
        """Stores the file, reads its text and runs the first extraction."""
        if len(data) > self._max_bytes:
            raise AppError(413, "FILE_TOO_LARGE", f"Files are limited to {self._max_bytes} bytes")
        # PDF parsing is CPU work: keep it off the event loop.
        text, page_count = await asyncio.to_thread(read_text, filename, data)
        if not text:
            raise BadRequestError("EMPTY_DOCUMENT", "The file has no text")
        if len(text) > self._max_chars:
            # Rejected rather than silently cut: a truncated invoice could lose its totals.
            raise AppError(
                413, "DOCUMENT_TOO_LONG", f"Documents are limited to {self._max_chars} characters"
            )

        document_id = uuid.uuid4()
        name = safe_filename(filename)
        storage_key = f"{document_id}/{name}"
        await self._storage.put(storage_key, data, content_type)
        async with self._db.transaction() as session:
            document = await self._documents.add(
                session,
                Document(
                    id=document_id,
                    filename=name,
                    content_type=content_type,
                    size_bytes=len(data),
                    storage_key=storage_key,
                    text=text,
                    page_count=page_count,
                ),
            )

        extraction = await self._extractions.run(document_id, text)
        return UploadResult(document=DocumentOut.model_validate(document), extraction=extraction)

    async def extract_again(self, document_id: UUID) -> ExtractionOut:
        """Runs a new extraction for an existing document (e.g. after changing the model)."""
        document = await self._require(document_id)
        return await self._extractions.run(document.id, document.text)

    async def list(self, page: PageParams) -> tuple[list[DocumentOut], int]:
        async with self._db.transaction() as session:
            rows, total = await self._documents.list(
                session,
                order_by=Document.created_at.desc(),
                offset=page.offset,
                limit=page.page_size,
            )
        return [DocumentOut.model_validate(d) for d in rows], total

    async def get(self, document_id: UUID) -> DocumentDetail:
        return DocumentDetail.model_validate(await self._require(document_id))

    async def delete(self, document_id: UUID) -> None:
        """Deletes the document (its extractions and reviews cascade), then the stored file."""
        async with self._db.transaction() as session:
            document = await self._documents.get(session, document_id)
            if document is None:
                raise NotFoundError("Document")
            storage_key = document.storage_key
            await self._documents.delete(session, document)
        await self._storage.delete(storage_key)

    async def _require(self, document_id: UUID) -> Document:
        async with self._db.transaction() as session:
            document = await self._documents.get(session, document_id)
        if document is None:
            raise NotFoundError("Document")
        return document
