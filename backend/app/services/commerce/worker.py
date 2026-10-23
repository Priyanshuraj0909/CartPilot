"""Persistent opt-in ranking/insight worker. No payment or LLM mutation authority."""
import asyncio
import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.commerce_workflows import CommerceRules
from app.services.commerce.merchandising import run_cycle

logger = logging.getLogger(__name__)


async def tick() -> list[dict]:
    async with AsyncSessionLocal() as session:
        ids = list((await session.scalars(select(CommerceRules.merchant_id).where(
            CommerceRules.scheduler_enabled.is_(True)).order_by(CommerceRules.merchant_id).limit(100))).all())
    results = []
    for merchant_id in ids:
        async with AsyncSessionLocal() as session:
            try:
                results.append(await run_cycle(session, merchant_id, scheduled=True))
            except Exception as exc:
                await session.rollback()
                results.append({"merchant_id": merchant_id, "error_type": type(exc).__name__})
    return results


async def main() -> None:
    while True:
        try:
            await tick()
        except Exception as exc:
            logger.warning("commerce_worker_tick_failed type=%s", type(exc).__name__)
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
