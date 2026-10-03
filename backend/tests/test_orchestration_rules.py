"""Deterministic routing, conflict detection, and schema boundaries."""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas.orchestration import AgentName, AgentResult, Goal, OrchestrationRequest
from app.schemas.pricing import PricingRecommendation
from app.schemas.restock import RestockRecommendation
from app.services.orchestration.context import BusinessContext
from app.services.orchestration.routing import select_agents
from app.services.orchestration.conflicts import detect_relationships
from app.services.orchestration.coordinator import create_plan


def results(price=Decimal("95"), risk="high", product_id=1):
    pricing = PricingRecommendation(product_id=product_id, current_price=100, recommended_price=price,
        cost_price=50, reason="Test pricing rationale", confidence=.8, risk_level="medium",
        price_change_percent=float(price - 100), sales_velocity=4, inventory_quantity=5)
    restock = RestockRecommendation(product_id=product_id, current_inventory=50, available_inventory=5,
        sales_velocity=4, estimated_days_remaining=1.25, recommended_quantity=63,
        reason="Inventory at risk", confidence=.75, risk_level=risk, reorder_point=10,
        lead_time_days=5, safety_stock=8, projected_demand_during_lead_time=20, stockout_risk=risk == "high")
    return [AgentResult(agent_name="pricing", product_id=product_id, success=True,
                       recommendation=pricing, risk_level=pricing.risk_level, confidence=pricing.confidence),
            AgentResult(agent_name="restock", product_id=product_id, success=True,
                       recommendation=restock, risk_level=restock.risk_level, confidence=restock.confidence)]


@pytest.mark.parametrize("goal,expected", [
    ("Optimize pricing", ["pricing"]), ("Increase revenue", ["pricing"]),
    ("Avoid stockouts", ["restock"]), ("Protect inventory", ["restock"]),
    ("Increase revenue while avoiding stockouts", ["pricing", "restock"]),
    ("Improve revenue while maintaining inventory health", ["pricing", "restock"]),
    ("  Improve REVENUE while avoiding stockouts. ", ["pricing", "restock"]),
])
def test_goal_routing(goal, expected):
    request = OrchestrationRequest(merchant_id=1, goal=goal, product_ids=[1])
    assert list(select_agents(request.goal)) == expected


@pytest.mark.parametrize("overrides", [dict(goal="Do anything"), dict(product_ids=[]),
    dict(product_ids=[1, 1]), dict(product_ids=[True]), dict(product_ids=["1"]),
    dict(merchant_id=0), dict(constraints={"max_reorder_quantity": 501}),
    dict(constraints={"max_price_increase_percent": 11}),
    dict(constraints={"max_price_decrease_percent": -1}),
    dict(constraints={"max_price_increase_percent": float("nan")}),
    dict(constraints={"auto_approve": True})])
def test_invalid_request(overrides):
    data = dict(merchant_id=1, goal="optimize pricing", product_ids=[1])
    data.update(overrides)
    with pytest.raises(ValidationError):
        OrchestrationRequest(**data)


def test_conflict_deferred_discount_priority_and_confidence():
    raw = results()
    request = OrchestrationRequest(merchant_id=1, goal=Goal.REVENUE_AND_STOCKOUTS, product_ids=[1])
    context = BusinessContext(request, (), select_agents(request.goal), datetime.now(timezone.utc))
    plan = create_plan(context, raw)
    assert plan.conflicts[0].type == "pricing_inventory_conflict"
    assert plan.conflicts[0].severity == "high"
    assert plan.recommendations[0].agent == "restock" and plan.recommendations[0].priority == "critical"
    pricing = plan.recommendations[1]
    assert pricing.action == "hold_price" and pricing.recommended_price == Decimal("100")
    assert pricing.deferred and pricing.priority == "low"
    assert raw[0].recommendation.recommended_price == Decimal("95")
    assert plan.overall_risk == "high" and plan.approval_required
    assert plan.overall_confidence == .6


def test_increase_is_synergy_not_conflict():
    conflicts, relationships = detect_relationships(results(Decimal("105")))
    assert not conflicts and relationships[0].type == "synergy"


def test_healthy_inventory_discount_has_no_conflict():
    assert detect_relationships(results(risk="low")) == ([], [])


def test_products_never_cross_matched():
    raw = results()
    other_restock = results(product_id=2)[1]
    assert detect_relationships([raw[0], other_restock]) == ([], [])


@pytest.mark.parametrize("data", [
    dict(agent_name="pricing", product_id=1, success=True),
    dict(agent_name="restock", product_id=1, success=False),
])
def test_invalid_agent_wrapper(data):
    with pytest.raises(ValidationError):
        AgentResult(**data)


def test_deterministic_product_scope():
    request = OrchestrationRequest(merchant_id=1, goal="optimize pricing", product_ids=[3, 1, 2])
    assert request.product_ids == [1, 2, 3]
