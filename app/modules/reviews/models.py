import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Review(Base):
    """One reviewer decision. `changes` maps each corrected field to {"from": ..., "to": ...}."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(20))  # "approve" or "correct"
    reviewer: Mapped[str] = mapped_column(String(100))
    changes: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
