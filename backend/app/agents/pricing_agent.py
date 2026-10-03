"""Pricing Agent implementation producing deterministic, guarded recommendations."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.pricing import PricingRecommendation
from app.services.pricing.calculator import calculate_pricing_recommendation
from app.services.pricing.signals import ProductPricingSignals, extract_pricing_signals

logger = logging.getLogger("cartpilot.agents.pricing")


class ProductNotFoundError(Exception):
    """Raised when the specified product ID cannot be located in the catalog."""

    def __init__(self, product_id: int):
        super().__init__(f"Product with ID {product_id} not found.")
        self.product_id = product_id


class PricingAgent:
    """Specialist agent responsible for evaluating pricing opportunities and proposing changes.

    OPERATING MODE: READ-ONLY RECOMMENDATIONS.
    This agent never mutates product selling prices, modifies inventory, or triggers external mutations.
    """

    def __init__(
        self,
        lookback_days: int = settings.PRICING_LOOKBACK_DAYS,
        max_increase_percent: float = settings.MAX_PRICE_INCREASE_PERCENT,
        max_decrease_percent: float = settings.MAX_PRICE_DECREASE_PERCENT,
        min_margin_percent: float = settings.MIN_MARGIN_PERCENT,
    ):
        self.lookback_days = lookback_days
        self.max_increase_percent = max_increase_percent
        self.max_decrease_percent = max_decrease_percent
        self.min_margin_percent = min_margin_percent

    async def analyze(
        self,
        product_id: int,
        session: AsyncSession,
    ) -> PricingRecommendation:
        """Extract multi-dimensional signals and calculate a deterministic pricing recommendation.

        Does not persist recommendations or alter product records.
        """
        logger.info("PricingAgent: Analyzing product ID %d...", product_id)
        signals = await extract_pricing_signals(
            product_id=product_id,
            session=session,
            lookback_days=self.lookback_days,
        )

        if signals is None:
            logger.warning("PricingAgent: Product ID %d not found.", product_id)
            raise ProductNotFoundError(product_id)

        recommendation = self.recommend(signals)

        logger.info(
            "PricingAgent: Produced recommendation for SKU '%s' (%s): curr=%.2f, rec=%.2f, conf=%.2f",
            signals.sku,
            signals.name,
            float(recommendation.current_price),
            float(recommendation.recommended_price),
            recommendation.confidence,
        )
        return recommendation


    def recommend(self, signals: ProductPricingSignals) -> PricingRecommendation:
        """Evaluate a preloaded snapshot without repeating database queries."""
        return calculate_pricing_recommendation(
            signals, self.max_increase_percent, self.max_decrease_percent, self.min_margin_percent,
        )
