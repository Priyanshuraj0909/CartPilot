"""Pure restock calculations, input validation, and safety boundaries."""
import pytest
from pydantic import ValidationError
from app.schemas.restock import RestockPolicy, RestockRecommendation
from app.services.restock.signals import RestockSignals
from app.services.restock.calculator import calculate_restock_recommendation
from app.services.restock.rules import cap_reorder_quantity


def make_signals(**overrides):
    values = dict(product_id=1, quantity=5, reserved_quantity=0, reorder_point=10,
                  reorder_quantity=40, sales_velocity=4.0, recent_orders=10,
                  has_sufficient_data=True)
    values.update(overrides)
    return RestockSignals(**values)


def test_low_stock_and_lead_time_demand():
    result = calculate_restock_recommendation(make_signals())
    assert result.recommended_quantity == 63  # 20 + 8 + 40 - 5
    assert result.projected_demand_during_lead_time == 20
    assert result.safety_stock == 8
    assert result.estimated_days_remaining == 1.25
    assert result.risk_level == "high" and result.stockout_risk
    assert result.estimated_daily_sales == result.sales_velocity


def test_healthy_inventory():
    result = calculate_restock_recommendation(make_signals(quantity=100, sales_velocity=2))
    assert result.recommended_quantity == 0
    assert result.risk_level == "low" and not result.stockout_risk


def test_reserved_inventory():
    result = calculate_restock_recommendation(make_signals(quantity=50, reserved_quantity=45, sales_velocity=3))
    assert result.current_inventory == 50
    assert result.available_inventory == 5
    assert result.recommended_quantity == 56


def test_zero_sales_below_reorder_point():
    result = calculate_restock_recommendation(make_signals(sales_velocity=0))
    assert result.recommended_quantity == 0
    assert result.estimated_days_remaining is None
    assert result.risk_level == "low" and result.confidence == 0.2


def test_maximum_quantity_and_explanation():
    result = calculate_restock_recommendation(make_signals(sales_velocity=100, reorder_quantity=205))
    assert result.recommended_quantity == 500
    assert "capped at 500" in result.reason
    assert result.risk_level == "high"


@pytest.mark.parametrize("quantity,maximum,expected,capped", [(-15, 500, 0, False), (900, 500, 500, True), (500, 500, 500, False)])
def test_quantity_guardrail(quantity, maximum, expected, capped):
    assert cap_reorder_quantity(quantity, maximum) == (expected, capped)


def test_strong_demand():
    result = calculate_restock_recommendation(make_signals(quantity=15, sales_velocity=8))
    assert result.recommended_quantity == 81
    assert result.stockout_risk


def test_insufficient_history_is_conservative():
    result = calculate_restock_recommendation(make_signals(has_sufficient_data=False, recent_orders=1))
    assert result.recommended_quantity == 0
    assert result.confidence == 0.2
    assert result.risk_level == "high"  # Observed risk still merits merchant attention.


def test_determinism():
    signals = make_signals()
    assert calculate_restock_recommendation(signals) == calculate_restock_recommendation(signals)


@pytest.mark.parametrize("overrides", [dict(quantity=-1), dict(reserved_quantity=6),
    dict(reorder_quantity=-1), dict(reorder_point=-1), dict(sales_velocity=-1),
    dict(sales_velocity=float("nan")), dict(sales_velocity=float("inf"))])
def test_invalid_inputs(overrides):
    with pytest.raises(ValidationError):
        make_signals(**overrides)


@pytest.mark.parametrize("overrides", [dict(lookback_days=0), dict(lead_time_days=-1),
    dict(safety_stock_days=-1), dict(max_reorder_quantity=0), dict(lead_time_days=float("inf"))])
def test_invalid_policy(overrides):
    with pytest.raises(ValidationError):
        RestockPolicy(**overrides)


@pytest.mark.parametrize("field,value", [("RESTOCK_LOOKBACK_DAYS", 0), ("DEFAULT_LEAD_TIME_DAYS", -1),
    ("SAFETY_STOCK_DAYS", float("nan")), ("MAX_REORDER_QUANTITY", 0)])
def test_invalid_environment_config(field, value):
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_exact_lead_time_boundary_high_risk():
    result = calculate_restock_recommendation(make_signals(quantity=20))
    assert result.stockout_risk and result.risk_level == "high"


def test_safety_stock_boundary():
    result = calculate_restock_recommendation(make_signals(quantity=28))
    assert result.recommended_quantity == 0 and result.risk_level == "low"


def test_reorder_point_boundary_medium_risk():
    result = calculate_restock_recommendation(make_signals(quantity=10, sales_velocity=1))
    assert result.recommended_quantity == 37
    assert result.risk_level == "medium" and not result.stockout_risk


def test_fractional_demand_rounds_up():
    result = calculate_restock_recommendation(make_signals(quantity=0, sales_velocity=1 / 14, reorder_quantity=0))
    assert result.safety_stock == 1
    assert result.recommended_quantity == 2


def test_custom_policy():
    result = calculate_restock_recommendation(make_signals(), RestockPolicy(lead_time_days=2, safety_stock_days=1, max_reorder_quantity=10))
    assert result.lead_time_days == 2 and result.safety_stock == 4
    assert result.recommended_quantity == 10


def test_inactive_product_no_order():
    result = calculate_restock_recommendation(make_signals(status="inactive"))
    assert result.recommended_quantity == 0 and result.confidence == 0.2


@pytest.mark.parametrize("overrides", [dict(recommended_quantity=-1), dict(confidence=1.1),
    dict(risk_level="extreme"), dict(available_inventory=100), dict(sales_velocity=float("inf"))])
def test_output_schema(overrides):
    data = calculate_restock_recommendation(make_signals()).model_dump(exclude={"estimated_daily_sales"})
    data.update(overrides)
    with pytest.raises(ValidationError):
        RestockRecommendation(**data)
