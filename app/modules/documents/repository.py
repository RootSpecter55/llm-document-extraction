from app.core.base_repository import BaseRepository
from app.modules.documents.models import Document


class DocumentRepository(BaseRepository[Document]):
    model = Document
