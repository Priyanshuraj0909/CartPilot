"""Explicit persistence service; saving a proposal never executes a listing."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.listing_agent import ListingAgent
from app.agents.pricing_agent import ProductNotFoundError
from app.models.product import Product
from app.models.recommendation import Recommendation, RecommendationStatus
from app.schemas.listing import ListingRecommendation


async def generate_and_persist_recommendation(
    product_id: int, session: AsyncSession, agent_run_id: int | None = None,
) -> ListingRecommendation:
    """Stage a pending listing proposal; caller owns commit and rollback."""
    result = await ListingAgent().analyze(product_id, session)
    product = await session.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    session.add(Recommendation(
        merchant_id=product.merchant_id, product_id=product_id, agent_run_id=agent_run_id,
        recommendation_type="listing", title=f"Listing review for {product.name}",
        description=result.reason, recommended_value=result.model_dump(mode="json"),
        confidence=result.confidence, status=RecommendationStatus.PENDING.value,
    ))
    await session.flush()
    return result
