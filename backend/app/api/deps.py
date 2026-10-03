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

async def require_product_scope(session: AsyncSession, product_id: int, merchant_id: int | None) -> None:
    """Validate optional MVP merchant scope before reading business analytics."""
    from fastapi import HTTPException
    from app.models.product import Product
    if merchant_id is None:
        return  # Legacy single-product calls remain supported; this is not authentication.
    with session.no_autoflush:
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found.")
        if product.merchant_id != merchant_id:
            raise HTTPException(403, "Product does not belong to the selected merchant.")
