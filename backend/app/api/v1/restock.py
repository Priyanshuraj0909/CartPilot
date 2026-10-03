"""Advisory restock endpoint; never persists or executes proposals."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.pricing_agent import ProductNotFoundError
from app.agents.restock_agent import RestockAgent
from app.api.deps import get_database_session, require_product_scope
from app.schemas.restock import RestockRecommendation, RestockRequest

router = APIRouter(prefix="/restock", tags=["Restock Agent"])
restock_agent = RestockAgent()


@router.post("/recommend", response_model=RestockRecommendation,
             summary="Generate advisory replenishment recommendation",
             description="Recommendation only: no inventory changes or purchase orders.")
async def recommend_restock(
    request: RestockRequest, session: AsyncSession = Depends(get_database_session),
) -> RestockRecommendation:
    try:
        await require_product_scope(session, request.product_id, request.merchant_id)
        return await restock_agent.analyze(request.product_id, session)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
