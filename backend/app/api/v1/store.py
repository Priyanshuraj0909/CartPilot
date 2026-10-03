"""Minimal read-only catalogue, inventory, and saved recommendation endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.models.merchant import Merchant
from app.schemas.store import MerchantSummary, CatalogSnapshot, CatalogProduct, SavedRecommendation
from app.services.store.catalog import get_catalog, get_saved_recommendations
from app.services.orchestration.context import ContextError

router = APIRouter(tags=["Merchant data"])


@router.get("/merchants", response_model=list[MerchantSummary])
async def merchants(session: AsyncSession = Depends(get_database_session)):
    with session.no_autoflush:
        return (await session.execute(select(Merchant).order_by(Merchant.id).limit(100))).scalars().all()


@router.get("/products", response_model=CatalogSnapshot)
async def products(merchant_id: int = Query(gt=0), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                   session: AsyncSession = Depends(get_database_session)) -> CatalogSnapshot:
    try:
        return await get_catalog(session, merchant_id, offset, limit)
    except ContextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/inventory", response_model=list[CatalogProduct])
async def inventory(merchant_id: int = Query(gt=0), session: AsyncSession = Depends(get_database_session)) -> list[CatalogProduct]:
    return (await products(merchant_id, 0, 100, session)).products


@router.get("/recommendations", response_model=list[SavedRecommendation])
async def recommendations(merchant_id: int = Query(gt=0), session: AsyncSession = Depends(get_database_session)) -> list[SavedRecommendation]:
    try:
        return await get_saved_recommendations(session, merchant_id)
    except ContextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
