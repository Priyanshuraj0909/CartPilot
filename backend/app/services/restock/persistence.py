"""Explicit persistence service; saving a proposal never executes a restock."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.restock_agent import RestockAgent
from app.agents.pricing_agent import ProductNotFoundError
from app.models.product import Product
from app.models.recommendation import Recommendation, RecommendationStatus
from app.schemas.restock import RestockRecommendation


async def generate_and_persist_recommendation(
    product_id: int, session: AsyncSession, agent_run_id: int | None = None,
) -> RestockRecommendation:
    """Stage a pending restock proposal; caller owns commit and rollback."""
    result = await RestockAgent().analyze(product_id, session)
    product = await session.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    session.add(Recommendation(
        merchant_id=product.merchant_id, product_id=product_id, agent_run_id=agent_run_id,
        recommendation_type="restock", title=f"Restock review for {product.name}",
        description=result.reason, recommended_value=result.model_dump(mode="json"),
        confidence=result.confidence, status=RecommendationStatus.PENDING.value,
    ))
    await session.flush()
    return result
