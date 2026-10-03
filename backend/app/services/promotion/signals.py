"""Promotion context reuses sales aggregation and validated inventory analytics."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.schemas.promotion import PromotionPolicy
from app.schemas.restock import RestockPolicy, RestockRecommendation
from app.services.pricing.signals import ProductPricingSignals, extract_pricing_signals, calculate_sales_velocity
from app.services.restock.signals import restock_signals_from_snapshot
from app.services.restock.calculator import calculate_restock_recommendation


@dataclass(frozen=True)
class PromotionSignals:
    product: ProductPricingSignals
    recent_units: int
    previous_units: int
    recent_days: int
    previous_days: int
    history_days: float
    restock: RestockRecommendation


async def enrich_promotion_signals(product: ProductPricingSignals, session: AsyncSession,
                                   as_of: datetime, restock_snapshot: ProductPricingSignals | None = None) -> PromotionSignals:
    recent_days = product.lookback_days // 2
    previous_days = product.lookback_days - recent_days
    boundary = as_of - timedelta(days=recent_days)
    # Shared aggregation covers both intervals; count the newer half using identical scope/status rules.
    units = await session.scalar(select(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.product_id == product.product_id, Order.merchant_id == product.merchant_id,
               Order.status != OrderStatus.CANCELLED.value, Order.ordered_at > boundary, Order.ordered_at <= as_of))
    created = await session.scalar(select(Product.created_at).where(Product.id == product.product_id))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    restock_snapshot = restock_snapshot or await extract_pricing_signals(product.product_id, session, RestockPolicy().lookback_days, as_of)
    restock = calculate_restock_recommendation(restock_signals_from_snapshot(restock_snapshot))
    return PromotionSignals(product, int(units), product.units_sold_lookback - int(units), recent_days,
                            previous_days, max(0, (as_of - created).total_seconds() / 86400), restock)


def sales_trend(signals: PromotionSignals, policy: PromotionPolicy) -> str:
    if signals.history_days < policy.lookback_days or signals.product.total_historical_orders == 0:
        return "insufficient_data"
    recent = calculate_sales_velocity(signals.recent_units, signals.recent_days)
    previous = calculate_sales_velocity(signals.previous_units, signals.previous_days)
    if previous == 0:
        return "increasing" if recent > 0 else "stable"
    delta = (recent - previous) / previous * 100
    return "declining" if delta < -policy.trend_change_percent else "increasing" if delta > policy.trend_change_percent else "stable"
