"""Redis caching and async connection management."""

import logging
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Obtain or initialize the global Redis async client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def check_redis_connection() -> bool:
    """Ping Redis to verify connectivity."""
    try:
        client = get_redis_client()
        result = await client.ping()
        return bool(result)
    except Exception as exc:
        logger.warning("Redis connectivity check failed: %s", exc)
        return False


async def close_redis_connection() -> None:
    """Close the global Redis client connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
