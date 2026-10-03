"""Guarded local execution and rollback tests against real model persistence."""
from decimal import Decimal
import pytest
from sqlalchemy import select, func, update
from app.models.action import Action
from app.models.approval import Approval
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.audit_log import AuditLog
from app.models.price_history import PriceHistory
from app.models.recommendation import Recommendation
from app.agents.pricing_agent import PricingAgent
from app.agents.restock_agent import RestockAgent
from app.agents.promotion_agent import PromotionAgent
from app.agents.listing_agent import ListingAgent
from app.schemas.actions import ActionCreate, ActionDecision, PricePayload, RestockPayload, PromotionPayload, ListingPayload
from app.services.actions import workflow
from app.services.actions.state import ActionError, transition
from app.services.policies.validator import validate_policy
from tests.test_promotion import candidate

async def setup_action(session, agent='pricing'):
    scope,p,_=await candidate(session)
    if agent=='pricing':
        pid=scope['low'];rec=await PricingAgent().analyze(pid,session)
    elif agent=='restock':
        pid=scope['low'];rec=await RestockAgent().analyze(pid,session)
    elif agent=='promotion':
        pid=p.id;rec=await PromotionAgent().analyze(pid,session)
    else:
        pid=p.id;p.description=None;await session.commit();rec=await ListingAgent().analyze(pid,session)
    request=ActionCreate(merchant_id=scope['merchant'],agent=agent,recommendation=rec)
    response=await workflow.create_action(session,request)
    decision=ActionDecision(merchant_id=scope['merchant'],actor='merchant-demo',comment='Reviewed local proposal')
    return scope,pid,response,decision,request

async def count(session,model):
    return await session.scalar(select(func.count(model.id)))

async def test_price_full_path_and_duplicate(db_session):
    s=db_session
    scope,pid,created,decision,request=await setup_action(s)
    assert created.status=='awaiting_approval' and created.policy.is_valid and created.approval_required
    product=await s.get(Product,pid);old=product.selling_price
    duplicate=await workflow.create_action(s,request);assert duplicate.id==created.id
    approved=await workflow.decide_action(s,created.id,decision,True)
    await s.refresh(product);assert product.selling_price==old and approved.status=='approved'
    done=await workflow.execute_action(s,created.id,decision)
    await s.refresh(product);assert product.selling_price==Decimal('1048.95') and done.status=='executed'
    assert await count(s,PriceHistory)==1
    again=await workflow.execute_action(s,created.id,decision)
    assert again.executed_at==done.executed_at and await count(s,PriceHistory)==1
    rows=(await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    events=[x.event_type for x in rows]
    for event in ['recommendation_created','action_created','policy_validated','action_approved','execution_started','execution_completed']: assert event in events
    assert rows[-1].metadata_['before']['selling_price']=='999.00'
    assert rows[-1].metadata_['after']['selling_price']=='1048.95'

@pytest.mark.parametrize('approved',[False,None])
async def test_rejected_and_unapproved(db_session,approved):
    scope,pid,created,decision,_=await setup_action(db_session)
    if approved is False: await workflow.decide_action(db_session,created.id,decision,False)
    with pytest.raises(ActionError): await workflow.execute_action(db_session,created.id,decision)
    assert (await db_session.get(Product,pid)).selling_price==999
    assert await count(db_session,PriceHistory)==0
    assert await db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_type=='execution_blocked'))==1

@pytest.mark.parametrize('case',['increase','below_cost','margin','cent'])
async def test_price_guardrails(db_session,case):
    scope,pid,created,decision,_=await setup_action(db_session)
    product=await db_session.get(Product,pid)
    payload=PricePayload(product_id=pid,old_price=999,new_price=1499 if case=='increase' else 499 if case=='below_cost' else 500 if case=='margin' else 999.01,expected_cost=500)
    if case=='margin':
        from app.core.config import settings
        old=settings.MIN_MARGIN_PERCENT;settings.MIN_MARGIN_PERCENT=10
    try:
        policy=await validate_policy(payload,product,db_session)
        assert policy.is_valid==(case=='cent')
    finally:
        if case=='margin': settings.MIN_MARGIN_PERCENT=old

async def test_policy_block_at_creation(db_session):
    scope,p,_=await candidate(db_session)
    rec=await PricingAgent().analyze(scope['low'],db_session)
    data=rec.model_dump();data['recommended_price']=Decimal('1499');data['price_change_percent']=50
    created=await workflow.create_action(db_session,ActionCreate(merchant_id=scope['merchant'],agent='pricing',recommendation=data))
    assert created.status=='failed' and not created.policy.is_valid and created.result['outcome']=='blocked'
    with pytest.raises(ActionError): await workflow.decide_action(db_session,created.id,ActionDecision(merchant_id=scope['merchant']),True)

@pytest.mark.parametrize('field,value',[('selling_price',Decimal('1099')),('cost_price',Decimal('600'))])
async def test_stale_price(db_session,field,value):
    scope,pid,created,decision,_=await setup_action(db_session)
    await workflow.decide_action(db_session,created.id,decision,True)
    product=await db_session.get(Product,pid);setattr(product,field,value);await db_session.commit()
    done=await workflow.execute_action(db_session,created.id,decision)
    assert done.status=='approved' and done.result['outcome']=='blocked'
    assert not done.policy.is_valid and await count(db_session,PriceHistory)==0

@pytest.mark.parametrize('agent',['restock','promotion','listing'])
async def test_other_actions(db_session,agent):
    scope,pid,created,decision,_=await setup_action(db_session,agent)
    product=await db_session.get(Product,pid);before=(product.name,product.description,product.selling_price)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==pid));qty=inv.quantity
    await workflow.decide_action(db_session,created.id,decision,True)
    done=await workflow.execute_action(db_session,created.id,decision)
    assert done.status=='executed'
    await db_session.refresh(product);await db_session.refresh(inv)
    assert inv.quantity==qty
    if agent=='listing':
        assert product.description==done.payload.new_description and product.description!=before[1]
        assert done.result['before']['description'] is None
    else:
        assert (product.name,product.description,product.selling_price)==before and done.execution_mode=='simulated'

async def test_promotion_current_stockout_block(db_session):
    scope,pid,created,decision,_=await setup_action(db_session,'promotion')
    await workflow.decide_action(db_session,created.id,decision,True)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==pid));inv.quantity=2;await db_session.commit()
    result=await workflow.execute_action(db_session,created.id,decision)
    assert result.result['outcome']=='blocked' and any('stockout' in x for x in result.policy.violations)
    assert result.status=='approved'

async def test_restock_limit_and_relevance(db_session):
    scope,pid,created,decision,_=await setup_action(db_session,'restock')
    product=await db_session.get(Product,pid)
    policy=await validate_policy(RestockPayload(product_id=pid,quantity=900),product,db_session)
    assert not policy.is_valid and any('maximum' in x for x in policy.violations)
    await workflow.decide_action(db_session,created.id,decision,True)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==pid));inv.quantity=1000;await db_session.commit()
    assert (await workflow.execute_action(db_session,created.id,decision)).result['outcome']=='blocked'

async def test_listing_stale_and_ungrounded(db_session):
    scope,pid,created,decision,_=await setup_action(db_session,'listing')
    product=await db_session.get(Product,pid)
    unsafe=created.payload.model_copy(update={'new_description':'Bluetooth 5.3 RGB rechargeable'})
    assert not (await validate_policy(unsafe,product,db_session)).is_valid
    await workflow.decide_action(db_session,created.id,decision,True)
    product.description='Changed source';await db_session.commit()
    assert (await workflow.execute_action(db_session,created.id,decision)).result['outcome']=='blocked'

async def test_rollback_on_executor_failure(db_session,monkeypatch):
    scope,pid,created,decision,_=await setup_action(db_session)
    await workflow.decide_action(db_session,created.id,decision,True)
    original=workflow.apply_local
    async def fail(*args,**kwargs):
        await original(*args,**kwargs)
        await db_session.flush()
        raise RuntimeError('private failure details')
    monkeypatch.setattr(workflow,'apply_local',fail)
    result=await workflow.execute_action(db_session,created.id,decision)
    assert result.status=='failed' and 'private' not in str(result.result)
    assert (await db_session.get(Product,pid,populate_existing=True)).selling_price==999
    assert await count(db_session,PriceHistory)==0
    assert await db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_type=='execution_failed'))==1

@pytest.mark.parametrize('operation',['read','approve','execute'])
async def test_merchant_isolation(db_session,operation):
    scope,pid,created,decision,_=await setup_action(db_session)
    other=ActionDecision(merchant_id=scope['other'])
    with pytest.raises(ActionError) as error:
        if operation=='read': await workflow.load_action(db_session,created.id,scope['other'])
        elif operation=='approve': await workflow.decide_action(db_session,created.id,other,True)
        else: await workflow.execute_action(db_session,created.id,other)
    assert error.value.status_code==403

@pytest.mark.parametrize('source,target',[('rejected','approved'),('executed','approved'),('failed','executing'),('awaiting_approval','executed'),('cancelled','executing')])
def test_invalid_transitions(source,target):
    with pytest.raises(ActionError): transition(Action(status=source),target)

async def test_payload_tampering(db_session):
    scope,pid,created,decision,_=await setup_action(db_session)
    await workflow.decide_action(db_session,created.id,decision,True)
    action=await db_session.get(Action,created.id)
    action.payload={**action.payload,'new_price':'1090'};await db_session.commit()
    result=await workflow.execute_action(db_session,created.id,decision)
    assert result.result['outcome']=='blocked' and await count(db_session,PriceHistory)==0

async def test_completed_audit_failure_rolls_back_mutation(db_session, monkeypatch):
    scope, pid, created, decision, _ = await setup_action(db_session)
    await workflow.decide_action(db_session, created.id, decision, True)
    original = workflow.audit
    def fail_completion(session, action, rec, event, actor, details=None):
        if event == 'execution_completed':
            raise RuntimeError('Private storage diagnostic')
        return original(session, action, rec, event, actor, details)
    monkeypatch.setattr(workflow, 'audit', fail_completion)
    result = await workflow.execute_action(db_session, created.id, decision)
    product = await db_session.get(Product, pid)
    await db_session.refresh(product)
    assert result.status == 'failed' and product.selling_price == Decimal('999.00')
    assert await count(db_session, PriceHistory) == 0
    assert 'Private' not in str(result.result)
    assert await db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_type == 'execution_failed')) == 1

async def test_saved_reference_to_inline_action_deduplicates(db_session):
    scope, _, created, _, _ = await setup_action(db_session)
    existing = await workflow.create_action(db_session, ActionCreate(merchant_id=scope['merchant'], recommendation_id=created.recommendation_id))
    assert existing.id == created.id
    assert await count(db_session, Action) == 1
