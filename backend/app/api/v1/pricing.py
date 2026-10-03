"""Pricing API endpoints for generating and retrieving pricing recommendations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pricing_agent import PricingAgent, ProductNotFoundError
from app.api.deps import get_database_session, require_product_scope
from app.schemas.pricing import PricingRecommendation, PricingRequest

router = APIRouter(prefix="/pricing", tags=["Pricing Agent"])

# Singleton pricing agent instance configured with application defaults
pricing_agent = PricingAgent()


@router.post(
    "/recommend",
    response_model=PricingRecommendation,
    status_code=status.HTTP_200_OK,
    summary="Generate a structured pricing recommendation for a product",
    description=(
        "Analyzes product inventory, cost, sales velocity, and historical trends "
        "to generate a guarded, deterministic pricing recommendation. "
        "NOTE: This endpoint operates strictly in recommendation-only mode and "
        "does NOT mutate the product's actual catalog price."
    ),
)
async def generate_pricing_recommendation(
    request: PricingRequest,
    session: AsyncSession = Depends(get_database_session),
) -> PricingRecommendation:
    """Generate pricing recommendation for the requested product ID."""
    try:
        await require_product_scope(session, request.product_id, request.merchant_id)
        recommendation = await pricing_agent.analyze(
            product_id=request.product_id,
            session=session,
        )
        return recommendation
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
