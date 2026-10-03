"""Read-only transport, safe mappings, local upserts and normal agent analysis."""
import copy
import json
from decimal import Decimal
import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from app.core.config import Settings
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.shopify import ShopifyConnection, ExternalProductMapping, ExternalOrderMapping
from app.integrations.shopify.client import ShopifyClient, ShopifyError
from app.integrations.shopify.queries import Query, QUERIES
from app.integrations.shopify.schemas import Variant, InventoryItem, SourceOrder, SyncRequest
from app.integrations.shopify.mapper import product_fields, project_inventory, order_status
from app.integrations.shopify.sync import ShopifySyncService
from app.services.pricing.signals import extract_pricing_signals
from app.services.pricing.calculator import calculate_pricing_recommendation
from app.services.restock.signals import restock_signals_from_snapshot
from app.services.restock.calculator import calculate_restock_recommendation
from app.agents.orchestrator import MasterOrchestrator
from app.schemas.orchestration import OrchestrationRequest
from tests.shopify_helpers import ShopifyFixture, connection, variant, inventory, level, order, line

@pytest.fixture
async def source(db_session):
    merchant=Merchant(name='Shopify Fixture',email='fixture@example.test',store_name='Fixture Store')
    db_session.add(merchant);await db_session.commit()
    return ShopifyFixture(merchant.id)

@pytest.mark.parametrize('domain',['https://store.myshopify.com','evil.com','store.myshopify.com/','store.myshopify.com@evil.com','localhost','127.0.0.1','-bad.myshopify.com','a.b.myshopify.com','store.myshopify.com:443','store.myshopify.com?token=x'])
def test_domain_rejected(domain):
    with pytest.raises(ValidationError): Settings(_env_file=None,SHOPIFY_STORE_DOMAIN=domain)

def test_config_secret_and_domain():
    config=Settings(_env_file=None,SHOPIFY_STORE_DOMAIN=' STORE.myshopify.com ',SHOPIFY_ACCESS_TOKEN='fixture-credential')
    assert config.SHOPIFY_STORE_DOMAIN=='store.myshopify.com'
    assert 'fixture-credential' not in repr(config) and 'fixture-credential' not in config.model_dump_json()

def test_mapping_unknown_cost():
    raw=variant(1,'SHIRT');fields=product_fields(Variant.model_validate(raw))
    assert fields['name']=='Cotton Shirt — Small' and fields['category']=='Clothing'
    assert fields['selling_price']==Decimal('100') and fields['cost_price'] is None and fields['source']=='shopify'

@pytest.mark.parametrize('tracked',[True,False])
def test_inventory_locations(tracked):
    raw=inventory();raw['inventoryLevels']=raw['inventoryLevels']['nodes'];raw['tracked']=tracked
    mapped=project_inventory(InventoryItem.model_validate(raw))
    if not tracked: assert mapped is None;return
    assert mapped.quantity==31 and mapped.reserved==4 and mapped.unavailable==2
    assert mapped.quantity-mapped.reserved-mapped.unavailable==25
    assert len(mapped.snapshot['locations'])==3

@pytest.mark.parametrize('financial,fulfillment,status,unknown',[
    ('PAID','FULFILLED','shipped',False),('PAID','UNFULFILLED','confirmed',False),
    ('PENDING','UNFULFILLED','pending',False),('REFUNDED','FULFILLED','cancelled',False),
    ('VOIDED','UNFULFILLED','cancelled',False),('EXPIRED','UNFULFILLED','cancelled',False),
    ('FUTURE_STATE','FULFILLED','cancelled',True),('PAID','FUTURE_STATE','cancelled',True)])
def test_status_mapper(financial,fulfillment,status,unknown):
    raw=order();raw['lineItems']=raw['lineItems']['nodes'];raw.update(displayFinancialStatus=financial,displayFulfillmentStatus=fulfillment)
    assert order_status(SourceOrder.model_validate(raw))==(status,unknown)

async def test_sync_idempotency_and_update(db_session,source):
    service=ShopifySyncService(source.client());request=SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID)
    first=await service.sync(db_session,request)
    assert first.status=='completed' and first.products_created==3 and first.inventory_updated==3 and first.orders_created==1
    source.variants[0]['price']='104.90'
    source.orders[0]['lineItems']['nodes'][0]['currentQuantity']=2
    second=await service.sync(db_session,request)
    assert second.status=='completed' and second.products_updated==3 and second.orders_updated==1 and second.products_created==0
    assert await db_session.scalar(select(func.count(Product.id)))==3
    assert await db_session.scalar(select(func.count(Order.id)))==1
    assert await db_session.scalar(select(func.count(OrderItem.id)))==1
    products=(await db_session.scalars(select(Product).order_by(Product.id))).all()
    assert len({p.sku for p in products})==3 and products[0].selling_price==Decimal('104.90')
    assert products[0].sku=='SHIRT' and products[2].sku=='SHOPIFY-3'
    item=await db_session.scalar(select(OrderItem));assert item.quantity==2 and item.subtotal==200
    row=await db_session.scalar(select(Order));assert row.customer_reference is None and row.status=='confirmed'
    mapping=await db_session.scalar(select(ExternalProductMapping));assert mapping.external_variant_id=='gid://shopify/ProductVariant/1'
    last=await db_session.scalar(select(ShopifyConnection));assert last.last_sync['status']=='completed' and not last.sync_in_progress

async def test_partial_failure_invalidates_stale_inventory(db_session,source):
    service=ShopifySyncService(source.client());request=SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID)
    await service.sync(db_session,request);source.inventory_failure=True
    result=await service.sync(db_session,request)
    assert result.status=='partial' and result.products_updated==3 and result.orders_updated==1
    assert len(result.errors)==3 and all(e.stage=='inventory' for e in result.errors)
    assert await db_session.scalar(select(func.count(Inventory.id)))==0
    db_session.expire_all()
    assert all(p.cost_price is None for p in (await db_session.scalars(select(Product))).all())
    assert len(source.delays)==6

async def test_analysis_all_agents_after_sync(db_session,source):
    result=await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    assert result.status=='completed'
    product_id=await db_session.scalar(select(Product.id).order_by(Product.id))
    signals=await extract_pricing_signals(product_id,db_session)
    assert signals.units_sold_lookback==3 and signals.available_quantity==25
    assert calculate_pricing_recommendation(signals).product_id==product_id
    assert calculate_restock_recommendation(restock_signals_from_snapshot(signals)).available_inventory==25
    plan=await MasterOrchestrator().analyze(OrchestrationRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID,goal='balanced_growth'),db_session)
    assert plan.products_analyzed==3 and plan.approval_required
    assert {r.agent_name for r in plan.agent_results}=={'pricing','restock','promotion','listing'}
    assert all(r.success for r in plan.agent_results)

async def test_unknown_cost_safe_degradation(db_session,source):
    source.cost=None
    await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    product_id=await db_session.scalar(select(Product.id))
    signals=await extract_pricing_signals(product_id,db_session)
    with pytest.raises(ValueError,match='unknown'): calculate_pricing_recommendation(signals)
    assert calculate_restock_recommendation(restock_signals_from_snapshot(signals)).product_id==product_id
    plan=await MasterOrchestrator().analyze(OrchestrationRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID,goal='balanced_growth'),db_session)
    assert any(r.agent_name=='restock' and r.success for r in plan.agent_results)
    assert any(r.agent_name=='listing' and r.success for r in plan.agent_results)
    assert all(not r.success for r in plan.agent_results if r.agent_name in ('pricing','promotion'))

async def test_unmapped_updated_order_excludes_previous_sales(db_session,source):
    service=ShopifySyncService(source.client());req=SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID)
    await service.sync(db_session,req)
    source.orders[0]['lineItems']['nodes'][0]['variant']=None
    result=await service.sync(db_session,req)
    assert result.status=='partial' and result.orders_skipped==1
    assert (await db_session.scalar(select(Order))).status=='cancelled'
    assert await db_session.scalar(select(func.count(OrderItem.id)))==0

async def test_merchant_binding(db_session,source):
    with pytest.raises(ShopifyError,match='selected merchant'):
        await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=999))
    assert not source.calls

async def test_sync_claim(db_session,source):
    db_session.add(ShopifyConnection(merchant_id=source.config.SHOPIFY_MERCHANT_ID,store_domain=source.config.SHOPIFY_STORE_DOMAIN,sync_in_progress=True));await db_session.commit()
    with pytest.raises(ShopifyError,match='already running'):
        await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    assert not source.calls

@pytest.mark.parametrize('status',[401,403])
async def test_auth_sanitized(source,status,caplog):
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:httpx.Response(status,text='fixture-credential')))
    with pytest.raises(ShopifyError,match='Check store domain') as error: await client.connection()
    assert error.value.code=='authentication' and 'fixture-credential' not in str(error.value)+caplog.text

@pytest.mark.parametrize('status',[429,500,502,503])
async def test_retry_limit(source,status):
    calls=[]
    def handler(request): calls.append(request);return httpx.Response(status,headers={'Retry-After':'2'})
    client=ShopifyClient(source.config,transport=httpx.MockTransport(handler),sleep=source.sleep)
    with pytest.raises(ShopifyError,match='retry limit'): await client.connection()
    assert len(calls)==3 and source.delays==[2,2]

async def test_graphql_throttle(source):
    responses=[httpx.Response(200,json={'errors':[{'message':'private','extensions':{'code':'THROTTLED'}}],
        'extensions':{'cost':{'requestedQueryCost':10,'throttleStatus':{'restoreRate':2,'currentlyAvailable':0}}}}),httpx.Response(200,json={'data':{'ok':True}})]
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:responses.pop(0)),sleep=source.sleep)
    assert await client.read(Query.SHOP)=={'ok':True} and source.delays==[5]

@pytest.mark.parametrize('error',[httpx.ConnectError,httpx.ReadTimeout])
async def test_network_bounded(source,error):
    def handler(request): raise error('fixture-credential',request=request)
    client=ShopifyClient(source.config,transport=httpx.MockTransport(handler),sleep=source.sleep)
    with pytest.raises(ShopifyError,match='unavailable') as caught: await client.connection()
    assert source.delays==[1,2] and 'fixture-credential' not in str(caught.value)

@pytest.mark.parametrize('body',[[],{}, {'data':None},{'errors':'bad'},{'errors':[{'extensions':None}]}])
async def test_malformed(source,body):
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body)))
    with pytest.raises(ShopifyError): await client.read(Query.SHOP)

async def test_optional_cost_scope_fallback(source):
    def handler(request):
        if 'unitCost' in json.loads(request.content)['query']:
            return httpx.Response(200,json={'errors':[{'extensions':{'code':'ACCESS_DENIED'},'message':'private'}]})
        return source.handler(request)
    client=ShopifyClient(source.config,transport=httpx.MockTransport(handler))
    item=await client.inventory('gid://shopify/InventoryItem/1')
    assert item['unitCost'] is None and len(item['inventoryLevels'])==3

async def test_all_pagination_dimensions(source):
    client=source.client();variants=[v async for page in client.variants() for v in page]
    assert len(variants)==3 and len((await client.inventory('gid://shopify/InventoryItem/1'))['inventoryLevels'])==3
    def handler(request):
        body=json.loads(request.content)
        if 'query CartPilotOrders' in body['query']:
            raw=order();raw['lineItems']=connection([line()],True,'lines-next')
            return httpx.Response(200,json={'data':{'orders':connection([raw],body['variables']['cursor'] is None,'orders-next')}})
        if 'query CartPilotOrderLines' in body['query']:
            return httpx.Response(200,json={'data':{'order':{'id':'gid://shopify/Order/1','lineItems':connection([line(2,2)])}}})
        return source.handler(request)
    client=ShopifyClient(source.config,transport=httpx.MockTransport(handler))
    pages=[page async for page in client.orders()]
    assert len(pages)==2 and all(len(page[0]['lineItems'])==2 for page in pages)

async def test_cursor_and_page_limits(source):
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'data':{'productVariants':connection([],True,'same')}})))
    with pytest.raises(ShopifyError,match='did not advance'): [page async for page in client.variants()]
    source.config.SHOPIFY_MAX_PAGES=1
    with pytest.raises(ShopifyError,match='limit reached'): [page async for page in source.client().variants()]

async def test_no_write_query_path(source):
    assert all(q.startswith('query ') and 'mutation' not in q.lower() for q in QUERIES.values())
    with pytest.raises(ShopifyError,match='fixed read-only'): await source.client().read('mutation { productUpdate }')
    assert not source.calls

async def test_demo_records_are_preserved(seeded_session):
    merchant_id=await seeded_session.scalar(select(Merchant.id).order_by(Merchant.id))
    before_products=await seeded_session.scalar(select(func.count(Product.id)))
    before_orders=await seeded_session.scalar(select(func.count(Order.id)))
    source=ShopifyFixture(merchant_id)
    await ShopifySyncService(source.client()).sync(seeded_session,SyncRequest(merchant_id=merchant_id))
    assert await seeded_session.scalar(select(func.count(Product.id)))==before_products+3
    assert await seeded_session.scalar(select(func.count(Order.id)))==before_orders+1
    assert await seeded_session.scalar(select(func.count(Product.id)).where(Product.source=='local'))==before_products

async def test_invalid_inventory_cannot_look_sellable(db_session,source):
    source.handler_original=source.handler
    def handler(request):
        response=source.handler_original(request)
        if 'query CartPilotInventory' in json.loads(request.content)['query']:
            body=response.json();body['data']['inventoryItem']['inventoryLevels']['nodes'][0]['quantities'][0]['quantity']=-1
            return httpx.Response(200,json=body)
        return response
    service=ShopifySyncService(ShopifyClient(source.config,transport=httpx.MockTransport(handler)))
    result=await service.sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    assert result.status=='partial' and result.inventory_updated==0
    assert await db_session.scalar(select(func.count(Inventory.id)))==0

async def test_orders_customer_privacy(db_session,source):
    source.orders[0].update(customer={'email':'private@example.test','phone':'private'},shippingAddress={'address1':'private'})
    result=await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    assert result.status=='completed'
    record=await db_session.scalar(select(Order));assert record.customer_reference is None
    last=await db_session.scalar(select(ShopifyConnection))
    assert 'private' not in json.dumps(last.last_sync)
    assert all('customer' not in query and 'shippingAddress' not in query for query in QUERIES.values())

async def test_cancelled_orders_excluded_from_analysis(db_session,source):
    source.orders[0]['cancelledAt']=source.orders[0]['createdAt']
    await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    product_id=await db_session.scalar(select(Product.id))
    signals=await extract_pricing_signals(product_id,db_session)
    assert signals.units_sold_lookback==0

async def test_currency_change_is_refused(db_session,source):
    service=ShopifySyncService(source.client());req=SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID)
    await service.sync(db_session,req)
    record=await db_session.scalar(select(ShopifyConnection));record.currency='INR';await db_session.commit()
    result=await service.sync(db_session,req)
    assert result.status=='failed' and result.errors[0].code=='currency_changed' and result.products_updated==0

async def test_version_fallback_refused(source):
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'data':{}},headers={'X-Shopify-API-Version':'2099-01'})))
    with pytest.raises(ShopifyError,match='different API version'): await client.connection()

async def test_redirect_not_followed(source):
    calls=[]
    def handler(request): calls.append(request);return httpx.Response(302,headers={'Location':'https://evil.example.test'})
    client=ShopifyClient(source.config,transport=httpx.MockTransport(handler))
    with pytest.raises(ShopifyError): await client.connection()
    assert len(calls)==1

async def test_missing_scopes(source):
    def handler(request):
        body=source.handler(request).json();body['data']['currentAppInstallation']['accessScopes']=[]
        return httpx.Response(200,json=body)
    with pytest.raises(ShopifyError,match='read_products'): await ShopifyClient(source.config,transport=httpx.MockTransport(handler)).connection()

async def test_retry_after_http_date(source):
    from datetime import datetime,timedelta,timezone
    from email.utils import format_datetime
    replies=[httpx.Response(429,headers={'Retry-After':format_datetime(datetime.now(timezone.utc)+timedelta(seconds=10))}),httpx.Response(200,json={'data':{'ok':True}})]
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:replies.pop(0)),sleep=source.sleep)
    assert await client.read(Query.SHOP)=={'ok':True} and 8<=source.delays[0]<=10

async def test_long_retry_after_stops(source):
    client=ShopifyClient(source.config,transport=httpx.MockTransport(lambda _:httpx.Response(429,headers={'Retry-After':'600'})),sleep=source.sleep)
    with pytest.raises(ShopifyError,match='long retry delay'): await client.connection()
    assert not source.delays

async def test_guarded_actions_refuse_unknown_cost(db_session,source):
    from app.schemas.actions import PricePayload
    from app.services.policies.validator import validate_policy
    source.cost=None
    await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    product=await db_session.scalar(select(Product).order_by(Product.id))
    payload=PricePayload(product_id=product.id,old_price=100,new_price=105,expected_cost=40)
    result=await validate_policy(payload,product,db_session)
    assert not result.is_valid and 'unknown' in result.violations[0]

async def test_approximate_discounted_unit_prices(db_session,source):
    source.orders[0]['lineItems']['nodes'][0]['discountedUnitPriceAfterAllDiscountsSet']['shopMoney']['amount']='33.333333333333'
    result=await ShopifySyncService(source.client()).sync(db_session,SyncRequest(merchant_id=source.config.SHOPIFY_MERCHANT_ID))
    assert result.status=='completed'
    item=await db_session.scalar(select(OrderItem))
    assert item.unit_price==Decimal('33.33') and item.subtotal==Decimal('100.00')
