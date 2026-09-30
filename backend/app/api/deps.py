"""FastAPI dependencies for database and caching access."""

from typing import AsyncGenerator
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.redis import get_redis_client


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining an async SQLAlchemy session."""
    async for session in get_db():
        yield session


def get_redis() -> aioredis.Redis:
    """Dependency for obtaining the Redis client."""
    return get_redis_client()
