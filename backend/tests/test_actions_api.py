"""Action API contracts, ownership, explicit confirmation and concurrent execution."""
import asyncio
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.api.deps import get_database_session
from app.core.config import settings
from app.main import app
from app.models.base import Base
from app.models.product import Product
from app.models.action import Action
from app.models.price_history import PriceHistory
from app.models.recommendation import Recommendation
from app.agents.pricing_agent import PricingAgent
from tests.test_promotion import candidate
from tests.test_actions import setup_action

async def test_api_workflow(db_session,async_client):
    scope,p,_=await candidate(db_session)
    rec=await PricingAgent().analyze(scope['low'],db_session)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        request={'merchant_id':scope['merchant'],'agent':'pricing','recommendation':rec.model_dump(mode='json')}
        created=await async_client.post('/api/v1/actions',json=request)
        assert created.status_code==200 and created.json()['status']=='awaiting_approval'
        aid=created.json()['id'];body={'merchant_id':scope['merchant'],'actor':'merchant-demo','comment':'Reviewed'}
        assert (await async_client.get(f'/api/v1/actions/{aid}',params={'merchant_id':scope['other']})).status_code==403
        assert (await async_client.post(f'/api/v1/actions/{aid}/approve',json={'merchant_id':scope['other']})).status_code==403
        assert (await async_client.post(f'/api/v1/actions/{aid}/execute',json={**body,'confirm':True})).status_code==409
        assert (await async_client.post(f'/api/v1/actions/{aid}/approve',json=body)).json()['status']=='approved'
        assert (await async_client.post(f'/api/v1/actions/{aid}/execute',json=body)).status_code==422
        assert (await async_client.post(f'/api/v1/actions/{aid}/execute',json={**body,'confirm':False})).status_code==422
        assert (await async_client.post(f'/api/v1/actions/{aid}/execute',json={**body,'confirm':True})).json()['status']=='executed'
        assert (await async_client.post(f'/api/v1/actions/{aid}/execute',json={**body,'confirm':True})).json()['status']=='executed'
        assert (await async_client.post(f'/api/v1/actions/{aid}/approve',json=body)).status_code==409
        rows=(await async_client.get('/api/v1/actions',params={'merchant_id':scope['merchant']})).json()
        assert len(rows)==1 and rows[0]['approval_required']
        audit=(await async_client.get('/api/v1/action-history',params={'merchant_id':scope['merchant']})).json()
        assert any(row['event_type']=='execution_completed' for row in audit)
        assert (await async_client.get('/api/v1/action-history',params={'merchant_id':scope['other']})).json()==[]
        assert (await async_client.get('/api/v1/actions',params={'merchant_id':scope['other']})).json()==[]
        assert (await async_client.get('/api/v1/actions/9999',params={'merchant_id':scope['merchant']})).status_code==404
    finally: app.dependency_overrides.clear()

async def test_saved_source(db_session,async_client):
    scope,p,_=await candidate(db_session)
    rec=await PricingAgent().analyze(scope['low'],db_session)
    record=Recommendation(merchant_id=scope['merchant'],product_id=rec.product_id,recommendation_type='pricing',title='Saved price',description=rec.reason,recommended_value=rec.model_dump(mode='json'),confidence=rec.confidence)
    db_session.add(record);await db_session.commit()
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        body={'merchant_id':scope['merchant'],'recommendation_id':record.id}
        one=await async_client.post('/api/v1/actions',json=body);two=await async_client.post('/api/v1/actions',json=body)
        assert one.status_code==200 and one.json()['id']==two.json()['id']
        assert await db_session.scalar(select(func.count(Action.id)))==1
    finally: app.dependency_overrides.clear()

@pytest.mark.parametrize('body',[{'merchant_id':1},{'merchant_id':True,'recommendation_id':1},{'merchant_id':1,'recommendation_id':1,'agent':'pricing'},{'merchant_id':1,'agent':'anything','recommendation':{}},{'merchant_id':1,'recommendation_id':1,'auto_execute':True}])
async def test_invalid_creation(async_client,body):
    assert (await async_client.post('/api/v1/actions',json=body)).status_code==422

async def test_production_disabled(async_client,monkeypatch):
    monkeypatch.setattr(settings,'ENVIRONMENT','production')
    r=await async_client.post('/api/v1/actions/1/approve',json={'merchant_id':1})
    assert r.status_code==401

async def test_concurrent_execution(tmp_path,async_client):
    engine=create_async_engine(f'sqlite+aiosqlite:///{tmp_path}/concurrent.sqlite')
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as session:
        scope,pid,created,decision,_=await setup_action(session)
        from app.services.actions.workflow import decide_action
        await decide_action(session,created.id,decision,True)
    async def override():
        async with factory() as session: yield session
    app.dependency_overrides[get_database_session]=override
    try:
        body={**decision.model_dump(),'confirm':True}
        responses=await asyncio.gather(*[async_client.post(f'/api/v1/actions/{created.id}/execute',json=body) for _ in range(2)])
        assert any(r.status_code==200 for r in responses)
        assert all(r.status_code in (200,409,503) for r in responses)
        async with factory() as session:
            assert await session.scalar(select(func.count(PriceHistory.id)))==1
            assert (await session.get(Product,pid)).selling_price==Decimal("1048.95")
            assert (await session.get(Action,created.id)).status=='executed'
    finally:
        app.dependency_overrides.clear();await engine.dispose()

@pytest.mark.parametrize('confirmation', [1, 'true', None])
async def test_confirmation_requires_boolean_true(async_client, confirmation):
    response = await async_client.post('/api/v1/actions/1/execute', json={'merchant_id': 1, 'confirm': confirmation})
    assert response.status_code == 422
