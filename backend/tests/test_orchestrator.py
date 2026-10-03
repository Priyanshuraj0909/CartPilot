"""Master Orchestrator integration, failures, and operational safety."""
from dataclasses import replace
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.agents.orchestrator import MasterOrchestrator, default_agents
from app.schemas.orchestration import AgentName, OrchestrationRequest
from app.services.orchestration.context import ContextError, build_context
from app.services.orchestration.routing import select_agents
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.recommendation import Recommendation
from app.models.action import Action
from app.models.approval import Approval
from app.models.order import Order
from tests.orchestration_helpers import make_store


def request(store, goal="Increase revenue while avoiding stockouts", products=None, **kwargs):
    return OrchestrationRequest(merchant_id=store["merchant"], goal=goal,
                                product_ids=products or [store["low"]], **kwargs)


@pytest.mark.asyncio
async def test_combined_demo_and_priority(db_session):
    store = await make_store(db_session)
    plan = await MasterOrchestrator().analyze(request(store), db_session, store["as_of"])
    assert plan.complete and plan.selected_agents == ["pricing", "restock"]
    assert plan.recommendations[0].agent == "restock"
    assert plan.recommendations[0].recommended_quantity == 67
    assert plan.recommendations[1].recommended_price == Decimal("1048.95")
    assert not plan.conflicts and plan.relationships[0].type == "synergy"
    assert plan.overall_risk == "high" and plan.approval_required


@pytest.mark.asyncio
@pytest.mark.parametrize("goal,agent", [("Optimize pricing", "pricing"), ("Avoid stockouts", "restock")])
async def test_single_agent_execution(db_session, goal, agent):
    store = await make_store(db_session)
    plan = await MasterOrchestrator().analyze(request(store, goal), db_session)
    assert len(plan.agent_results) == 1 and plan.agent_results[0].agent_name == agent


@pytest.mark.asyncio
async def test_multi_product_determinism_and_shared_snapshot(db_session):
    store = await make_store(db_session)
    req = request(store, products=[store["healthy"], store["low"]])
    context = await build_context(req, select_agents(req.goal), db_session, store["as_of"])
    assert context.products[0].signals[AgentName.PRICING] is context.products[0].signals[AgentName.RESTOCK]
    orchestrator = MasterOrchestrator()
    first = await orchestrator.analyze(req, db_session, store["as_of"])
    second = await orchestrator.analyze(req, db_session, store["as_of"])
    assert first == second and len(first.agent_results) == 4
    assert first.recommendations[0].agent == "restock"


@pytest.mark.asyncio
async def test_partial_failure_preserves_success_and_sanitizes_error(db_session):
    store = await make_store(db_session)
    req = request(store)
    agents = default_agents(req)
    def fail(signals):
        raise RuntimeError("private credential should never appear")
    agents[AgentName.RESTOCK] = fail
    plan = await MasterOrchestrator(agents).analyze(req, db_session)
    assert not plan.complete and plan.overall_risk == "high"
    assert len(plan.recommendations) == 1
    assert plan.agent_results[0].success and not plan.agent_results[1].success
    assert plan.agent_results[1].error.code == "agent_failed"
    assert "private credential" not in plan.model_dump_json()
    assert plan.overall_confidence == 0


@pytest.mark.asyncio
async def test_conflict_demo_with_injected_discount(db_session):
    store = await make_store(db_session)
    req = request(store)
    agents = default_agents(req)
    pricing = agents[AgentName.PRICING]
    agents[AgentName.PRICING] = lambda signals: pricing(replace(signals, is_low_stock=False,
        days_of_inventory=100, units_sold_lookback=1, sales_velocity=.07, has_sufficient_data=True))
    plan = await MasterOrchestrator(agents).analyze(req, db_session)
    assert plan.conflicts and plan.recommendations[1].deferred
    assert plan.recommendations[1].recommended_price == Decimal("999")
    assert plan.agent_results[0].recommendation.recommended_price == Decimal("949.05")


@pytest.mark.asyncio
async def test_no_operational_or_recommendation_mutation(db_session):
    store = await make_store(db_session)
    before_prices = (await db_session.execute(select(Product.id, Product.selling_price))).all()
    before_inventory = (await db_session.execute(select(Inventory.product_id, Inventory.quantity, Inventory.reserved_quantity))).all()
    await MasterOrchestrator().analyze(request(store), db_session)
    db_session.expire_all()
    assert (await db_session.execute(select(Product.id, Product.selling_price))).all() == before_prices
    assert (await db_session.execute(select(Inventory.product_id, Inventory.quantity, Inventory.reserved_quantity))).all() == before_inventory
    for model in (Recommendation, Action, Approval):
        assert await db_session.scalar(select(func.count(model.id))) == 0
    assert await db_session.scalar(select(func.count(Order.id))) == 7


@pytest.mark.asyncio
async def test_ownership_rejected_before_agent_calls(db_session):
    store = await make_store(db_session)
    with pytest.raises(ContextError) as error:
        await MasterOrchestrator({}).analyze(request(store, products=[store["low"], store["foreign"]]), db_session)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_constraints_tighten_both_agents(db_session):
    store = await make_store(db_session)
    req = request(store, constraints={"max_price_increase_percent": 2, "max_reorder_quantity": 20})
    plan = await MasterOrchestrator().analyze(req, db_session)
    assert plan.agent_results[0].recommendation.recommended_price <= Decimal("1018.98")
    assert plan.agent_results[1].recommendation.recommended_quantity == 20


@pytest.mark.asyncio
async def test_invalid_price_partial_success(db_session):
    store = await make_store(db_session)
    product = await db_session.get(Product, store["low"])
    product.selling_price = Decimal("0")
    await db_session.commit()
    plan = await MasterOrchestrator().analyze(request(store), db_session)
    assert not plan.agent_results[0].success and plan.agent_results[1].success
    assert not plan.complete


@pytest.mark.asyncio
async def test_invalid_output_product_is_rejected(db_session):
    store = await make_store(db_session)
    req = request(store)
    agents = default_agents(req)
    pricing = agents[AgentName.PRICING]
    agents[AgentName.PRICING] = lambda signals: pricing(replace(signals, product_id=store["foreign"]))
    plan = await MasterOrchestrator(agents).analyze(req, db_session)
    assert not plan.agent_results[0].success
    assert plan.agent_results[0].error.code == "invalid_agent_output"


@pytest.mark.asyncio
async def test_all_agents_fail_returns_incomplete_plan(db_session):
    store = await make_store(db_session)
    plan = await MasterOrchestrator({}).analyze(request(store), db_session)
    assert not plan.complete and not plan.recommendations
    assert plan.overall_risk == "high" and plan.overall_confidence == 0


@pytest.mark.asyncio
async def test_discount_deferred_when_inventory_analysis_fails(db_session):
    from app.schemas.pricing import PricingRecommendation
    store = await make_store(db_session)
    req = request(store)
    agents = default_agents(req)
    pricing = agents[AgentName.PRICING]
    def discount(signals):
        data = pricing(signals).model_dump()
        data.update(recommended_price=Decimal("949.05"), price_change_percent=-5)
        return PricingRecommendation(**data)
    def fail(signals):
        raise ValueError("Inventory unavailable")
    agents[AgentName.PRICING] = discount
    agents[AgentName.RESTOCK] = fail
    plan = await MasterOrchestrator(agents).analyze(req, db_session)
    assert not plan.complete and not plan.conflicts
    assert plan.recommendations[0].deferred and plan.recommendations[0].action == "hold_price"


@pytest.mark.asyncio
async def test_no_implicit_flush_of_caller_changes(db_session):
    store = await make_store(db_session)
    product = await db_session.get(Product, store["low"])
    product.name = "Caller has uncommitted changes"
    await MasterOrchestrator().analyze(request(store), db_session)
    with db_session.no_autoflush:
        stored_name = await db_session.scalar(select(Product.name).where(Product.id == store["low"]))
    assert stored_name == "Wireless Mouse"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_output_cannot_invent_current_price(db_session):
    store = await make_store(db_session)
    req = request(store)
    agents = default_agents(req)
    pricing = agents[AgentName.PRICING]
    agents[AgentName.PRICING] = lambda signals: pricing(replace(signals, current_price=Decimal("1000")))
    plan = await MasterOrchestrator(agents).analyze(req, db_session)
    assert not plan.agent_results[0].success and plan.agent_results[1].success
