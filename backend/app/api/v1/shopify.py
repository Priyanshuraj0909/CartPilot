"""Merchant-bound read-only connection checks and local cache synchronization."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.api.v1.actions import local_only
from app.core.config import settings
from app.models.shopify import ShopifyConnection
from app.integrations.shopify.client import ShopifyClient, ShopifyError
from app.integrations.shopify.schemas import ConnectionStatus, SyncRequest, ShopifySyncResult
from app.integrations.shopify.sync import ShopifySyncService, require_binding

router = APIRouter(prefix='/integrations/shopify', tags=['Shopify read-only'])


def build_client() -> ShopifyClient:
    return ShopifyClient(settings)


async def summary(session: AsyncSession, merchant_id: int):
    record = await session.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant_id))
    return record.last_sync if record else None


@router.get('/status', response_model=ConnectionStatus, dependencies=[Depends(local_only)])
async def status(merchant_id: int = Query(gt=0), session: AsyncSession = Depends(get_database_session)):
    configured = bool(settings.SHOPIFY_STORE_DOMAIN and settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()
                      and settings.SHOPIFY_MERCHANT_ID == merchant_id)
    result = ConnectionStatus(configured=configured, connected=False, api_version=settings.SHOPIFY_API_VERSION,
                              message='Shopify is not configured for this merchant. Local/demo data remains available.')
    if not configured:
        return result
    try:
        await require_binding(session, settings, merchant_id)
        record = await session.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant_id))
        if record and record.store_domain != settings.SHOPIFY_STORE_DOMAIN:
            raise ShopifyError('store_binding', 'This merchant is bound to a different Shopify store. Use a separate merchant.', 409)
        result.last_sync = record.last_sync if record else None
        shop = await build_client().connection()
        result.connected = True
        result.store = shop['domain']
        result.currency = shop['currency']
        result.message = 'Connected. Shopify is the source; CartPilot is a local analysis cache.'
    except ShopifyError as exc:
        result.message = str(exc)
    except SQLAlchemyError:
        await session.rollback()
        raise HTTPException(503, 'Integration metadata is temporarily unavailable.') from None
    return result


@router.get('/last-sync', response_model=ShopifySyncResult | None, dependencies=[Depends(local_only)])
async def last_sync(merchant_id: int = Query(gt=0), session: AsyncSession = Depends(get_database_session)):
    try:
        await require_binding(session, settings, merchant_id)
        return await summary(session, merchant_id)
    except ShopifyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except SQLAlchemyError:
        await session.rollback()
        raise HTTPException(503, 'Integration metadata is temporarily unavailable.') from None


@router.post('/sync', response_model=ShopifySyncResult, dependencies=[Depends(local_only)])
async def sync(request: SyncRequest, session: AsyncSession = Depends(get_database_session)):
    try:
        return await ShopifySyncService(build_client()).sync(session, request)
    except ShopifyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except SQLAlchemyError:
        await session.rollback()
        raise HTTPException(503, 'Integration metadata is temporarily unavailable. Review last sync before retrying.') from None
