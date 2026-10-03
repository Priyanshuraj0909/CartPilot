"""Pytest configuration and shared fixtures for backend testing."""

import os
# Set safe process configuration before importing the application; no developer services.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["SHOPIFY_STORE_DOMAIN"] = ""
os.environ["SHOPIFY_ACCESS_TOKEN"] = ""
os.environ.pop("SHOPIFY_MERCHANT_ID", None)

from typing import AsyncGenerator
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy import event
from app.core.seed import seed_database
from app.main import app
from app.models.base import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh in-memory SQLite database session with all tables created."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """Provide an in-memory database session populated with mock catalog and order data."""
    await seed_database(db_session)
    return db_session

@pytest.fixture(autouse=True)
def isolated_health(monkeypatch):
    async def unavailable(): return False
    monkeypatch.setattr("app.api.v1.health.check_db_connection", unavailable)
    monkeypatch.setattr("app.api.v1.health.check_redis_connection", unavailable)
