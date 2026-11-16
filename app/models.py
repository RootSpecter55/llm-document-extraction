"""Imports every ORM model so Base.metadata is complete (Alembic and tests use this)."""

from app.core.db import Base
from app.modules.documents.models import Document
from app.modules.extractions.models import Extraction
from app.modules.reviews.models import Review

__all__ = ["Base", "Document", "Extraction", "Review"]
