"""Extraction and aggregation of multi-dimensional pricing signals."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.price_history import PriceHistory
from app.models.product import Product

# Documented policy thresholds; adjust here to tune signal classification.
STRONG_SALES_UNITS_PER_DAY = 1.0
STRONG_SALES_LOOKBACK_UNITS = 10
WEAK_SALES_UNITS_PER_DAY = 0.25
WEAK_SALES_LOOKBACK_UNITS = 2
MAX_HEALTHY_INVENTORY_DAYS = 45.0
SURPLUS_REORDER_MULTIPLIER = 1.5
MIN_HISTORY_ORDERS = 3
MIN_RECENT_UNITS = 3


@dataclass(frozen=True)
class ProductPricingSignals:
    """Aggregated quantitative and categorical signals for pricing evaluation."""

    product_id: int
    merchant_id: int
    sku: str
    name: str
    category: str
    cost_price: Decimal | None
    current_price: Decimal
    status: str

    # Inventory signals
    total_quantity: int
    reserved_quantity: int
    available_quantity: int
    reorder_point: int
    reorder_quantity: int
    is_low_stock: bool
    days_of_inventory: float

    # Sales signals (within lookback period)
    units_sold_lookback: int
    orders_count_lookback: int
    revenue_lookback: Decimal
    sales_velocity: float  # Units sold per day
    lookback_days: int

    # Historical context
    total_historical_orders: int
    historical_price_changes_count: int
    has_sufficient_data: bool
    has_inventory: bool = True
    unavailable_quantity: int = 0

    @property
    def is_strong_sales(self) -> bool:
        """Strong sales signal: velocity >= 1.0 unit/day or >= 10 units in lookback."""
        return self.sales_velocity >= STRONG_SALES_UNITS_PER_DAY or self.units_sold_lookback >= STRONG_SALES_LOOKBACK_UNITS

    @property
    def is_weak_sales(self) -> bool:
        """Weak sales signal: velocity < 0.25 units/day despite having data history."""
        return self.has_sufficient_data and (self.sales_velocity < WEAK_SALES_UNITS_PER_DAY or self.units_sold_lookback <= WEAK_SALES_LOOKBACK_UNITS)

    @property
    def is_healthy_inventory(self) -> bool:
        """Stock is above reorder point and holding duration is reasonable (<= 45 days)."""
        if self.is_low_stock:
            return False
        return self.days_of_inventory <= MAX_HEALTHY_INVENTORY_DAYS

    @property
    def is_high_inventory(self) -> bool:
        """Surplus stock: Available units exceed replenishment ceiling or supply exceeds 45 days."""
        surplus_threshold = self.reorder_point + (self.reorder_quantity * SURPLUS_REORDER_MULTIPLIER)
        return self.available_quantity > surplus_threshold or self.days_of_inventory > MAX_HEALTHY_INVENTORY_DAYS


async def extract_pricing_signals(
    product_id: int,
    session: AsyncSession,
    lookback_days: int = 14,
    as_of: Optional[datetime] = None,
    *, preloaded_product: Product | None = None,
) -> Optional[ProductPricingSignals]:
    """Retrieve product, inventory, and sales records to assemble deterministic signals."""
    with session.no_autoflush:
        if lookback_days <= 0:
            raise ValueError("Lookback days must be positive.")
        as_of = as_of or datetime.now(timezone.utc)
        # 1. Fetch Product with Inventory
        if preloaded_product is not None:
            if preloaded_product.id != product_id:
                raise ValueError("Preloaded product does not match requested identity.")
            product = preloaded_product
        else:
            stmt = (
                select(Product)
                .options(selectinload(Product.inventory))
                .where(Product.id == product_id)
            )
            res = await session.execute(stmt)
            product = res.scalar_one_or_none()

        if product is None:
            return None

        # 2. Extract Inventory Attributes
        inv = product.inventory
        total_qty = inv.quantity if inv else 0
        reserved_qty = inv.reserved_quantity if inv else 0
        avail_qty = inv.available_quantity if inv else 0
        reorder_pt = inv.reorder_point if inv else 0
        reorder_qty = inv.reorder_quantity if inv else 0
        is_low = avail_qty <= reorder_pt

        # 3. Aggregate Sales within Lookback Window
        cutoff_dt = as_of - timedelta(days=lookback_days)
        sales_stmt = (
            select(
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
                func.count(func.distinct(Order.id)).label("orders_count"),
                func.coalesce(func.sum(OrderItem.subtotal), Decimal("0.00")).label("revenue"),
            )
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                OrderItem.product_id == product_id,
                Order.ordered_at >= cutoff_dt,
                Order.ordered_at <= as_of,
                Order.merchant_id == product.merchant_id,
                Order.status != OrderStatus.CANCELLED.value,
            )
        )
        sales_res = await session.execute(sales_stmt)
        units_sold, orders_count, revenue = sales_res.one()

        # Sales velocity calculation: units per day
        sales_velocity = calculate_sales_velocity(int(units_sold), lookback_days)

        # Days of inventory estimate
        if sales_velocity > 0:
            days_of_inventory = round(float(avail_qty) / sales_velocity, 1)
        else:
            days_of_inventory = 999.0 if avail_qty > 0 else 0.0

        # 4. Total Lifetime Order History (to verify data sufficiency)
        lifetime_stmt = (
            select(func.count(func.distinct(Order.id)))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                OrderItem.product_id == product_id,
                Order.ordered_at <= as_of,
                Order.merchant_id == product.merchant_id,
                Order.status != OrderStatus.CANCELLED.value,
            )
        )
        lifetime_res = await session.execute(lifetime_stmt)
        total_lifetime_orders = lifetime_res.scalar_one()

        # 5. Price History Event Count
        ph_stmt = select(func.count(PriceHistory.id)).where(PriceHistory.product_id == product_id, PriceHistory.changed_at <= as_of)
        ph_res = await session.execute(ph_stmt)
        price_changes_count = ph_res.scalar_one()

        # Data sufficiency criteria
        has_sufficient_data = total_lifetime_orders >= MIN_HISTORY_ORDERS or units_sold >= MIN_RECENT_UNITS

        return ProductPricingSignals(
            product_id=product.id,
            merchant_id=product.merchant_id,
            sku=product.sku,
            name=product.name,
            category=product.category,
            cost_price=product.cost_price,
            current_price=product.selling_price,
            status=product.status,
            total_quantity=total_qty,
            reserved_quantity=reserved_qty,
            available_quantity=avail_qty,
            reorder_point=reorder_pt,
            reorder_quantity=reorder_qty,
            is_low_stock=is_low,
            days_of_inventory=days_of_inventory,
            units_sold_lookback=int(units_sold),
            orders_count_lookback=int(orders_count),
            revenue_lookback=Decimal(str(revenue)),
            sales_velocity=sales_velocity,
            lookback_days=lookback_days,
            total_historical_orders=int(total_lifetime_orders),
            historical_price_changes_count=int(price_changes_count),
            has_sufficient_data=has_sufficient_data and inv is not None,
            has_inventory=inv is not None,
            unavailable_quantity=inv.unavailable_quantity if inv else 0,
        )


def calculate_sales_velocity(units_sold: int, lookback_days: int) -> float:
    """Daily units sold, retaining precision for inventory classification."""
    if units_sold < 0 or lookback_days <= 0:
        raise ValueError("Units must be nonnegative and lookback days positive.")
    return units_sold / lookback_days
