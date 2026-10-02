"""Unit and integration tests for Phase 2 Data Layer.

Verifies:
- Product creation, boundaries, and constraint enforcement
- Inventory retrieval and stock availability calculations
- Order and order line item retrieval and cascade behaviors
- Sales aggregation and sales velocity calculations
- Seed dataset volume requirements (>=20 products, >=100 orders)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory import Inventory
from app.models.merchant import Merchant
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product


# ---------------------------------------------------------------------------
# 1. Product Creation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_creation_happy_path(db_session: AsyncSession):
    """Happy path: Create and query a valid product belonging to a merchant."""
    merchant = Merchant(
        name="Test Merchant",
        email="test@merchant.com",
        store_name="Test Store",
    )
    db_session.add(merchant)
    await db_session.flush()

    product = Product(
        merchant_id=merchant.id,
        sku="TEST-SKU-001",
        name="Ergonomic Mousepad",
        description="Memory foam desk wrist support.",
        category="Workspace",
        cost_price=Decimal("5.50"),
        selling_price=Decimal("19.99"),
        status="active",
    )
    db_session.add(product)
    await db_session.commit()

    query = select(Product).where(Product.sku == "TEST-SKU-001")
    result = await db_session.execute(query)
    saved = result.scalar_one()

    assert saved.id is not None
    assert saved.name == "Ergonomic Mousepad"
    assert saved.cost_price == Decimal("5.50")
    assert saved.selling_price == Decimal("19.99")
    assert saved.created_at is not None
    assert saved.updated_at is not None


@pytest.mark.asyncio
async def test_product_creation_boundary_zero_prices(db_session: AsyncSession):
    """Boundary condition: Zero cost and zero selling prices are valid non-negative values."""
    merchant = Merchant(name="Merchant B", email="b@merchant.com", store_name="Store B")
    db_session.add(merchant)
    await db_session.flush()

    free_product = Product(
        merchant_id=merchant.id,
        sku="FREE-GIFT-001",
        name="Complimentary Sticker",
        category="Promotional",
        cost_price=Decimal("0.00"),
        selling_price=Decimal("0.00"),
    )
    db_session.add(free_product)
    await db_session.commit()
    assert free_product.id is not None


@pytest.mark.asyncio
async def test_product_duplicate_sku_failure(db_session: AsyncSession):
    """Failure case: Duplicate SKU within the same merchant violates uniqueness constraint."""
    merchant = Merchant(name="Merchant C", email="c@merchant.com", store_name="Store C")
    db_session.add(merchant)
    await db_session.flush()

    prod1 = Product(
        merchant_id=merchant.id,
        sku="DUPLICATE-SKU",
        name="Item One",
        category="General",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
    )
    db_session.add(prod1)
    await db_session.flush()

    prod2 = Product(
        merchant_id=merchant.id,
        sku="DUPLICATE-SKU",
        name="Item Two",
        category="General",
        cost_price=Decimal("12.00"),
        selling_price=Decimal("25.00"),
    )
    db_session.add(prod2)

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_product_negative_price_failure(db_session: AsyncSession):
    """Failure case: Negative selling price violates check constraint."""
    merchant = Merchant(name="Merchant D", email="d@merchant.com", store_name="Store D")
    db_session.add(merchant)
    await db_session.flush()

    invalid_product = Product(
        merchant_id=merchant.id,
        sku="INVALID-PRICE",
        name="Bad Price Item",
        category="General",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("-5.00"),
    )
    db_session.add(invalid_product)

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 2. Inventory Retrieval & Stock Availability Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inventory_retrieval_and_properties(db_session: AsyncSession):
    """Happy path & boundary: Verify available quantity and low-stock detection."""
    merchant = Merchant(name="Merchant E", email="e@merchant.com", store_name="Store E")
    db_session.add(merchant)
    await db_session.flush()

    prod = Product(
        merchant_id=merchant.id,
        sku="INV-TEST-001",
        name="Stock Item",
        category="General",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("25.00"),
    )
    db_session.add(prod)
    await db_session.flush()

    # Case A: Normal stock levels
    inv = Inventory(
        product_id=prod.id,
        quantity=50,
        reserved_quantity=10,
        reorder_point=15,
        reorder_quantity=40,
    )
    db_session.add(inv)
    await db_session.commit()

    # Query product with loaded inventory
    result = await db_session.execute(
        select(Product).options(selectinload(Product.inventory)).where(Product.id == prod.id)
    )
    loaded_prod = result.scalar_one()

    assert loaded_prod.inventory is not None
    assert loaded_prod.inventory.available_quantity == 40
    assert loaded_prod.inventory.is_low_stock is False

    # Case B: Low stock trigger condition
    loaded_prod.inventory.quantity = 20
    loaded_prod.inventory.reserved_quantity = 10  # Available = 10 <= reorder_point (15)
    await db_session.commit()

    assert loaded_prod.inventory.available_quantity == 10
    assert loaded_prod.inventory.is_low_stock is True

    # Case C: Fully depleted stock
    loaded_prod.inventory.quantity = 5
    loaded_prod.inventory.reserved_quantity = 5
    assert loaded_prod.inventory.available_quantity == 0
    assert loaded_prod.inventory.is_low_stock is True


# ---------------------------------------------------------------------------
# 3. Order Retrieval & Line Item Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_retrieval_and_cascade(db_session: AsyncSession):
    """Happy path: Create order with line items, query, and verify cascading deletion."""
    merchant = Merchant(name="Merchant F", email="f@merchant.com", store_name="Store F")
    db_session.add(merchant)
    await db_session.flush()

    p1 = Product(merchant_id=merchant.id, sku="P1", name="Item 1", category="Cat", cost_price=Decimal("5"), selling_price=Decimal("10"))
    p2 = Product(merchant_id=merchant.id, sku="P2", name="Item 2", category="Cat", cost_price=Decimal("8"), selling_price=Decimal("15"))
    db_session.add_all([p1, p2])
    await db_session.flush()

    order = Order(
        merchant_id=merchant.id,
        order_number="ORD-TEST-001",
        customer_reference="customer@test.com",
        status=OrderStatus.CONFIRMED.value,
        total_amount=Decimal("35.00"),
    )
    db_session.add(order)
    await db_session.flush()

    item1 = OrderItem(order_id=order.id, product_id=p1.id, quantity=2, unit_price=Decimal("10.00"), subtotal=Decimal("20.00"))
    item2 = OrderItem(order_id=order.id, product_id=p2.id, quantity=1, unit_price=Decimal("15.00"), subtotal=Decimal("15.00"))
    db_session.add_all([item1, item2])
    await db_session.commit()

    # Query with joined line items
    stmt = select(Order).options(selectinload(Order.items)).where(Order.order_number == "ORD-TEST-001")
    res = await db_session.execute(stmt)
    retrieved = res.scalar_one()

    assert retrieved.total_amount == Decimal("35.00")
    assert len(retrieved.items) == 2
    assert retrieved.status == "confirmed"

    # Cascade deletion check: deleting the order must remove line items
    await db_session.delete(retrieved)
    await db_session.commit()

    remaining_items = await db_session.execute(select(OrderItem).where(OrderItem.order_id == retrieved.id))
    assert len(remaining_items.scalars().all()) == 0


@pytest.mark.asyncio
async def test_order_invalid_status_failure(db_session: AsyncSession):
    """Failure case: Non-existent order status violates database check constraint."""
    merchant = Merchant(name="Merchant G", email="g@merchant.com", store_name="Store G")
    db_session.add(merchant)
    await db_session.flush()

    bad_order = Order(
        merchant_id=merchant.id,
        order_number="ORD-INVALID-STATUS",
        status="non_standard_status",
        total_amount=Decimal("10.00"),
    )
    db_session.add(bad_order)

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 4. Sales Aggregation & Sales Velocity Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sales_aggregation_metrics(seeded_session: AsyncSession):
    """Verify sales revenue calculation, total orders, and item sales breakdown."""
    # Total revenue across delivered and shipped orders
    rev_stmt = select(func.sum(Order.total_amount)).where(
        Order.status.in_([OrderStatus.DELIVERED.value, OrderStatus.SHIPPED.value])
    )
    rev_res = await seeded_session.execute(rev_stmt)
    completed_revenue = rev_res.scalar_one()
    assert completed_revenue is not None
    assert completed_revenue > Decimal("0.00")

    # Product sales aggregation: Units sold and revenue per product
    sales_stmt = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
            func.coalesce(func.sum(OrderItem.subtotal), Decimal("0.00")).label("gross_sales"),
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .group_by(Product.id, Product.sku, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
    )
    sales_res = await seeded_session.execute(sales_stmt)
    top_sellers = sales_res.all()

    assert len(top_sellers) > 0
    top_product = top_sellers[0]
    assert top_product.units_sold > 0
    assert top_product.gross_sales > Decimal("0.00")


@pytest.mark.asyncio
async def test_sales_velocity_calculation(seeded_session: AsyncSession):
    """Calculate sales velocity (units/day) over the last 14 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    stmt = (
        select(
            OrderItem.product_id,
            func.sum(OrderItem.quantity).label("recent_units"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.ordered_at >= cutoff)
        .where(Order.status != OrderStatus.CANCELLED.value)
        .group_by(OrderItem.product_id)
    )
    res = await seeded_session.execute(stmt)
    velocities = res.all()

    assert len(velocities) > 0
    for prod_id, recent_units in velocities:
        daily_velocity = float(recent_units) / 14.0
        assert daily_velocity >= 0.0


@pytest.mark.asyncio
async def test_sales_aggregation_empty_boundary(db_session: AsyncSession):
    """Boundary condition: Aggregate sales for a catalog with 0 orders returns None or 0 gracefully."""
    merchant = Merchant(name="Empty Merchant", email="empty@test.com", store_name="Empty Store")
    db_session.add(merchant)
    await db_session.flush()

    prod = Product(merchant_id=merchant.id, sku="ZERO-SALES", name="Never Sold", category="Test", cost_price=Decimal("1"), selling_price=Decimal("5"))
    db_session.add(prod)
    await db_session.commit()

    stmt = (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .where(OrderItem.product_id == prod.id)
    )
    result = await db_session.execute(stmt)
    units_sold = result.scalar_one()
    assert units_sold == 0


# ---------------------------------------------------------------------------
# 5. Phase 2 Seed Dataset Volume Validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_dataset_requirements(seeded_session: AsyncSession):
    """Verify seed script satisfies Phase 2 requirements (>=20 products, >=100 orders, realistic inventory)."""
    # Verify Products count >= 20
    prod_count_res = await seeded_session.execute(select(func.count(Product.id)))
    product_count = prod_count_res.scalar_one()
    assert product_count >= 20, f"Expected at least 20 products, found {product_count}"

    # Verify Orders count >= 100
    order_count_res = await seeded_session.execute(select(func.count(Order.id)))
    order_count = order_count_res.scalar_one()
    assert order_count >= 100, f"Expected at least 100 orders, found {order_count}"

    # Verify all products have corresponding Inventory
    inv_count_res = await seeded_session.execute(select(func.count(Inventory.id)))
    inventory_count = inv_count_res.scalar_one()
    assert inventory_count == product_count, "Each product must have an associated inventory record"

    # Verify low-stock items exist to supply testing signals for future specialist agents
    low_stock_res = await seeded_session.execute(
        select(func.count(Inventory.id)).where(Inventory.quantity - Inventory.reserved_quantity <= Inventory.reorder_point)
    )
    low_stock_count = low_stock_res.scalar_one()
    assert low_stock_count > 0, "Seed dataset must include realistic low-stock situations for Restock Agent testing"
