"""Development-only API, merchant scoping and non-secret summaries."""
import httpx
import pytest
from app.api.deps import get_database_session
from app.api.v1 import shopify
from app.core.config import settings
from app.main import app
from app.models.merchant import Merchant
from app.integrations.shopify.client import ShopifyClient
from tests.shopify_helpers import ShopifyFixture

@pytest.fixture
async def configured(db_session, monkeypatch):
    merchant=Merchant(name='Fixture',email='api@example.test',store_name='Fixture');db_session.add(merchant);await db_session.commit()
    source=ShopifyFixture(merchant.id)
    for key in ('SHOPIFY_STORE_DOMAIN','SHOPIFY_ACCESS_TOKEN','SHOPIFY_MERCHANT_ID'):
        monkeypatch.setattr(settings,key,getattr(source.config,key))
    monkeypatch.setattr(shopify,'build_client',source.client)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    yield source
    app.dependency_overrides.clear()

async def test_connection_sync_summary(async_client,configured):
    response=await async_client.get('/api/v1/integrations/shopify/status?merchant_id=1')
    assert response.status_code==200 and response.json()['connected'] and response.json()['mode']=='read_only'
    assert 'fixture-credential' not in response.text
    assert (await async_client.get('/api/v1/integrations/shopify/last-sync?merchant_id=1')).json() is None
    response=await async_client.post('/api/v1/integrations/shopify/sync',json={'merchant_id':1})
    assert response.status_code==200 and response.json()['status']=='completed'
    last=await async_client.get('/api/v1/integrations/shopify/last-sync?merchant_id=1')
    assert last.json()==response.json()

async def test_foreign_binding(async_client,configured):
    status=await async_client.get('/api/v1/integrations/shopify/status?merchant_id=2')
    assert not status.json()['configured'] and status.json()['store'] is None
    response=await async_client.post('/api/v1/integrations/shopify/sync',json={'merchant_id':2})
    assert response.status_code==403
    assert (await async_client.get('/api/v1/integrations/shopify/last-sync?merchant_id=2')).status_code==403
    assert not configured.calls

@pytest.mark.parametrize('body',[{}, {'merchant_id':1,'products':False,'inventory':False,'orders':False},
    {'merchant_id':1,'token':'anything'}, {'merchant_id':1,'orders':'true'}, {'merchant_id':True}])
async def test_invalid_requests(async_client,configured,body):
    assert (await async_client.post('/api/v1/integrations/shopify/sync',json=body)).status_code==422
    assert not configured.calls

async def test_remote_auth_failure_is_saved(async_client,configured,monkeypatch):
    monkeypatch.setattr(shopify,'build_client',lambda:ShopifyClient(configured.config,transport=httpx.MockTransport(lambda _:httpx.Response(401,text='fixture-credential'))))
    status=await async_client.get('/api/v1/integrations/shopify/status?merchant_id=1')
    assert status.status_code==200 and not status.json()['connected'] and 'Check store domain' in status.json()['message']
    synced=await async_client.post('/api/v1/integrations/shopify/sync',json={'merchant_id':1})
    assert synced.json()['status']=='failed' and synced.json()['errors'][0]['code']=='authentication'
    assert 'fixture-credential' not in status.text+synced.text
    last=await async_client.get('/api/v1/integrations/shopify/last-sync?merchant_id=1')
    assert last.json()['status']=='failed'

async def test_production_blocked(async_client,configured,monkeypatch):
    monkeypatch.setattr(settings,'ENVIRONMENT','production')
    assert (await async_client.get('/api/v1/integrations/shopify/status?merchant_id=1')).status_code==403
    assert (await async_client.post('/api/v1/integrations/shopify/sync',json={'merchant_id':1})).status_code==403
    assert not configured.calls

async def test_not_configured_preserves_demo(async_client,configured,monkeypatch):
    monkeypatch.setattr(settings,'SHOPIFY_STORE_DOMAIN','')
    response=await async_client.get('/api/v1/integrations/shopify/status?merchant_id=1')
    assert response.status_code==200 and not response.json()['configured']
    assert not configured.calls
