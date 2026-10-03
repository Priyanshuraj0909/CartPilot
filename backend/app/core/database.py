"""Database connectivity and async session management."""

import logging
import asyncio
from typing import AsyncGenerator
from sqlalchemy import text, event
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    hide_parameters=True,
    future=True,
    pool_pre_ping=True,
    # Serverless processes should not retain idle connections across invocations.
    **({"poolclass": NullPool} if settings.DATABASE_POOL_MODE == "null" else {}),
)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Verify database connectivity with a lightweight probe."""
    try:
        async with asyncio.timeout(3):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed type=%s", type(exc).__name__)
        return False


async def close_db_connection() -> None:
    """Dispose of the database connection pool cleanly."""
    await engine.dispose()
