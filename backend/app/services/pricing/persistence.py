"""Explicit application service for saving pending proposals; never executes them."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.pricing_agent import PricingAgent, ProductNotFoundError
from app.models.product import Product
from app.models.recommendation import Recommendation, RecommendationStatus
from app.schemas.pricing import PricingRecommendation


async def generate_and_persist_recommendation(
    product_id: int, session: AsyncSession, agent_run_id: int | None = None,
) -> PricingRecommendation:
    """Stage a pending recommendation. The caller owns commit/rollback."""
    recommendation = await PricingAgent().analyze(product_id, session)
    product = await session.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    session.add(Recommendation(
        agent_run_id=agent_run_id, merchant_id=product.merchant_id,
        product_id=product_id, recommendation_type="pricing",
        title=f"Price adjustment for {product.name}", description=recommendation.reason,
        recommended_value=recommendation.model_dump(mode="json"),
        confidence=recommendation.confidence, status=RecommendationStatus.PENDING.value,
    ))
    await session.flush()
    return recommendation
