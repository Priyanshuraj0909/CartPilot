"""Per-cart SHA-256 chain. Detects edits; not an externally anchored immutable ledger."""
import hashlib
import json
import time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.commerce import CommerceEvent, ShoppingCart

GENESIS = "0" * 64


def digest(cart_id: str, sequence: int, event: str, payload: dict, created_at: int, previous_hash: str) -> str:
    canonical = json.dumps(dict(cart_id=cart_id, sequence=sequence, event=event, payload=payload,
        created_at=created_at, previous_hash=previous_hash), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def events(session: AsyncSession, cart_id: str) -> list[CommerceEvent]:
    return list((await session.scalars(select(CommerceEvent).where(CommerceEvent.cart_id == cart_id)
        .order_by(CommerceEvent.sequence))).all())


async def append(session: AsyncSession, cart: ShoppingCart, event: str, payload: dict) -> None:
    history = await events(session, cart.id)
    sequence = len(history) + 1
    previous = history[-1].digest if history else GENESIS
    timestamp = int(time.time())
    session.add(CommerceEvent(cart_id=cart.id, sequence=sequence, event=event, payload=payload,
        created_at=timestamp, previous_hash=previous,
        digest=digest(cart.id, sequence, event, payload, timestamp, previous)))
    await session.flush()


def verify(history: list[CommerceEvent]) -> bool:
    previous = GENESIS
    for index, row in enumerate(history, 1):
        if row.sequence != index or row.previous_hash != previous or row.digest != digest(
            row.cart_id, row.sequence, row.event, row.payload, row.created_at, previous):
            return False
        previous = row.digest
    return bool(history)
