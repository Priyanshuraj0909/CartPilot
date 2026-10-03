from datetime import datetime,timezone,timedelta
import hashlib
import pytest
from app.api.deps import get_database_session
from app.main import app
from app.core.config import settings
from app.models.account import AccountSession
from app.models.product import Product

@pytest.fixture
async def account_client(async_client,db_session,monkeypatch):
    async def override():yield db_session
    app.dependency_overrides[get_database_session]=override
    monkeypatch.setattr(settings,'REQUIRE_AUTH',True)
    try:yield async_client,db_session
    finally:app.dependency_overrides.clear()

async def signup(c,email='owner@example.test'):
    r=await c.post('/api/v1/auth/signup',json={'email':email,'password':'correct horse battery staple','name':'Owner','store_name':'Store'})
    assert r.status_code==201,r.text
    return {'Authorization':'Bearer '+r.json()['token']},r.json()

async def test_account_lifecycle(account_client):
    c,s=account_client
    assert (await c.get('/api/v1/merchants')).status_code==401
    h,d=await signup(c)
    assert len((await c.get('/api/v1/merchants',headers=h)).json())==1
    assert (await c.get('/api/v1/products?merchant_id=999',headers=h)).status_code==403
    assert (await c.post('/api/v1/auth/login',json={'email':'owner@example.test','password':'wrong long password'})).status_code==401
    assert (await c.post('/api/v1/auth/logout',headers=h)).status_code==200
    assert (await c.get('/api/v1/auth/me',headers=h)).status_code==401
    r=await c.post('/api/v1/auth/login',json={'email':'owner@example.test','password':'correct horse battery staple'});assert r.status_code==200
    token=r.json()['token'];record=await s.get(AccountSession,hashlib.sha256(token.encode()).hexdigest());record.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);await s.commit()
    assert (await c.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+token})).status_code==401

async def test_merchant_workflow(account_client):
    c,s=account_client;h,d=await signup(c)
    p={'sku':'SKU','name':'Mouse','category':'Electronics','cost_price':'10.00','selling_price':'20.00','quantity':5}
    r=await c.post('/api/v1/products',headers=h,json=p);assert r.status_code==201,r.text
    pid=r.json()['id']
    assert (await c.post('/api/v1/products',headers=h,json=p)).status_code==409
    assert (await c.put(f'/api/v1/products/{pid}',headers=h,json={**p,'selling_price':'21.00'})).status_code==200
    other,_=await signup(c,'other@example.test')
    assert (await c.put(f'/api/v1/products/{pid}',headers=other,json=p)).status_code==404
    assert (await c.post('/api/v1/pricing/recommend',headers=other,json={'product_id':pid})).status_code==403
    sale={'reference':'sale-1','product_id':pid,'quantity':2,'unit_price':'20.00','ordered_at':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}
    for expected in [{'imported':1,'skipped':0},{'imported':0,'skipped':1}]:
        assert (await c.post('/api/v1/sales/import',headers=h,json={'sales':[sale]})).json()==expected
    assert (await c.post('/api/v1/sales/import',headers=h,json={'sales':[{**sale,'quantity':3}]})).status_code==409
    assert (await c.get('/api/v1/analytics',headers=h)).json()['total_revenue']=='40.00'
    assert (await c.get('/api/v1/notifications',headers=h)).json()['notifications']
    assert (await c.delete(f'/api/v1/products/{pid}',headers=h)).status_code==200
    assert (await s.get(Product,pid)).status=='archived'

async def test_validation(account_client):
    c,_=account_client
    assert (await c.post('/api/v1/auth/signup',json={'email':'bad','password':'short','name':'','store_name':''})).status_code==422
    h,_=await signup(c)
    assert (await c.post('/api/v1/products',headers=h,json={'sku':'bad'})).status_code==422
    assert (await c.post('/api/v1/sales/import',headers=h,json={'sales':[]})).status_code==422

async def test_authenticated_production_gates(account_client,monkeypatch):
    c,_=account_client;h,_=await signup(c)
    monkeypatch.setattr(settings,'ENVIRONMENT','production')
    assert (await c.post('/api/v1/actions',headers=h,json={})).status_code==403
    assert (await c.get('/api/v1/integrations/shopify/status?merchant_id=1',headers=h)).status_code==403

async def test_new_store_five_products_analysis(account_client):
    c,_=account_client;h,data=await signup(c)
    for i in range(5):
        r=await c.post('/api/v1/products',headers=h,json={'sku':f'NEW-{i}','name':f'Desktop accessory {i}','category':'Electronics','cost_price':'10.00','selling_price':'20.00','quantity':20})
        assert r.status_code==201
    mid=data['user']['merchant_id']
    catalog=await c.get(f'/api/v1/products?merchant_id={mid}',headers=h)
    assert len(catalog.json()['products'])==5
    plan=await c.post('/api/v1/orchestrate',headers=h,json={'merchant_id':mid,'goal':'balanced_growth'})
    assert plan.status_code==200,plan.text
    assert plan.json()['products_analyzed']==5
