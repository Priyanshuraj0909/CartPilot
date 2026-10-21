"""Atomic, database-backed limits shared by serverless instances and workers."""
import hashlib
import json
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_database_session
from app.core.config import settings
from app.models.auth_rate_limit import AuthRateLimit


async def record_attempt(
    session: AsyncSession, key: str, limit: int, now: int, window: int,
) -> int:
    """Return retry seconds when over budget; commit is owned by the caller."""
    dialect = session.get_bind().dialect.name
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert
    expired = AuthRateLimit.expires_at <= now
    statement = insert(AuthRateLimit).values(key=key, attempts=1, expires_at=now + window)
    statement = statement.on_conflict_do_update(
        index_elements=[AuthRateLimit.key],
        set_={
            "attempts": case(
                (expired, 1),
                (AuthRateLimit.attempts <= limit, AuthRateLimit.attempts + 1),
                else_=AuthRateLimit.attempts,
            ),
            "expires_at": case((expired, now + window), else_=AuthRateLimit.expires_at),
        },
    ).returning(AuthRateLimit.attempts, AuthRateLimit.expires_at)
    attempts, expires_at = (await session.execute(statement)).one()
    return max(1, expires_at - now) if attempts > limit else 0


async def limit_auth_attempts(
    request: Request, session: AsyncSession = Depends(get_database_session),
) -> None:
    """Limit auth writes, including schema-invalid requests, before password hashing.

    Forwarded headers are deliberately ignored. Configure trusted proxy handling at
    the ASGI server/provider; clients must not be able to choose their peer identity.
    """
    now = int(time.time())
    route = request.url.path
    peer = request.client.host if request.client else "unknown"
    identities = [(f"peer:{route}:{peer}", settings.AUTH_RATE_LIMIT_PEER_ATTEMPTS)]
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    if isinstance(body, dict):
        identity = body.get("store_name" if route.endswith("recover-email") else "email")
        if isinstance(identity, str) and identity.strip():
            identities.append((f"identity:{route}:{identity.strip().casefold()}", settings.AUTH_RATE_LIMIT_IDENTITY_ATTEMPTS))
    retry_after = 0
    for identity, limit in identities:
        key = hashlib.sha256(identity.encode()).hexdigest()
        retry_after = max(retry_after, await record_attempt(
            session, key, limit, now, settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        ))
    # Remove long-expired counters without extending any active lockout.
    await session.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at < now - 86400))
    await session.commit()
    if retry_after:
        raise HTTPException(
            429, "Too many account attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )
