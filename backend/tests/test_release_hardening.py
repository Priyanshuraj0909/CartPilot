"""Phase 12 security/failure/integrity regressions; no live network or user DB."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError, OperationalError
from app.main import app
from app.api.deps import get_database_session
from app.core.config import Settings
from app.models.product import Product
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.action import Action, ActionStatus
from app.services.actions.state import TRANSITIONS, transition, ActionError
from app.agents.pricing_agent import PricingAgent
from app.agents.restock_agent import RestockAgent
from tests.cross_agent_helpers import four_products

@pytest.fixture
async def scoped(db_session):
    scope=await four_products(db_session)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    yield scope
    app.dependency_overrides.clear()

@pytest.mark.parametrize('agent',['pricing','restock','promotion','listing'])
async def test_all_agents_reject_foreign_scope(async_client,scoped,agent):
    response=await async_client.post(f'/api/v1/{agent}/recommend',json={'product_id':scoped['products'][0],'merchant_id':999})
    assert response.status_code==403

@pytest.mark.parametrize('agent',['pricing','restock'])
@pytest.mark.parametrize('merchant',[True,-1,'1'])
async def test_strict_merchant_ids(async_client,scoped,agent,merchant):
    assert (await async_client.post(f'/api/v1/{agent}/recommend',json={'product_id':scoped['products'][0],'merchant_id':merchant})).status_code==422

@pytest.mark.parametrize('agent',['pricing','restock'])
async def test_storage_failure_sanitized(async_client,scoped,monkeypatch,agent,caplog):
    module=__import__(f'app.api.v1.{agent}',fromlist=['router'])
    target=getattr(module,f'{agent}_agent')
    async def unavailable(*args,**kwargs): raise OperationalError('private-password',{},Exception('private-password'))
    monkeypatch.setattr(target,'analyze',unavailable)
    response=await async_client.post(f'/api/v1/{agent}/recommend',json={'product_id':scoped['products'][0]})
    assert response.status_code==503
    assert 'private-password' not in response.text+caplog.text

@pytest.mark.parametrize('agent',[PricingAgent,RestockAgent])
async def test_analysis_never_autoflushes_pending_changes(db_session,agent):
    scope=await four_products(db_session)
    product=await db_session.get(Product,scope['products'][0]);product.name='Pending merchant edit'
    await agent().analyze(product.id,db_session)
    assert product in db_session.dirty
    await db_session.rollback()
    stored=await db_session.scalar(select(Product.name).where(Product.id==scope['products'][0]))
    assert stored!='Pending merchant edit'

@pytest.mark.parametrize('db,redis',[(True,True),(False,True),(True,False),(False,False)])
async def test_health_honest_states(async_client,monkeypatch,db,redis):
    async def database(): return db
    async def cache(): return redis
    monkeypatch.setattr('app.api.v1.health.check_db_connection',database)
    monkeypatch.setattr('app.api.v1.health.check_redis_connection',cache)
    result=(await async_client.get('/api/v1/health/detailed')).json()
    assert result['status']==('ok' if db and redis else 'degraded')
    assert result['database']==('connected' if db else 'disconnected')
    assert result['redis']==('connected' if redis else 'disconnected')

async def test_probe_logs_omit_credentials(monkeypatch,caplog):
    from app.core import database,redis
    class BrokenEngine:
        def connect(self): raise RuntimeError('private-password')
    class BrokenRedis:
        async def ping(self): raise RuntimeError('private-password')
    monkeypatch.setattr(database,'engine',BrokenEngine())
    monkeypatch.setattr(redis,'get_redis_client',lambda:BrokenRedis())
    assert not await database.check_db_connection()
    assert not await redis.check_redis_connection()
    assert 'private-password' not in caplog.text

@pytest.mark.parametrize('source',list(ActionStatus))
@pytest.mark.parametrize('target',list(ActionStatus))
def test_all_state_transitions(source,target):
    action=Action(status=source.value)
    if target in TRANSITIONS.get(source,set()):
        transition(action,target);assert action.status==target.value
    else:
        with pytest.raises(ActionError): transition(action,target)
        assert action.status==source.value

async def test_foreign_keys_and_order_cascade(db_session):
    scope=await four_products(db_session)
    db_session.add(OrderItem(order_id=999999,product_id=scope['products'][0],quantity=1,unit_price=1,subtotal=1))
    with pytest.raises(IntegrityError): await db_session.commit()
    await db_session.rollback()
    order_id=await db_session.scalar(select(Order.id).order_by(Order.id))
    assert await db_session.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id==order_id))>0
    await db_session.execute(delete(Order).where(Order.id==order_id));await db_session.commit()
    assert await db_session.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id==order_id))==0

@pytest.mark.parametrize('origin',['*','https://*.example.test'])
def test_production_wildcard_cors_rejected(origin):
    with pytest.raises(ValidationError): Settings(_env_file=None,ENVIRONMENT='production',CORS_ORIGINS=[origin])

def test_known_production_cors_allowed():
    assert Settings(_env_file=None,ENVIRONMENT='production',CORS_ORIGINS=['https://demo.example.test']).CORS_ORIGINS==['https://demo.example.test']

async def test_catalog_reuses_eager_loaded_products(db_session):
    from sqlalchemy import event
    from app.services.store.catalog import get_catalog
    scope=await four_products(db_session)
    statements=[]
    engine=db_session.bind.sync_engine
    def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try: catalog=await get_catalog(db_session,scope['merchant'])
    finally: event.remove(engine,'before_cursor_execute',capture)
    assert catalog.total_products>=4
    product_reads=[s for s in statements if 'FROM products' in s and 'count(' not in s]
    assert len(product_reads)==1  # Catalog page is loaded once, not again for each product.

async def test_catalog_database_timestamps_are_utc(seeded_session):
    from app.services.store.catalog import get_catalog
    from app.models.merchant import Merchant
    merchant_id=await seeded_session.scalar(select(Merchant.id))
    catalog=await get_catalog(seeded_session,merchant_id)
    for product in catalog.products:
        assert product.created_at.tzinfo is not None and product.updated_at.tzinfo is not None
        assert product.inventory.updated_at.tzinfo is not None
        assert all(row.changed_at.tzinfo is not None for row in product.price_history)

async def test_unexpected_failure_response_is_sanitized(monkeypatch,caplog):
    from httpx import ASGITransport,AsyncClient
    async def broken_session():
        raise RuntimeError('private-password')
        yield
    app.dependency_overrides[get_database_session]=broken_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://release') as client:
            result=await client.get('/api/v1/merchants')
            assert result.status_code==500 and 'private-password' not in result.text+caplog.text
    finally: app.dependency_overrides.clear()
