import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(500))
    # The text the extraction worked from (for PDFs: the text layer pypdf found).
    text: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
