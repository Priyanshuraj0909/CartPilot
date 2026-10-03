"""Independently callable, read-only Restock Agent."""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.pricing_agent import ProductNotFoundError
from app.schemas.restock import RestockPolicy, RestockRecommendation
from app.services.restock.signals import RestockSignals, extract_restock_signals
from app.services.restock.calculator import calculate_restock_recommendation


class RestockAgent:
    """Return replenishment advice without inventory writes or purchase orders."""
    def __init__(self, policy: RestockPolicy | None = None) -> None:
        self.policy = policy or RestockPolicy()

    async def analyze(
        self, product_id: int, session: AsyncSession, as_of: datetime | None = None,
    ) -> RestockRecommendation:
        signals = await extract_restock_signals(product_id, session, self.policy.lookback_days, as_of)
        if signals is None:
            raise ProductNotFoundError(product_id)
        return self.recommend(signals)

    def recommend(self, signals: RestockSignals) -> RestockRecommendation:
        """Evaluate a preloaded snapshot without database writes or repeat reads."""
        return calculate_restock_recommendation(signals, self.policy)
