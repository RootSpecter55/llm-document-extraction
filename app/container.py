from dataclasses import dataclass
from typing import Any

from app.core.auth import make_key_auth
from app.core.config import Settings
from app.core.db import Database, get_engine
from app.modules.documents.controller import DocumentsController
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.service import DocumentsService
from app.modules.extractions.controller import ExtractionsController
from app.modules.extractions.extractor import InvoiceExtractor
from app.modules.extractions.repository import ExtractionRepository
from app.modules.extractions.service import ExtractionsService
from app.modules.reviews.controller import ReviewsController
from app.modules.reviews.repository import ReviewRepository
from app.modules.reviews.service import ReviewsService
from app.providers.llm.base import LLMProvider
from app.providers.llm.factory import create_llm
from app.providers.storage.base import StorageProvider
from app.providers.storage.factory import create_storage


@dataclass
class Container:
    require_api_key: Any
    documents: DocumentsController
    extractions: ExtractionsController
    reviews: ReviewsController


def build_container(
    settings: Settings,
    *,
    llm: LLMProvider | None = None,
    storage: StorageProvider | None = None,
) -> Container:
    """Composition root: wires every repository, service and controller in one place.

    Providers come from their factories unless passed in (tests pass scripted LLMs).
    """
    db = Database(get_engine())
    extraction_repo = ExtractionRepository()

    extractions = ExtractionsService(
        db, extraction_repo, InvoiceExtractor(llm or create_llm(settings))
    )
    documents = DocumentsService(
        db,
        DocumentRepository(),
        storage or create_storage(settings),
        extractions,
        max_bytes=settings.max_upload_bytes,
        max_chars=settings.max_document_chars,
    )
    reviews = ReviewsService(db, ReviewRepository(), extraction_repo)

    return Container(
        require_api_key=make_key_auth(settings.api_key, "API key"),
        documents=DocumentsController(documents),
        extractions=ExtractionsController(extractions),
        reviews=ReviewsController(reviews),
    )
