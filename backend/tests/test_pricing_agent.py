"""Comprehensive integration test suite for the Pricing Agent covering all 11 required scenarios."""

from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pricing_agent import PricingAgent
from app.services.pricing.persistence import generate_and_persist_recommendation
from app.models.inventory import Inventory
from app.models.merchant import Merchant
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.schemas.pricing import RiskLevel
from app.services.pricing.calculator import calculate_pricing_recommendation
from app.services.pricing.signals import ProductPricingSignals


@pytest.fixture
async def setup_pricing_environment(db_session: AsyncSession):
    """Helper creating a test merchant and products with diverse inventory and sales profiles."""
    merchant = Merchant(name="Agent Merchant", email="agent@test.com", store_name="Agent Store")
    db_session.add(merchant)
    await db_session.flush()

    # 1. Normal Product
    p_normal = Product(
        merchant_id=merchant.id,
        sku="SKU-NORM",
        name="Normal Item",
        category="Cat",
        cost_price=Decimal("40.00"),
        selling_price=Decimal("100.00"),
    )
    # 2. Low Inventory Item
    p_low_inv = Product(
        merchant_id=merchant.id,
        sku="SKU-LOW-INV",
        name="Low Stock Item",
        category="Cat",
        cost_price=Decimal("50.00"),
        selling_price=Decimal("100.00"),
    )
    # 3. High Inventory Item (Sluggish sales)
    p_high_inv = Product(
        merchant_id=merchant.id,
        sku="SKU-HIGH-INV",
        name="Surplus Item",
        category="Cat",
        cost_price=Decimal("30.00"),
        selling_price=Decimal("100.00"),
    )
    # 4. Brand New Item (Insufficient data)
    p_new = Product(
        merchant_id=merchant.id,
        sku="SKU-NEW",
        name="Untested New Item",
        category="Cat",
        cost_price=Decimal("20.00"),
        selling_price=Decimal("50.00"),
    )
    db_session.add_all([p_normal, p_low_inv, p_high_inv, p_new])
    await db_session.flush()

    # Associated inventories
    inv_norm = Inventory(product_id=p_normal.id, quantity=60, reserved_quantity=5, reorder_point=15, reorder_quantity=40)
    inv_low = Inventory(product_id=p_low_inv.id, quantity=8, reserved_quantity=2, reorder_point=15, reorder_quantity=40)
    inv_high = Inventory(product_id=p_high_inv.id, quantity=250, reserved_quantity=0, reorder_point=15, reorder_quantity=40)
    inv_new = Inventory(product_id=p_new.id, quantity=50, reserved_quantity=0, reorder_point=10, reorder_quantity=30)
    db_session.add_all([inv_norm, inv_low, inv_high, inv_new])
    await db_session.flush()

    # Orders for Normal item (healthy/strong sales)
    for i in range(1, 10):
        order = Order(
            merchant_id=merchant.id,
            order_number=f"ORD-N-{i:03d}",
            status=OrderStatus.DELIVERED.value,
            total_amount=Decimal("100.00"),
        )
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(order_id=order.id, product_id=p_normal.id, quantity=2, unit_price=Decimal("100.00"), subtotal=Decimal("200.00")))

    # Orders for Low inventory item (high demand)
    for i in range(1, 12):
        order = Order(
            merchant_id=merchant.id,
            order_number=f"ORD-L-{i:03d}",
            status=OrderStatus.DELIVERED.value,
            total_amount=Decimal("100.00"),
        )
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(order_id=order.id, product_id=p_low_inv.id, quantity=1, unit_price=Decimal("100.00"), subtotal=Decimal("100.00")))

    # Sparse orders for Surplus item (weak sales: 1 order only)
    order_weak = Order(
        merchant_id=merchant.id,
        order_number="ORD-H-001",
        status=OrderStatus.DELIVERED.value,
        total_amount=Decimal("100.00"),
    )
    db_session.add(order_weak)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order_weak.id, product_id=p_high_inv.id, quantity=1, unit_price=Decimal("100.00"), subtotal=Decimal("100.00")))

    await db_session.commit()
    return {
        "normal": p_normal,
        "low_inv": p_low_inv,
        "high_inv": p_high_inv,
        "new": p_new,
    }


# ---------------------------------------------------------------------------
# Test 1: Normal Product Analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normal_product_recommendation(db_session: AsyncSession, setup_pricing_environment):
    """Test 1: Normal product with healthy stock and demand generates valid recommendation."""
    products = setup_pricing_environment
    agent = PricingAgent()
    rec = await agent.analyze(product_id=products["normal"].id, session=db_session)

    assert rec.product_id == products["normal"].id
    assert rec.current_price == Decimal("100.00")
    assert rec.recommended_price >= rec.cost_price
    assert 0.0 <= rec.confidence <= 1.0
    assert rec.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]


# ---------------------------------------------------------------------------
# Test 2: Below-Cost Protection
# ---------------------------------------------------------------------------

def test_below_cost_protection_calculator():
    """Test 2: When proposed discount drops below cost, clamp to cost floor."""
    signals = ProductPricingSignals(
        product_id=10,
        merchant_id=1,
        sku="TEST-COST",
        name="Cost Floor Item",
        category="Cat",
        cost_price=Decimal("580.00"),
        current_price=Decimal("600.00"),
        status="active",
        total_quantity=200,
        reserved_quantity=0,
        available_quantity=200,
        reorder_point=10,
        reorder_quantity=20,
        is_low_stock=False,
        days_of_inventory=100.0,
        units_sold_lookback=1,
        orders_count_lookback=3,
        revenue_lookback=Decimal("600.00"),
        sales_velocity=0.07,
        lookback_days=14,
        total_historical_orders=3,
        historical_price_changes_count=1,
        has_sufficient_data=True,
    )
    # The 5% proposed discount (570) must be raised to the 580 cost floor.
    rec = calculate_pricing_recommendation(signals, max_decrease_percent=30.0)
    assert rec.recommended_price == Decimal("580.00")
    assert "below unit cost price" in rec.reason


# ---------------------------------------------------------------------------
# Test 3: Maximum Increase Guardrail
# ---------------------------------------------------------------------------

def test_maximum_increase_guardrail():
    """Test 3: Enforce configured maximum price increase cap (e.g. 10%)."""
    signals = ProductPricingSignals(
        product_id=11,
        merchant_id=1,
        sku="TEST-INC",
        name="Surging Demand Item",
        category="Cat",
        cost_price=Decimal("500.00"),
        current_price=Decimal("1000.00"),
        status="active",
        total_quantity=100,
        reserved_quantity=0,
        available_quantity=100,
        reorder_point=10,
        reorder_quantity=20,
        is_low_stock=False,
        days_of_inventory=10.0,
        units_sold_lookback=100,
        orders_count_lookback=50,
        revenue_lookback=Decimal("10000.00"),
        sales_velocity=7.14,
        lookback_days=14,
        total_historical_orders=50,
        historical_price_changes_count=2,
        has_sufficient_data=True,
    )
    rec = calculate_pricing_recommendation(signals, max_increase_percent=10.0)
    assert rec.recommended_price <= Decimal("1100.00")
    assert rec.price_change_percent <= 10.0


# ---------------------------------------------------------------------------
# Test 4: Maximum Decrease Guardrail
# ---------------------------------------------------------------------------

def test_maximum_decrease_guardrail():
    """Test 4: Enforce configured maximum price decrease cap (e.g. 10%)."""
    signals = ProductPricingSignals(
        product_id=12,
        merchant_id=1,
        sku="TEST-DEC",
        name="Sluggish Item",
        category="Cat",
        cost_price=Decimal("200.00"),
        current_price=Decimal("1000.00"),
        status="active",
        total_quantity=500,
        reserved_quantity=0,
        available_quantity=500,
        reorder_point=10,
        reorder_quantity=20,
        is_low_stock=False,
        days_of_inventory=200.0,
        units_sold_lookback=1,
        orders_count_lookback=3,
        revenue_lookback=Decimal("1000.00"),
        sales_velocity=0.07,
        lookback_days=14,
        total_historical_orders=3,
        historical_price_changes_count=1,
        has_sufficient_data=True,
    )
    rec = calculate_pricing_recommendation(signals, max_decrease_percent=10.0)
    assert rec.recommended_price >= Decimal("900.00")
    assert rec.price_change_percent >= -10.0


# ---------------------------------------------------------------------------
# Test 5: Low Inventory Safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_inventory_safety(db_session: AsyncSession, setup_pricing_environment):
    """Test 5: Low stock items must not be discounted (stable or moderate increase)."""
    products = setup_pricing_environment
    agent = PricingAgent()
    rec = await agent.analyze(product_id=products["low_inv"].id, session=db_session)

    # Must never recommend a decrease on low stock
    assert rec.recommended_price >= rec.current_price
    assert rec.price_change_percent >= 0.0


# ---------------------------------------------------------------------------
# Test 6: Strong Sales Opportunity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strong_sales_increase(db_session: AsyncSession, setup_pricing_environment):
    """Test 6: High sales velocity with healthy stock yields controlled price rise."""
    products = setup_pricing_environment
    agent = PricingAgent()
    rec = await agent.analyze(product_id=products["normal"].id, session=db_session)

    assert rec.recommended_price > rec.current_price
    assert rec.price_change_percent > 0.0
    assert rec.price_change_percent <= 10.0


# ---------------------------------------------------------------------------
# Test 7: Slow Sales + High Inventory (Controlled Decrease)
# ---------------------------------------------------------------------------

def test_slow_sales_high_inventory_decrease():
    """Test 7: Surplus inventory paired with sluggish sales yields controlled discount."""
    signals = ProductPricingSignals(
        product_id=14,
        merchant_id=1,
        sku="TEST-SLOW-SURPLUS",
        name="Stagnant Item",
        category="Cat",
        cost_price=Decimal("40.00"),
        current_price=Decimal("100.00"),
        status="active",
        total_quantity=200,
        reserved_quantity=0,
        available_quantity=200,
        reorder_point=15,
        reorder_quantity=40,
        is_low_stock=False,
        days_of_inventory=150.0,
        units_sold_lookback=2,
        orders_count_lookback=3,
        revenue_lookback=Decimal("200.00"),
        sales_velocity=0.14,
        lookback_days=14,
        total_historical_orders=3,
        historical_price_changes_count=1,
        has_sufficient_data=True,
    )
    rec = calculate_pricing_recommendation(signals)
    assert rec.recommended_price < rec.current_price
    assert rec.price_change_percent < 0.0
    assert rec.recommended_price >= rec.cost_price


# ---------------------------------------------------------------------------
# Test 8: Insufficient Data Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insufficient_data_safe_fallback(db_session: AsyncSession, setup_pricing_environment):
    """Test 8: Uncalibrated items with 0 sales maintain stable price with high risk."""
    products = setup_pricing_environment
    agent = PricingAgent()
    rec = await agent.analyze(product_id=products["new"].id, session=db_session)

    assert rec.recommended_price == rec.current_price
    assert rec.price_change_percent == 0.0
    assert rec.confidence <= 0.30
    assert rec.risk_level == RiskLevel.HIGH
    assert "Insufficient" in rec.reason


# ---------------------------------------------------------------------------
# Test 9: Negative/Invalid Prices Rejected
# ---------------------------------------------------------------------------

def test_invalid_prices_rejected():
    """Test 9: Negative current price or negative cost price raises ValueError."""
    signals_bad_price = ProductPricingSignals(
        product_id=15,
        merchant_id=1,
        sku="BAD-P",
        name="Bad Item",
        category="Cat",
        cost_price=Decimal("10.00"),
        current_price=Decimal("-5.00"),
        status="active",
        total_quantity=10,
        reserved_quantity=0,
        available_quantity=10,
        reorder_point=5,
        reorder_quantity=10,
        is_low_stock=False,
        days_of_inventory=10.0,
        units_sold_lookback=5,
        orders_count_lookback=5,
        revenue_lookback=Decimal("50.00"),
        sales_velocity=0.35,
        lookback_days=14,
        total_historical_orders=5,
        historical_price_changes_count=0,
        has_sufficient_data=True,
    )
    with pytest.raises(ValueError, match="price must be strictly positive"):
        calculate_pricing_recommendation(signals_bad_price)


# ---------------------------------------------------------------------------
# Test 10: Determinism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recommendation_determinism(db_session: AsyncSession, setup_pricing_environment):
    """Test 10: Same input data produces identical output across multiple runs."""
    products = setup_pricing_environment
    agent = PricingAgent()

    run1 = await agent.analyze(product_id=products["normal"].id, session=db_session)
    run2 = await agent.analyze(product_id=products["normal"].id, session=db_session)

    assert run1.recommended_price == run2.recommended_price
    assert run1.confidence == run2.confidence
    assert run1.risk_level == run2.risk_level
    assert run1.reason == run2.reason
    assert run1.price_change_percent == run2.price_change_percent


# ---------------------------------------------------------------------------
# Test 11: Crucial Safety Check — No Automatic Price Mutation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_automatic_price_mutation(db_session: AsyncSession, setup_pricing_environment):
    """Test 11: CRITICAL — Generating or persisting a recommendation must NEVER alter Product.selling_price."""
    products = setup_pricing_environment
    prod = products["normal"]
    initial_price = prod.selling_price

    agent = PricingAgent()

    # 1. Run read-only analyze
    rec1 = await agent.analyze(product_id=prod.id, session=db_session)
    assert rec1.recommended_price != initial_price  # Confirmed recommendation proposes change

    # Re-fetch from DB
    res1 = await db_session.execute(select(Product).where(Product.id == prod.id))
    unmutated1 = res1.scalar_one()
    assert unmutated1.selling_price == initial_price

    # 2. Run analyze_and_persist (which stores a pending Recommendation row)
    rec2 = await generate_and_persist_recommendation(product_id=prod.id, session=db_session)
    assert rec2.recommended_price != initial_price

    # Re-fetch again from DB
    res2 = await db_session.execute(select(Product).where(Product.id == prod.id))
    unmutated2 = res2.scalar_one()
    assert unmutated2.selling_price == initial_price, (
        f"CRITICAL VIOLATION: Product price was mutated from {initial_price} to {unmutated2.selling_price}!"
    )


@pytest.mark.asyncio
async def test_future_orders_excluded(db_session, setup_pricing_environment):
    from datetime import datetime, timedelta, timezone
    from app.services.pricing.signals import extract_pricing_signals
    product = setup_pricing_environment["new"]
    now = datetime.now(timezone.utc)
    order = Order(merchant_id=product.merchant_id, order_number="FUTURE",
                  status="delivered", total_amount=Decimal("5000"),
                  ordered_at=now + timedelta(days=1))
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=100,
                             unit_price=Decimal("50"), subtotal=Decimal("5000")))
    await db_session.flush()
    signals = await extract_pricing_signals(product.id, db_session, as_of=now)
    assert signals.units_sold_lookback == 0
    assert signals.total_historical_orders == 0
    assert not signals.has_sufficient_data


@pytest.mark.asyncio
async def test_persistence_stays_pending_and_inventory_unchanged(db_session, setup_pricing_environment):
    from app.models.recommendation import Recommendation
    product = setup_pricing_environment["normal"]
    inventory = (await db_session.execute(select(Inventory).where(Inventory.product_id == product.id))).scalar_one()
    inventory_id = inventory.id
    before = (inventory.quantity, inventory.reserved_quantity)
    await generate_and_persist_recommendation(product.id, db_session)
    await db_session.commit()
    db_session.expire_all()
    saved = (await db_session.execute(select(Recommendation))).scalar_one()
    assert saved.status == "pending"
    inventory = (await db_session.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one()
    assert (inventory.quantity, inventory.reserved_quantity) == before
