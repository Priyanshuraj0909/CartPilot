"""Goal routing, relationships, budgets, safety and Phase 9 integration."""
from dataclasses import replace
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.agents.orchestrator import MasterOrchestrator, default_agents
from app.schemas.orchestration import OrchestrationRequest, AgentName
from app.schemas.actions import ActionCreate, ActionDecision
from app.services.actions import workflow
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.action import Action
from app.models.approval import Approval
from app.models.recommendation import Recommendation
from app.models.price_history import PriceHistory
from app.core.config import settings
from app.api.deps import get_database_session
from app.main import app
from tests.cross_agent_helpers import four_products

def request(scope, goal='balanced_growth', **extra):
    return OrchestrationRequest(merchant_id=scope['merchant'], goal=goal, product_ids=scope['products'], **extra)

@pytest.mark.parametrize('goal', ['balanced_growth','maximize_revenue','avoid_stockouts','reduce_excess_inventory','improve_product_performance','improve_catalog_quality'])
async def test_goals_and_determinism(db_session, goal):
    scope=await four_products(db_session); req=request(scope,goal)
    first=await MasterOrchestrator().analyze(req,db_session,scope['as_of'])
    second=await MasterOrchestrator().analyze(req,db_session,scope['as_of'])
    assert first == second and first.products_analyzed == 4 and first.approval_required
    assert first.prioritized_actions[0].agent == 'restock' and first.prioritized_actions[0].priority == 'critical'
    if goal=='balanced_growth': assert set(first.selected_agents)==set(AgentName)
    if goal=='improve_catalog_quality': assert 'pricing' not in first.selected_agents and 'promotion' not in first.selected_agents
    if goal=='avoid_stockouts': assert first.selected_agents == ['restock']
    if goal=='reduce_excess_inventory': assert {'promotion','pricing','listing'} <= set(first.selected_agents)

async def test_flagship_four_product_plan(db_session):
    scope=await four_products(db_session); plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    mouse,speaker,headphones,keyboard=scope['products']
    assert plan.opportunity_summary.restock_risks == [mouse]
    assert speaker in plan.opportunity_summary.promotion_opportunities
    assert headphones in plan.opportunity_summary.listing_issues
    assert any(i.product_id==speaker and i.agent=='promotion' and not i.blocked for i in plan.prioritized_actions)
    assert any(i.product_id==headphones and i.agent=='listing' for i in plan.prioritized_actions)
    assert all(i.product_id!=keyboard for i in plan.prioritized_actions)
    assert any(i.product_id==mouse and i.agent=='promotion' and i.depends_on==[f'{mouse}:restock'] for i in plan.blocked_actions)
    assert any(r.relationship_type=='synergy' and r.agent_a=='listing' and r.product_id==headphones for r in plan.recommendation_relationships)
    assert any(r.relationship_type=='dependency' and r.agent_b=='listing' for r in plan.recommendation_relationships)
    assert any(r.relationship_type=='independent' for r in plan.recommendation_relationships)

async def test_selection_avoids_blind_all_agents(db_session):
    scope=await four_products(db_session);plan=await MasterOrchestrator().analyze(request(scope,'maximize_revenue'),db_session,scope['as_of'])
    keyboard=next(o for o in plan.opportunities if o.product_id==scope['products'][3])
    assert keyboard.selected_agents==[]
    assert len(plan.agent_results)<16
    assert all(o.selection_reasons.keys()==set(o.selected_agents) for o in plan.opportunities)

async def test_goal_changes_overlap_resolution(db_session):
    scope=await four_products(db_session)
    speaker=scope['products'][1]
    plans=[]
    for goal in ('maximize_revenue','reduce_excess_inventory'):
        req=request(scope,goal);agents=default_agents(req);pricing=agents[AgentName.PRICING]
        def increase(signals):
            rec=pricing(signals)
            if signals.product_id==speaker:
                return rec.model_copy(update={'recommended_price':signals.current_price*Decimal('1.05'),'price_change_percent':5})
            return rec
        agents[AgentName.PRICING]=increase
        plans.append(await MasterOrchestrator(agents).analyze(req,db_session,scope['as_of']))
    revenue,excess=plans
    assert any(i.product_id==speaker and i.agent=='promotion' for i in revenue.blocked_actions)
    assert any(i.product_id==speaker and i.agent=='pricing' for i in excess.blocked_actions)
    assert any(i.product_id==speaker and i.agent=='promotion' for i in excess.prioritized_actions)

async def test_price_discount_safety_override(db_session):
    scope=await four_products(db_session);req=request(scope,'maximize_revenue'); agents=default_agents(req);pricing=agents[AgentName.PRICING]
    def discount(s):
        data=pricing(s).model_dump();data.update(recommended_price=s.current_price*Decimal('.95'),price_change_percent=-5)
        from app.schemas.pricing import PricingRecommendation
        return PricingRecommendation(**data)
    agents[AgentName.PRICING]=discount
    plan=await MasterOrchestrator(agents).analyze(req,db_session,scope['as_of'])
    item=next(i for i in plan.blocked_actions if i.agent=='pricing' and i.product_id==scope['low'])
    assert item.depends_on==[f"{scope['low']}:restock"] and not item.approval_candidate
    assert plan.overall_risk=='high'

async def test_partial_failure_blocks_discounts(db_session):
    scope=await four_products(db_session);req=request(scope); agents=default_agents(req)
    def fail(s): raise RuntimeError('private token')
    agents[AgentName.RESTOCK]=fail
    plan=await MasterOrchestrator(agents).analyze(req,db_session,scope['as_of'])
    assert not plan.complete and plan.overall_confidence==0 and plan.overall_risk=='high'
    assert plan.prioritized_actions and 'private token' not in plan.model_dump_json()
    assert any(not r.success and r.error.code=='agent_failed' for r in plan.agent_results)
    assert any(i.product_id==scope['products'][1] and i.agent=='promotion' for i in plan.blocked_actions)

async def test_action_limit_preserves_critical_visibility(db_session,monkeypatch):
    scope=await four_products(db_session);monkeypatch.setattr(settings,'MAX_ACTIONS_PER_PLAN',1)
    # Create several independently urgent products so critical overflow is exercised.
    for pid in scope['products'][1:]:
        inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==pid));inv.quantity=0
    await db_session.commit()
    plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    assert len(plan.prioritized_actions)==1 and any(i.priority=='critical' for i in plan.omitted_actions)
    assert any('critical items' in warning for warning in plan.warnings)
    assert len({i.id for i in [*plan.prioritized_actions,*plan.blocked_actions,*plan.omitted_actions]})==len(plan.prioritized_actions)+len(plan.blocked_actions)+len(plan.omitted_actions)

async def test_no_mutation_or_duplicate_persistence(db_session):
    scope=await four_products(db_session)
    before=(await db_session.execute(select(Product.id,Product.name,Product.description,Product.selling_price))).all()
    inventory=(await db_session.execute(select(Inventory.product_id,Inventory.quantity))).all()
    for _ in range(2): await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    assert (await db_session.execute(select(Product.id,Product.name,Product.description,Product.selling_price))).all()==before
    assert (await db_session.execute(select(Inventory.product_id,Inventory.quantity))).all()==inventory
    for model in (Recommendation,Action,Approval,PriceHistory): assert await db_session.scalar(select(func.count(model.id)))==0

async def test_fresh_analysis_flags_changed_opportunities(db_session):
    scope=await four_products(db_session);req=request(scope)
    first=await MasterOrchestrator().analyze(req,db_session,scope['as_of'])
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==scope['low']));inv.quantity=100
    await db_session.commit()
    second=await MasterOrchestrator().analyze(req,db_session,scope['as_of'])
    assert first.opportunity_summary.restock_risks != second.opportunity_summary.restock_risks

async def test_plan_candidate_uses_guarded_workflow(db_session):
    scope=await four_products(db_session);plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    item=next(i for i in plan.prioritized_actions if i.agent=='pricing' and i.approval_candidate)
    result=next(r for r in plan.agent_results if r.product_id==item.product_id and r.agent_name==item.agent)
    source=ActionCreate(merchant_id=scope['merchant'],agent=item.agent,recommendation=result.recommendation)
    created=await workflow.create_action(db_session,source);duplicate=await workflow.create_action(db_session,source)
    assert created.id==duplicate.id and created.status=='awaiting_approval'
    decision=ActionDecision(merchant_id=scope['merchant'])
    await workflow.decide_action(db_session,created.id,decision,True)
    product=await db_session.get(Product,item.product_id);await db_session.refresh(product)
    assert product.selling_price==result.recommendation.current_price
    done=await workflow.execute_action(db_session,created.id,decision)
    assert done.status=='executed'

@pytest.mark.parametrize('patch,status', [({},200),({'limit':2},200),({'product_ids':[]},422),({'limit':101},422),({'goal':'anything'},422),({'merchant_id':9999},404)])
async def test_store_wide_api(db_session,async_client,patch,status):
    scope=await four_products(db_session)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        response=await async_client.post('/api/v1/orchestrate',json={'merchant_id':scope['merchant'],'goal':'balanced_growth',**patch})
        assert response.status_code==status
        if status==200:
            plan=response.json();assert plan['products_analyzed']==patch.get('limit',4)
            assert plan['scope_has_more']==('limit' in patch)
            assert all(o['product_id']!=scope['foreign'] for o in plan['opportunities'])
    finally: app.dependency_overrides.clear()

async def test_twenty_opportunities_have_five_action_budget(db_session,monkeypatch):
    scope=await four_products(db_session)
    for index in range(16):
        product=Product(merchant_id=scope['merchant'],sku=f'OVERFLOW-{index}',name='Wireless USB Mouse',category='Electronics',cost_price=Decimal('500'),selling_price=Decimal('999'))
        db_session.add(product);await db_session.flush()
        db_session.add(Inventory(product_id=product.id,quantity=0,reserved_quantity=0,reorder_point=10,reorder_quantity=40))
        scope['products'].append(product.id)
        from app.models.order import Order
        from app.models.order_item import OrderItem
        order=Order(merchant_id=scope['merchant'],order_number=f'OVERFLOW-SALES-{index}',status='delivered',total_amount=Decimal('13986'),ordered_at=scope['as_of'])
        db_session.add(order);await db_session.flush()
        db_session.add(OrderItem(order_id=order.id,product_id=product.id,quantity=14,unit_price=Decimal('999'),subtotal=Decimal('13986')))
    await db_session.commit();monkeypatch.setattr(settings,'MAX_ACTIONS_PER_PLAN',5)
    plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    assert plan.products_analyzed==20 and len(plan.prioritized_actions)==5
    assert len(plan.omitted_actions)>=12 and any(i.priority=='critical' for i in plan.omitted_actions)
    assert len(plan.blocked_actions)>=17

async def test_missing_inventory_is_not_treated_as_safe(db_session):
    scope=await four_products(db_session)
    inventory=await db_session.scalar(select(Inventory).where(Inventory.product_id==scope['products'][1]))
    await db_session.delete(inventory);await db_session.commit();db_session.expire_all()
    plan=await MasterOrchestrator().analyze(request(scope,'maximize_revenue'),db_session,scope['as_of'])
    assert not plan.complete and plan.overall_risk=='high'
    assert any(i.product_id==scope['products'][1] and i.agent=='promotion' for i in plan.blocked_actions)

async def test_foreign_scope_fails_before_specialists(db_session):
    from app.services.orchestration.context import ContextError
    scope=await four_products(db_session)
    req=request(scope).model_copy(update={'product_ids':[scope['low'],scope['foreign']]})
    with pytest.raises(ContextError) as error:
        await MasterOrchestrator({}).analyze(req,db_session)
    assert error.value.status_code==403

async def test_old_saved_proposals_do_not_drive_plan(db_session):
    scope=await four_products(db_session)
    record=Recommendation(merchant_id=scope['merchant'],product_id=scope['low'],recommendation_type='promotion',title='Old unsafe proposal',recommended_value={'promotional_price':1},confidence=1,status='pending')
    db_session.add(record);await db_session.commit()
    plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    assert any(i.agent=='promotion' and i.product_id==scope['low'] for i in plan.blocked_actions)
    assert 'Old unsafe proposal' not in plan.model_dump_json()
    assert await db_session.scalar(select(func.count(Recommendation.id)))==1

async def test_storage_failure_sanitized(db_session,async_client,monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    import app.api.v1.orchestration as endpoint
    async def fail(*args,**kwargs): raise SQLAlchemyError('private connection details')
    monkeypatch.setattr(endpoint.orchestrator,'analyze',fail)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        response=await async_client.post('/api/v1/orchestrate',json={'merchant_id':1,'goal':'balanced_growth'})
        assert response.status_code==503 and 'private' not in response.text
    finally: app.dependency_overrides.clear()

async def test_direct_action_creation_cannot_bypass_inventory_override(db_session):
    from app.schemas.pricing import PricingRecommendation
    scope=await four_products(db_session)
    source=default_agents(request(scope))[AgentName.PRICING]
    from app.services.pricing.signals import extract_pricing_signals
    signals=await extract_pricing_signals(scope['low'],db_session,as_of=scope['as_of'])
    data=source(signals).model_dump();data.update(recommended_price=Decimal('949.05'),price_change_percent=-5)
    created=await workflow.create_action(db_session,ActionCreate(merchant_id=scope['merchant'],agent='pricing',recommendation=PricingRecommendation(**data)))
    assert created.status=='failed' and not created.policy.is_valid
    assert any('inventory risk' in reason for reason in created.policy.violations)

async def test_explicit_inactive_product_cannot_be_approval_candidate(db_session):
    scope=await four_products(db_session)
    product=await db_session.get(Product,scope['products'][2]);product.status='inactive';await db_session.commit()
    plan=await MasterOrchestrator().analyze(request(scope),db_session,scope['as_of'])
    assert any(i.product_id==product.id and i.agent=='listing' and not i.approval_candidate and 'inactive' in i.blocked_reason for i in plan.blocked_actions)
    assert all(i.product_id!=product.id or not i.approval_candidate for i in plan.prioritized_actions)

async def test_store_wide_empty_active_scope_returns_empty_plan(db_session):
    scope=await four_products(db_session)
    for pid in scope['products']:
        product=await db_session.get(Product,pid);product.status='inactive'
    await db_session.commit()
    plan=await MasterOrchestrator().analyze(OrchestrationRequest(merchant_id=scope['merchant'],goal='balanced_growth'),db_session,scope['as_of'])
    assert plan.products_analyzed==0 and plan.prioritized_actions==[] and plan.complete
