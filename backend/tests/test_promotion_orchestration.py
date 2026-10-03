"""Promotion routing, coordination and adversarial specialist validation."""
from dataclasses import replace
from decimal import Decimal
import pytest
from app.agents.orchestrator import MasterOrchestrator, validate_agent_output
from app.agents.promotion_agent import PromotionAgent
from app.schemas.orchestration import OrchestrationRequest, AgentResult, AgentName
from app.services.orchestration.routing import select_agents
from app.services.orchestration.context import BusinessContext
from app.services.orchestration.coordinator import create_plan
from tests.test_promotion import candidate
from tests.test_orchestration_rules import results

@pytest.mark.parametrize('goal',['move slow inventory','increase sell-through','reduce excess inventory','improve revenue from slow-moving products'])
def test_promotion_routing(goal):
    r=OrchestrationRequest(merchant_id=1,goal=goal,product_ids=[1]);assert select_agents(r.goal)==('promotion',)

async def test_combined_readonly(db_session):
    scope,product,_=await candidate(db_session)
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='increase revenue while maintaining healthy inventory',product_ids=[scope['low'],product.id])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert plan.selected_agents==['pricing','restock','promotion'] and len(plan.agent_results)==6 and plan.complete
    promos={x.product_id:x.recommendation for x in plan.agent_results if x.agent_name=='promotion'}
    assert not promos[scope['low']].promotion_recommended and promos[product.id].promotion_recommended
    assert plan.recommendations[0].agent=='restock' and plan.recommendations[0].priority=='critical'
    await db_session.refresh(product);assert product.selling_price==1499

@pytest.mark.parametrize('mode',['stockout','increase','decrease','hold','failed_restock'])
async def test_conflicts(db_session,mode):
    scope,product,s=await candidate(db_session)
    promo=PromotionAgent().recommend(s).model_copy(update={'product_id':1})
    raw=results(price=Decimal('105') if mode=='increase' else Decimal('95') if mode=='decrease' else Decimal('100'),risk='high' if mode=='stockout' else 'low')
    raw.append(AgentResult(agent_name='promotion',product_id=1,success=True,recommendation=promo,risk_level=promo.risk_level,confidence=promo.confidence))
    if mode=='failed_restock': raw[1]=AgentResult(agent_name='restock',product_id=1,success=False,error={'code':'agent_failed','message':'Unavailable'})
    request=OrchestrationRequest(merchant_id=1,goal='increase revenue while maintaining healthy inventory',product_ids=[1])
    plan=create_plan(BusinessContext(request,(),select_agents(request.goal),scope['as_of']),raw)
    coordinated=next(x for x in plan.recommendations if x.agent=='promotion')
    if mode=='stockout': assert plan.conflicts[0].type=='promotion_inventory_conflict'
    if mode in ['increase','decrease']: assert plan.conflicts[0].type=='pricing_promotion_conflict'
    assert coordinated.deferred==(mode!='hold')
    if coordinated.deferred: assert coordinated.action=='no_promotion' and coordinated.recommended_price==1499
    else: assert coordinated.action=='review_promotion' and plan.relationships
    assert raw[-1].recommendation.discount_percentage==10

@pytest.mark.parametrize('violation',['inventory','margin','cap','price'])
async def test_untrusted_output(db_session,violation):
    scope,product,s=await candidate(db_session)
    rec=PromotionAgent().recommend(s)
    request=OrchestrationRequest(merchant_id=scope['merchant'],goal='reduce excess inventory',product_ids=[product.id])
    if violation=='inventory': s=replace(s,restock=s.restock.model_copy(update={'risk_level':'high'}))
    if violation=='margin': rec=rec.model_copy(update={'promotional_price':Decimal('1')})
    if violation=='cap': request=request.model_copy(update={'constraints':request.constraints.model_copy(update={'max_promotion_discount_percent':5})})
    if violation=='price': rec=rec.model_copy(update={'current_price':Decimal('1')})
    with pytest.raises(ValueError): validate_agent_output(AgentName.PROMOTION,rec,request,s)

async def test_tightened_discount(db_session):
    scope,product,_=await candidate(db_session)
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='reduce excess inventory',product_ids=[product.id],constraints={'max_promotion_discount_percent':3})
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert plan.complete and plan.agent_results[0].recommendation.discount_percentage==3

async def test_missing_inventory_partial(db_session):
    from sqlalchemy import select
    from app.models.inventory import Inventory
    scope,product,_=await candidate(db_session)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==product.id));await db_session.delete(inv);await db_session.commit();db_session.expire(product,['inventory'])
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='increase revenue while maintaining healthy inventory',product_ids=[product.id])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert not plan.complete
    assert next(x for x in plan.agent_results if x.agent_name=='promotion').error.code=='invalid_agent_input'
    assert next(x for x in plan.agent_results if x.agent_name=='pricing').success
