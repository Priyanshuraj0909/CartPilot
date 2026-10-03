"""Advisory endpoint; never launches or persists promotions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_database_session
from app.agents.pricing_agent import ProductNotFoundError
from app.agents.promotion_agent import PromotionAgent
from app.schemas.promotion import PromotionRecommendation, PromotionRequest
from app.services.orchestration.context import ContextError

router = APIRouter(prefix="/promotion", tags=["Promotion Agent"])


@router.post("/recommend", response_model=PromotionRecommendation, summary="Generate a promotion recommendation only")
async def recommend_promotion(request: PromotionRequest, session: AsyncSession = Depends(get_database_session)) -> PromotionRecommendation:
    try:
        return await PromotionAgent().analyze(request.product_id, session, merchant_id=request.merchant_id)
    except ProductNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ContextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Store data is temporarily unavailable; try again.") from exc
