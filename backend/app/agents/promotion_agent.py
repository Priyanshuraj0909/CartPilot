"""Independently callable recommendation-only Promotion Agent."""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.pricing_agent import ProductNotFoundError
from app.schemas.promotion import PromotionPolicy, PromotionRecommendation
from app.services.pricing.signals import extract_pricing_signals
from app.services.promotion.signals import PromotionSignals, enrich_promotion_signals
from app.services.promotion.calculator import calculate_promotion_recommendation
from app.services.orchestration.context import ContextError


class PromotionAgent:
    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self.policy = policy or PromotionPolicy()

    async def analyze(self, product_id: int, session: AsyncSession, as_of: datetime | None = None,
                      merchant_id: int | None = None) -> PromotionRecommendation:
        as_of = as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            raise ValueError("Snapshot time must include a timezone.")
        with session.no_autoflush:
            snapshot = await extract_pricing_signals(product_id, session, self.policy.lookback_days, as_of)
            if snapshot is None:
                raise ProductNotFoundError(product_id)
            if merchant_id is not None and snapshot.merchant_id != merchant_id:
                raise ContextError(403, "Product does not belong to the merchant.")
            signals = await enrich_promotion_signals(snapshot, session, as_of)
        return self.recommend(signals)

    def recommend(self, signals: PromotionSignals) -> PromotionRecommendation:
        if not isinstance(signals, PromotionSignals):
            raise ValueError("Validated promotion inventory context is required.")
        return calculate_promotion_recommendation(signals, self.policy)
