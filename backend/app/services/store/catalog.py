"""Expose existing inventory and analytics without merchant writes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.models.product import Product
from app.models.merchant import Merchant
from app.models.order import Order, OrderStatus
from app.models.recommendation import Recommendation
from app.schemas.store import CatalogProduct, CatalogSnapshot, SavedRecommendation
from app.schemas.product import ProductDetailResponse
from app.schemas.pricing import PricingRecommendation
from app.schemas.listing import ListingRecommendation
from app.schemas.promotion import PromotionRecommendation
from app.schemas.restock import RestockRecommendation
from app.services.pricing.signals import extract_pricing_signals
from app.services.restock.signals import restock_signals_from_snapshot
from app.services.restock.calculator import calculate_restock_recommendation
from app.services.orchestration.context import ContextError


async def require_merchant(session: AsyncSession, merchant_id: int) -> None:
    if await session.get(Merchant, merchant_id) is None:
        raise ContextError(404, "Merchant not found.")


async def get_catalog(session: AsyncSession, merchant_id: int, offset: int = 0, limit: int = 100) -> CatalogSnapshot:
    now = datetime.now(timezone.utc)
    with session.no_autoflush:
        await require_merchant(session, merchant_id)
        total = await session.scalar(select(func.count(Product.id)).where(Product.merchant_id == merchant_id))
        rows = (await session.execute(select(Product).where(Product.merchant_id == merchant_id)
            .options(selectinload(Product.inventory), selectinload(Product.price_history))
            .order_by(Product.id).offset(offset).limit(limit))).scalars().all()
        products = []
        for product in rows:
            signals = await extract_pricing_signals(product.id, session, settings.RESTOCK_LOOKBACK_DAYS, now, preloaded_product=product)
            if signals is None:
                continue
            status = "Missing"
            days = None
            stockout = None
            if signals.has_inventory:
                try:
                    restock = calculate_restock_recommendation(restock_signals_from_snapshot(signals))
                    days, stockout = restock.estimated_days_remaining, restock.stockout_risk
                    status = "Out of Stock" if signals.available_quantity == 0 else "Critical" if stockout else "Low Stock" if signals.is_low_stock else "Healthy"
                except ValueError:
                    status = "Invalid"
            products.append(CatalogProduct(**ProductDetailResponse.model_validate(product).model_dump(),
                sales_velocity=signals.sales_velocity, recent_units=signals.units_sold_lookback,
                days_remaining=days, stockout_risk=stockout, inventory_status=status))
        recent_orders, revenue = (await session.execute(select(func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .where(Order.merchant_id == merchant_id, Order.status != OrderStatus.CANCELLED.value,
                   Order.ordered_at >= now - timedelta(days=settings.RESTOCK_LOOKBACK_DAYS), Order.ordered_at <= now))).one()
    return CatalogSnapshot(products=products, total_products=total or 0,
        low_stock_products=sum(p.inventory_status in ("Low Stock", "Critical", "Out of Stock") for p in products),
        potential_stockouts=sum(p.stockout_risk is True for p in products),
        available_units=sum(p.inventory.available_quantity for p in products if p.inventory and p.inventory_status != "Invalid"),
        recent_orders=recent_orders, revenue=Decimal(str(revenue)), lookback_days=settings.RESTOCK_LOOKBACK_DAYS,
        as_of=now, has_more=offset + len(rows) < (total or 0))


async def get_saved_recommendations(session: AsyncSession, merchant_id: int) -> list[SavedRecommendation]:
    with session.no_autoflush:
        await require_merchant(session, merchant_id)
        rows = (await session.execute(select(Recommendation, Product.name)
            .outerjoin(Product, (Product.id == Recommendation.product_id) & (Product.merchant_id == merchant_id))
            .where(Recommendation.merchant_id == merchant_id, or_(Recommendation.product_id.is_(None), Product.id.is_not(None))).order_by(Recommendation.created_at.desc(), Recommendation.id.desc()).limit(200))).all()
    results = []
    for record, name in rows:
        payload = None
        try:
            if record.recommended_value and record.recommendation_type == "pricing":
                payload = PricingRecommendation.model_validate(record.recommended_value)
            elif record.recommended_value and record.recommendation_type == "restock":
                payload = RestockRecommendation.model_validate(record.recommended_value)
            elif record.recommended_value and record.recommendation_type == "promotion":
                payload = PromotionRecommendation.model_validate(record.recommended_value)
            elif record.recommended_value and record.recommendation_type == "listing":
                payload = ListingRecommendation.model_validate(record.recommended_value)
        except ValueError:
            pass  # Legacy/untyped proposals still appear with their recorded title/status.
        results.append(SavedRecommendation(id=record.id, product_id=record.product_id,
            product_name=name, agent=record.recommendation_type, title=record.title,
            description=record.description, confidence=record.confidence, risk_level=payload.risk_level if payload else None,
            status=record.status, created_at=record.created_at, payload=payload))
    return results
