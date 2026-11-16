import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExtractionStatus(StrEnum):
    PENDING_REVIEW = "pending_review"  # valid output, waiting for a reviewer
    FAILED = "failed"  # still invalid after the retry; a reviewer must supply the data
    APPROVED = "approved"
    CORRECTED = "corrected"


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (Index("ix_extractions_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    # The validated invoice (JSON-safe: decimals and dates as strings), or null if it failed.
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempts: Mapped[int]
    first_errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    final_errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    raw_output: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
