from app.core.base_repository import BaseRepository
from app.modules.extractions.models import Extraction


class ExtractionRepository(BaseRepository[Extraction]):
    model = Extraction
