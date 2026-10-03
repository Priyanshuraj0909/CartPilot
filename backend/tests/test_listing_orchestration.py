"""Listing-only reads, grounding validation and cross-agent relationships."""
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.agents.orchestrator import MasterOrchestrator, validate_agent_output
from app.agents.listing_agent import ListingAgent
from app.schemas.orchestration import OrchestrationRequest, AgentResult, AgentName
from app.services.orchestration.routing import select_agents
from app.services.orchestration.conflicts import detect_relationships
from app.services.listing.signals import extract_listing_signals
from app.models.product import Product
from app.models.inventory import Inventory
from tests.test_listing import listing
from tests.test_promotion import candidate
from tests.test_orchestration_rules import results

@pytest.mark.parametrize('goal',['improve product listings','improve catalog quality','improve product discoverability','optimize product information'])
def test_routes(goal):
    r=OrchestrationRequest(merchant_id=1,goal=goal,product_ids=[1])
    assert select_agents(r.goal)==('listing',)

async def test_listing_needs_no_inventory_or_sales(db_session,monkeypatch):
    scope,p,_=await candidate(db_session)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==p.id))
    await db_session.delete(inv);await db_session.commit()
    async def forbidden(*args,**kwargs): raise AssertionError('Listing must not load sales analytics')
    monkeypatch.setattr('app.services.orchestration.context.extract_pricing_signals',forbidden)
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='improve product listings',product_ids=[p.id])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert plan.complete and plan.selected_agents==['listing']
    assert plan.recommendations[0].action=='review_listing'

async def test_combined_synergy(db_session):
    scope,p,_=await candidate(db_session)
    p.name='Wireless Mouse';p.description='Wireless mouse.'
    await db_session.commit()
    before=(p.name,p.description,p.selling_price)
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='improve product performance',product_ids=[p.id])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert plan.complete and plan.selected_agents==['pricing','promotion','listing']
    assert any('incomplete listing' in rel.message for rel in plan.relationships)
    await db_session.refresh(p);assert (p.name,p.description,p.selling_price)==before
    assert next(x for x in plan.recommendations if x.agent=='listing').priority=='low'

@pytest.mark.parametrize('price',[Decimal('95'),Decimal('100')])
def test_pricing_relationship(price):
    rec=ListingAgent().recommend(listing(description='Wireless mouse.'))
    raw=results(price=price)
    raw.append(AgentResult(agent_name='listing',product_id=1,success=True,recommendation=rec,risk_level=rec.risk_level,confidence=rec.confidence))
    conflicts,synergies=detect_relationships([raw[0],raw[-1]])
    assert not conflicts
    assert bool(synergies)==(price<100)

async def test_restock_listing_no_false_conflict(db_session):
    scope,p,_=await candidate(db_session)
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='improve listings while protecting inventory',product_ids=[scope['low']])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert plan.complete and not plan.conflicts
    assert plan.recommendations[0].agent=='restock' and plan.recommendations[0].priority=='critical'

@pytest.mark.parametrize('field,value',[('recommended_description','Bluetooth 5.3 RGB rechargeable 16000 DPI'),('current_title','Foreign title'),('quality_score',1.0),('product_id',999)])
async def test_untrusted_output_rejected(db_session,field,value):
    scope,p,_=await candidate(db_session)
    snapshot=await extract_listing_signals(p.id,db_session)
    rec=ListingAgent().recommend(snapshot).model_copy(update={field:value})
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='improve product listings',product_ids=[p.id])
    with pytest.raises(ValueError): validate_agent_output(AgentName.LISTING,rec,r,snapshot)

async def test_foreign_scope(db_session):
    from app.services.orchestration.context import ContextError
    scope,p,_=await candidate(db_session)
    r=OrchestrationRequest(merchant_id=scope['other'],goal='improve product listings',product_ids=[p.id])
    with pytest.raises(ContextError) as error: await MasterOrchestrator().analyze(r,db_session)
    assert error.value.status_code==403

async def test_invalid_title_partial_results(db_session):
    scope,p,_=await candidate(db_session)
    p.name='';await db_session.commit()
    r=OrchestrationRequest(merchant_id=scope['merchant'],goal='improve product performance',product_ids=[p.id])
    plan=await MasterOrchestrator().analyze(r,db_session,scope['as_of'])
    assert not plan.complete and next(x for x in plan.agent_results if x.agent_name=='listing').error.code=='invalid_agent_input'
    assert next(x for x in plan.agent_results if x.agent_name=='promotion').success

async def test_saved_payload(db_session):
    from app.services.listing.persistence import generate_and_persist_recommendation
    from app.services.store.catalog import get_saved_recommendations
    scope,p,_=await candidate(db_session)
    await generate_and_persist_recommendation(p.id,db_session)
    rows=await get_saved_recommendations(db_session,scope['merchant'])
    assert rows[0].payload.current_title==p.name and rows[0].agent=='listing'
