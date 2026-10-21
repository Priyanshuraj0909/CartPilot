"""Persistent worker for scheduled, read-only Shopify cache refreshes.

Run as a separate long-lived process (``python -m app.integrations.shopify.worker``).
Do not start this from a serverless request process: those processes are not durable.
"""
import asyncio
import logging

from app.core.config import settings
from app.core.database import AsyncSessionLocal, close_db_connection
from app.integrations.shopify.client import ShopifyClient
from app.integrations.shopify.schemas import SyncRequest
from app.integrations.shopify.sync import ShopifySyncService

logger = logging.getLogger("cartpilot.shopify_worker")


async def run_once(client: ShopifyClient | None = None) -> str:
    """Run one full sync and return its final status."""
    if not settings.SHOPIFY_STORE_DOMAIN or not settings.shopify_auth_configured or not settings.SHOPIFY_MERCHANT_ID:
        logger.warning("shopify_auto_sync_skipped reason=not_configured")
        return "skipped"

    try:
        async with AsyncSessionLocal() as session:
            result = await ShopifySyncService(client or ShopifyClient(settings)).sync(
                session,
                SyncRequest(merchant_id=settings.SHOPIFY_MERCHANT_ID),
            )
        logger.info(
            "shopify_auto_sync_finished status=%s products_created=%d products_updated=%d inventory_updated=%d orders_created=%d orders_updated=%d errors=%d",
            result.status,
            result.products_created,
            result.products_updated,
            result.inventory_updated,
            result.orders_created,
            result.orders_updated,
            len(result.errors),
        )
        return result.status
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Do not log exception text: upstream or storage errors can contain sensitive data.
        logger.error("shopify_auto_sync_failed exception_type=%s", type(exc).__name__)
        return "failed"


async def run_forever() -> None:
    """Refresh immediately at startup, then at the configured interval."""
    if not settings.SHOPIFY_AUTO_SYNC_ENABLED:
        logger.info("shopify_auto_sync_disabled")
        return

    logger.info(
        "shopify_auto_sync_started interval_seconds=%d merchant_id=%s",
        settings.SHOPIFY_AUTO_SYNC_INTERVAL_SECONDS,
        settings.SHOPIFY_MERCHANT_ID or "unconfigured",
    )
    client = None
    if settings.SHOPIFY_STORE_DOMAIN and settings.shopify_auth_configured and settings.SHOPIFY_MERCHANT_ID:
        client = ShopifyClient(settings)
    try:
        while True:
            await run_once(client)
            await asyncio.sleep(settings.SHOPIFY_AUTO_SYNC_INTERVAL_SECONDS)
    finally:
        await close_db_connection()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("shopify_auto_sync_stopped")


if __name__ == "__main__":
    main()
