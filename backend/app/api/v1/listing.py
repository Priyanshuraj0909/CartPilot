"""Recommendation-only listing API; no product writes or automatic persistence."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_database_session
from app.agents.pricing_agent import ProductNotFoundError
from app.agents.listing_agent import ListingAgent, ListingOwnershipError
from app.schemas.listing import ListingRecommendation, ListingRequest

router = APIRouter(prefix="/listing", tags=["Listing Agent"])


@router.post("/recommend", response_model=ListingRecommendation,
             summary="Recommend grounded listing improvements without publication")
async def recommend_listing(request: ListingRequest, session: AsyncSession = Depends(get_database_session)) -> ListingRecommendation:
    try:
        return await ListingAgent().analyze(request.product_id, session, request.merchant_id)
    except ProductNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ListingOwnershipError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Product listing data is invalid or cannot satisfy configured content bounds.") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Store data is temporarily unavailable; try again.") from exc
