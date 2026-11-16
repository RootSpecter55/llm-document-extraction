import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import get_engine
from app.main import create_app

API = {"Authorization": f"Bearer {os.environ['API_KEY']}"}


async def _create_database_if_missing() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    base, db_name = url.rsplit("/", 1)
    connection = await asyncpg.connect(f"{base}/postgres")
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    """Creates the test database if needed and applies migrations once per session."""
    await _create_database_if_missing()
    await asyncio.to_thread(
        subprocess.run,
        ["alembic", "upgrade", "head"],
        check=True,
        capture_output=True,
        env=os.environ,
    )
    yield
    await get_engine().dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> None:
    """Every test starts empty. Deleting documents cascades to extractions and reviews."""
    async with get_engine().begin() as connection:
        await connection.execute(text("TRUNCATE documents CASCADE"))


@pytest.fixture(scope="session")
def app() -> Any:
    return create_app()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def upload(
    client: AsyncClient, content: bytes, filename: str = "invoice.txt"
) -> dict[str, Any]:
    """Uploads a file and returns {"document": ..., "extraction": ...}."""
    response = await client.post(
        "/documents",
        headers=API,
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]
