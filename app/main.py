from fastapi import FastAPI

from app.container import Container, build_container
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.pagination import data_envelope
from app.modules.documents.routes import documents_router
from app.modules.extractions.routes import extractions_router
from app.modules.reviews.routes import reviews_router


def create_app(container: Container | None = None) -> FastAPI:
    configure_logging()
    c = container or build_container(get_settings())

    app = FastAPI(
        title="LLM document extraction",
        version="1.0.0",
        description="Extract invoice fields with an LLM, validate them, and review them.",
    )
    register_error_handlers(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        return data_envelope({"status": "ok"})

    app.include_router(documents_router(c.documents, c.require_api_key))
    app.include_router(extractions_router(c.extractions, c.require_api_key))
    app.include_router(reviews_router(c.reviews, c.require_api_key))
    return app
