"""Merchant ownership preflight and shared, time-bounded business context."""
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.promotion.signals import PromotionSignals, enrich_promotion_signals
from app.services.listing.signals import ListingSignals, extract_listing_signals
from app.models.merchant import Merchant
from app.models.product import Product
from app.schemas.orchestration import AgentName, OrchestrationRequest
from app.services.pricing.signals import ProductPricingSignals, extract_pricing_signals


class ContextError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ProductContext:
    product_id: int
    signals: dict[AgentName, ProductPricingSignals | PromotionSignals | ListingSignals]


@dataclass(frozen=True)
class BusinessContext:
    request: OrchestrationRequest
    products: tuple[ProductContext, ...]
    selected_agents: tuple[AgentName, ...]
    as_of: datetime


async def build_context(
    request: OrchestrationRequest, selected_agents: tuple[AgentName, ...],
    session: AsyncSession, as_of: datetime | None = None,
) -> BusinessContext:
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ContextError(422, "Snapshot time must include a timezone.")
    # No implicit flushing of caller-owned merchant changes during read-only analysis.
    with session.no_autoflush:
        if await session.get(Merchant, request.merchant_id) is None:
            raise ContextError(404, "Merchant not found.")
        rows = (await session.execute(select(Product.id, Product.merchant_id).where(Product.id.in_(request.product_ids)))).all()
        ownership = dict(rows)
        # Validate the entire scope before gathering any merchant business data.
        if any(owner != request.merchant_id for owner in ownership.values()):
            raise ContextError(403, "Requested product does not belong to the merchant.")
        missing = sorted(set(request.product_ids) - ownership.keys())
        if missing:
            raise ContextError(404, f"Products not found: {missing}.")
        products = []
        lookbacks = {AgentName.PRICING: settings.PRICING_LOOKBACK_DAYS,
                     AgentName.RESTOCK: settings.RESTOCK_LOOKBACK_DAYS,
                     AgentName.PROMOTION: settings.PROMOTION_LOOKBACK_DAYS}
        for product_id in request.product_ids:
            cache: dict[int, ProductPricingSignals] = {}
            signals_by_agent = {}
            for name in selected_agents:
                if name == AgentName.LISTING:
                    listing = await extract_listing_signals(product_id, session)
                    if listing is None:
                        raise ContextError(404, f"Product {product_id} no longer exists.")
                    if listing.merchant_id != request.merchant_id:
                        raise ContextError(403, "Product ownership changed during analysis.")
                    signals_by_agent[name] = listing
                    continue
                window = lookbacks[name]
                if window not in cache:
                    signals = await extract_pricing_signals(product_id, session, window, as_of)
                    if signals is None:
                        raise ContextError(404, f"Product {product_id} no longer exists.")
                    if signals.merchant_id != request.merchant_id:
                        raise ContextError(403, "Product ownership changed during analysis.")
                    cache[window] = signals
                if name == AgentName.PROMOTION:
                    restock_window = settings.RESTOCK_LOOKBACK_DAYS
                    if restock_window not in cache:
                        restock_snapshot = await extract_pricing_signals(product_id, session, restock_window, as_of)
                        if restock_snapshot is None:
                            raise ContextError(404, f"Product {product_id} no longer exists.")
                        if restock_snapshot.merchant_id != request.merchant_id:
                            raise ContextError(403, "Product ownership changed during analysis.")
                        cache[restock_window] = restock_snapshot
                    # Input failures belong to the specialist, preserving successful analyses.
                    try:
                        signals_by_agent[name] = await enrich_promotion_signals(cache[window], session, as_of, cache[restock_window])
                    except ValueError:
                        signals_by_agent[name] = cache[window]
                else:
                    signals_by_agent[name] = cache[window]
            products.append(ProductContext(product_id, signals_by_agent))
    return BusinessContext(request, tuple(products), selected_agents, as_of)
