"""Independently callable Listing Agent; never updates or publishes products."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.pricing_agent import ProductNotFoundError
from app.schemas.listing import ListingPolicy, ListingRecommendation
from app.services.listing.signals import ListingSignals, extract_listing_signals
from app.services.listing.generator import generate_listing_recommendation


class ListingOwnershipError(ValueError):
    """Optional merchant scope does not own the requested listing."""


class ListingAgent:
    def __init__(self, policy: ListingPolicy | None = None) -> None:
        self.policy = policy or ListingPolicy()

    async def analyze(self, product_id: int, session: AsyncSession,
                      merchant_id: int | None = None) -> ListingRecommendation:
        with session.no_autoflush:
            signals = await extract_listing_signals(product_id, session)
        if signals is None:
            raise ProductNotFoundError(product_id)
        if merchant_id is not None and signals.merchant_id != merchant_id:
            raise ListingOwnershipError("Product does not belong to the merchant.")
        return self.recommend(signals)

    def recommend(self, signals: ListingSignals) -> ListingRecommendation:
        return generate_listing_recommendation(signals, self.policy)
