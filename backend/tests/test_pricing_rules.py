"""Unit tests for deterministic pricing rules, guardrails, confidence, and risk scoring."""

from decimal import Decimal
import pytest

from app.schemas.pricing import RiskLevel
from app.services.pricing.rules import (
    apply_below_cost_guardrail,
    apply_price_change_caps,
    calculate_confidence,
    calculate_risk_level,
)
from app.services.pricing.signals import ProductPricingSignals


def make_test_signals(
    product_id: int = 1,
    cost_price: Decimal = Decimal("50.00"),
    current_price: Decimal = Decimal("100.00"),
    available_quantity: int = 50,
    reorder_point: int = 15,
    reorder_quantity: int = 40,
    units_sold_lookback: int = 14,
    orders_count_lookback: int = 10,
    sales_velocity: float = 1.0,
    historical_price_changes_count: int = 2,
    has_sufficient_data: bool = True,
) -> ProductPricingSignals:
    """Helper constructing mock signals for pure rule evaluation."""
    is_low = available_quantity <= reorder_point
    days_of_inv = available_quantity / sales_velocity if sales_velocity > 0 else 999.0
    return ProductPricingSignals(
        product_id=product_id,
        merchant_id=1,
        sku="TEST-SKU",
        name="Test Item",
        category="Test Category",
        cost_price=cost_price,
        current_price=current_price,
        status="active",
        total_quantity=available_quantity,
        reserved_quantity=0,
        available_quantity=available_quantity,
        reorder_point=reorder_point,
        reorder_quantity=reorder_quantity,
        is_low_stock=is_low,
        days_of_inventory=days_of_inv,
        units_sold_lookback=units_sold_lookback,
        orders_count_lookback=orders_count_lookback,
        revenue_lookback=Decimal("1000.00"),
        sales_velocity=sales_velocity,
        lookback_days=14,
        total_historical_orders=orders_count_lookback,
        historical_price_changes_count=historical_price_changes_count,
        has_sufficient_data=has_sufficient_data,
    )


# ---------------------------------------------------------------------------
# Rule 1: Below-Cost Protection
# ---------------------------------------------------------------------------

def test_below_cost_protection_triggers_when_price_below_cost():
    """Rule 1: If proposed price is less than cost price, clamp to cost floor."""
    cost = Decimal("500.00")
    proposed = Decimal("450.00")
    final_price, was_clamped = apply_below_cost_guardrail(proposed, cost)

    assert final_price == Decimal("500.00")
    assert was_clamped is True


def test_below_cost_protection_passes_when_price_above_cost():
    """Rule 1: If proposed price is above cost price, leave untouched."""
    cost = Decimal("500.00")
    proposed = Decimal("550.00")
    final_price, was_clamped = apply_below_cost_guardrail(proposed, cost)

    assert final_price == Decimal("550.00")
    assert was_clamped is False


def test_below_cost_protection_with_minimum_margin():
    """Rule 1 boundary: Configurable minimum margin (e.g. 10%) enforces cost * 1.10."""
    cost = Decimal("100.00")
    proposed = Decimal("105.00")
    final_price, was_clamped = apply_below_cost_guardrail(proposed, cost, min_margin_percent=10.0)

    assert final_price == Decimal("110.00")
    assert was_clamped is True


# ---------------------------------------------------------------------------
# Rules 2 & 3: Maximum Price Increase / Decrease Guardrails
# ---------------------------------------------------------------------------

def test_max_increase_cap_enforced():
    """Rule 2: Cap proposed price if increase exceeds configured percentage (e.g. 10%)."""
    current_price = Decimal("1000.00")
    proposed_price = Decimal("1300.00")  # +30%
    capped, was_inc, was_dec = apply_price_change_caps(
        current_price=current_price,
        proposed_price=proposed_price,
        max_increase_percent=10.0,
        max_decrease_percent=10.0,
    )

    assert capped == Decimal("1100.00")
    assert was_inc is True
    assert was_dec is False


def test_max_decrease_cap_enforced():
    """Rule 3: Cap proposed price if decrease exceeds configured percentage (e.g. 10%)."""
    current_price = Decimal("1000.00")
    proposed_price = Decimal("700.00")  # -30%
    capped, was_inc, was_dec = apply_price_change_caps(
        current_price=current_price,
        proposed_price=proposed_price,
        max_increase_percent=10.0,
        max_decrease_percent=10.0,
    )

    assert capped == Decimal("900.00")
    assert was_inc is False
    assert was_dec is True


def test_price_within_caps_unchanged():
    """Boundary: Price within the +10% / -10% window remains unchanged."""
    current_price = Decimal("1000.00")
    proposed_price = Decimal("1050.00")  # +5%
    capped, was_inc, was_dec = apply_price_change_caps(
        current_price=current_price,
        proposed_price=proposed_price,
        max_increase_percent=10.0,
        max_decrease_percent=10.0,
    )

    assert capped == Decimal("1050.00")
    assert was_inc is False
    assert was_dec is False


# ---------------------------------------------------------------------------
# Confidence & Risk Scoring
# ---------------------------------------------------------------------------

def test_confidence_insufficient_data():
    """Rule 7: Confidence is low (0.20) when data sufficiency flag is False."""
    signals = make_test_signals(has_sufficient_data=False, orders_count_lookback=0, units_sold_lookback=0)
    confidence = calculate_confidence(signals)
    assert confidence == 0.20


def test_confidence_bounded_range():
    """Confidence score must strictly adhere to 0.0 <= confidence <= 1.0."""
    high_volume_signals = make_test_signals(
        orders_count_lookback=50,
        units_sold_lookback=100,
        sales_velocity=5.0,
        historical_price_changes_count=10,
    )
    confidence = calculate_confidence(high_volume_signals)
    assert 0.0 <= confidence <= 1.0
    assert confidence >= 0.80


def test_risk_level_classifications():
    """Verify RiskLevel evaluation across high, medium, and low scenarios."""
    # High risk: Insufficient data
    s_insufficient = make_test_signals(has_sufficient_data=False)
    assert calculate_risk_level(s_insufficient, Decimal("100"), False, False, False) == RiskLevel.HIGH

    # High risk: Low inventory
    s_low_inv = make_test_signals(available_quantity=5, reorder_point=15)
    assert calculate_risk_level(s_low_inv, Decimal("100"), False, False, False) == RiskLevel.HIGH

    # High risk: Below-cost clamping
    s_normal = make_test_signals()
    assert calculate_risk_level(s_normal, Decimal("50"), True, False, False) == RiskLevel.HIGH

    # Medium risk: Capped by maximum limits
    assert calculate_risk_level(s_normal, Decimal("110"), False, True, False) == RiskLevel.MEDIUM

    # Low risk: Normal healthy operations with small change
    assert calculate_risk_level(s_normal, Decimal("102"), False, False, False) == RiskLevel.LOW


@pytest.mark.parametrize("current,proposed,increase,decrease", [
    ("9.99", "20", 5, 10), ("9.99", "1", 10, 5),
])
def test_fractional_cent_caps_remain_inside_limits(current, proposed, increase, decrease):
    price, _, _ = apply_price_change_caps(Decimal(current), Decimal(proposed), increase, decrease)
    assert price <= Decimal(current) * (1 + Decimal(str(increase)) / 100)
    assert price >= Decimal(current) * (1 - Decimal(str(decrease)) / 100)


def test_conflicting_cost_and_increase_limits_rejected():
    from app.services.pricing.calculator import calculate_pricing_recommendation
    with pytest.raises(ValueError, match="conflicts"):
        calculate_pricing_recommendation(make_test_signals(cost_price=Decimal("120")))


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_prices_rejected(price):
    from app.services.pricing.calculator import calculate_pricing_recommendation
    with pytest.raises(ValueError, match="finite"):
        calculate_pricing_recommendation(make_test_signals(current_price=Decimal(price)))


@pytest.mark.parametrize("field,value", [
    ("MAX_PRICE_INCREASE_PERCENT", -1), ("MAX_PRICE_DECREASE_PERCENT", 100),
    ("PRICING_LOOKBACK_DAYS", 0), ("MIN_MARGIN_PERCENT", -1),
    ("PRICING_ADJUSTMENT_PERCENT", float("nan")),
])
def test_invalid_pricing_configuration_rejected(field, value):
    from app.core.config import Settings
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


def test_sales_velocity_keeps_precision_and_validates_window():
    from app.services.pricing.signals import calculate_sales_velocity
    assert calculate_sales_velocity(1, 14) == 1 / 14
    with pytest.raises(ValueError):
        calculate_sales_velocity(1, 0)


@pytest.mark.parametrize("overrides", [
    {"confidence": 1.1}, {"risk_level": "extreme"},
    {"recommended_price": Decimal("40")}, {"sales_velocity": float("inf")},
])
def test_recommendation_schema_rejects_invalid_output(overrides):
    from app.services.pricing.calculator import calculate_pricing_recommendation
    from app.schemas.pricing import PricingRecommendation
    data = calculate_pricing_recommendation(make_test_signals()).model_dump()
    data.update(overrides)
    with pytest.raises(ValueError):
        PricingRecommendation(**data)


@pytest.mark.parametrize("status,age,expected", [
    ("cancelled", 1, 0), ("delivered", 15, 0), ("delivered", 14, 2),
])
@pytest.mark.asyncio
async def test_sales_lookback_boundaries(db_session, status, age, expected):
    from datetime import datetime, timedelta, timezone
    from app.models.merchant import Merchant
    from app.models.product import Product
    from app.models.order import Order
    from app.models.order_item import OrderItem
    from app.models.inventory import Inventory
    from app.services.pricing.signals import extract_pricing_signals
    merchant = Merchant(name="Window", email="window@test.com", store_name="Window")
    db_session.add(merchant)
    await db_session.flush()
    product = Product(merchant_id=merchant.id, sku="WINDOW", name="Window", category="Test",
                      cost_price=Decimal("50"), selling_price=Decimal("100"))
    db_session.add(product)
    await db_session.flush()
    db_session.add(Inventory(product_id=product.id, quantity=50, reserved_quantity=5,
                             reorder_point=10, reorder_quantity=20))
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    order = Order(merchant_id=merchant.id, order_number="WINDOW", status=status,
                  ordered_at=now - timedelta(days=age), total_amount=Decimal("200"))
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=2,
                             unit_price=Decimal("100"), subtotal=Decimal("200")))
    await db_session.flush()
    signals = await extract_pricing_signals(product.id, db_session, as_of=now)
    assert signals.units_sold_lookback == expected
    assert signals.revenue_lookback == Decimal(expected * 100)
    assert signals.available_quantity == 45


def test_low_inventory_weak_sales_does_not_discount():
    from app.services.pricing.calculator import calculate_pricing_recommendation
    signals = make_test_signals(available_quantity=5, sales_velocity=0.1, units_sold_lookback=1)
    recommendation = calculate_pricing_recommendation(signals)
    assert recommendation.recommended_price == signals.current_price
