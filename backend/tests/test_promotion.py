"""Promotion economics, history, API scope and read-only behavior."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from app.agents.promotion_agent import PromotionAgent
from app.api.deps import get_database_session
from app.main import app
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.recommendation import Recommendation
from app.schemas.promotion import PromotionPolicy
from app.services.promotion.signals import enrich_promotion_signals, sales_trend
from app.services.pricing.signals import extract_pricing_signals
from app.services.promotion.persistence import generate_and_persist_recommendation
from tests.orchestration_helpers import make_store

async def candidate(session):
    scope=await make_store(session)
    product=await session.get(Product,scope['healthy'])
    product.created_at=scope['as_of']-timedelta(days=60)
    product.selling_price=Decimal('1499');product.cost_price=Decimal('850')
    inv=await session.scalar(select(Inventory).where(Inventory.product_id==product.id));inv.quantity=120
    for i,(days,qty) in enumerate([(10,12),(9,4),(3,1)]):
        order=Order(merchant_id=scope['merchant'],order_number=f'PROMO-{i}',status='delivered',total_amount=1499*qty,ordered_at=scope['as_of']-timedelta(days=days))
        session.add(order);await session.flush()
        session.add(OrderItem(order_id=order.id,product_id=product.id,quantity=qty,unit_price=1499,subtotal=1499*qty))
    await session.commit()
    snapshot=await extract_pricing_signals(product.id,session,14,scope['as_of'])
    return scope,product,await enrich_promotion_signals(snapshot,session,scope['as_of'])

@pytest.mark.parametrize('case',['slow','zero','low','strong','new','inactive','cap','margin','thin','tiny','reserved'])
async def test_decisions(db_session,case):
    _,_,s=await candidate(db_session);policy=PromotionPolicy()
    if case=='zero': s=replace(s,product=replace(s.product,sales_velocity=0,units_sold_lookback=0),recent_units=0,previous_units=0)
    if case=='low': s=replace(s,restock=s.restock.model_copy(update={'available_inventory':5,'risk_level':'high'}))
    if case=='strong': s=replace(s,product=replace(s.product,sales_velocity=5),recent_units=35,previous_units=35)
    if case=='new': s=replace(s,history_days=1)
    if case=='inactive': s=replace(s,product=replace(s.product,status='inactive'))
    if case=='cap': policy=PromotionPolicy(moderate_discount=30)
    if case=='margin': s=replace(s,product=replace(s.product,current_price=Decimal('100'),cost_price=Decimal('90')))
    if case=='thin': s=replace(s,product=replace(s.product,current_price=Decimal('100'),cost_price=Decimal('85')))
    if case=='tiny': s=replace(s,product=replace(s.product,current_price=Decimal('.02'),cost_price=Decimal('.01')))
    if case=='reserved': s=replace(s,restock=s.restock.model_copy(update={'available_inventory':0}))
    rec=PromotionAgent(policy).recommend(s)
    assert rec==PromotionAgent(policy).recommend(s)
    assert 0<=rec.confidence<=1 and rec.discount_percentage<=policy.max_discount_percent
    if rec.promotion_recommended: assert rec.promotional_price>=rec.cost_price/(1-policy.min_margin_percent/100)
    assert rec.promotion_recommended==(case in ['slow','zero','cap','thin'])
    if case=='slow': assert rec.discount_percentage==10 and rec.sales_trend=='declining'
    if case=='thin': assert rec.discount_percentage<10

@pytest.mark.parametrize('recent,previous,expected',[(1,16,'declining'),(16,1,'increasing'),(7,7,'stable'),(1,0,'increasing'),(0,0,'stable')])
async def test_trend(db_session,recent,previous,expected):
    _,_,s=await candidate(db_session)
    assert sales_trend(replace(s,recent_units=recent,previous_units=previous),PromotionPolicy())==expected

@pytest.mark.parametrize('price,cost',[('0','1'),('NaN','1'),('100','-1'),('100','Infinity')])
async def test_invalid_prices(db_session,price,cost):
    _,_,s=await candidate(db_session)
    with pytest.raises(ValueError): PromotionAgent().recommend(replace(s,product=replace(s.product,current_price=Decimal(price),cost_price=Decimal(cost))))

async def test_api_read_only_and_scope(db_session,async_client):
    scope,product,_=await candidate(db_session)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        r=await async_client.post('/api/v1/promotion/recommend',json={'product_id':product.id,'merchant_id':scope['merchant']})
        assert r.status_code==200 and r.json()['promotion_recommended']
        await db_session.refresh(product);assert product.selling_price==1499
        assert (await db_session.scalar(select(Inventory).where(Inventory.product_id==product.id))).quantity==120
        assert await db_session.scalar(select(func.count(Recommendation.id)))==0
        assert (await async_client.post('/api/v1/promotion/recommend',json={'product_id':product.id,'merchant_id':scope['other']})).status_code==403
        assert (await async_client.post('/api/v1/promotion/recommend',json={'product_id':9999})).status_code==404
        assert (await async_client.post('/api/v1/promotion/recommend',json={'product_id':True})).status_code==422
    finally: app.dependency_overrides.clear()

async def test_missing_inventory(db_session):
    _,product,_=await candidate(db_session)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==product.id))
    await db_session.delete(inv);await db_session.commit();db_session.expire(product,['inventory'])
    with pytest.raises(ValueError): await PromotionAgent().analyze(product.id,db_session)

async def test_pending_persistence(db_session):
    _,product,_=await candidate(db_session)
    await generate_and_persist_recommendation(product.id,db_session)
    row=await db_session.scalar(select(Recommendation));assert row.status=='pending' and row.recommendation_type=='promotion'
    await db_session.rollback();assert await db_session.scalar(select(func.count(Recommendation.id)))==0

async def test_database_failure(async_client,monkeypatch):
    async def fail(*args,**kwargs): raise SQLAlchemyError('private connection info')
    monkeypatch.setattr(PromotionAgent,'analyze',fail)
    r=await async_client.post('/api/v1/promotion/recommend',json={'product_id':1})
    assert r.status_code==503 and 'private' not in r.text

async def test_order_scope(db_session):
    scope,product,s=await candidate(db_session)
    rec=PromotionAgent().recommend(replace(s,history_days=0,recent_units=0,previous_units=0,product=replace(s.product,sales_velocity=0,total_historical_orders=0)))
    assert not rec.promotion_recommended and rec.sales_trend=='insufficient_data'
    for i,(merchant,status,days) in enumerate([(scope['other'],'delivered',1),(scope['merchant'],'cancelled',1),(scope['merchant'],'delivered',-1)]):
        order=Order(merchant_id=merchant,order_number=f'EXCLUDE-{i}',status=status,total_amount=1499,ordered_at=scope['as_of']-timedelta(days=days))
        db_session.add(order);await db_session.flush()
        db_session.add(OrderItem(order_id=order.id,product_id=product.id,quantity=100,unit_price=1499,subtotal=149900))
    await db_session.commit()
    rec=await PromotionAgent().analyze(product.id,db_session,scope['as_of']);assert rec.recent_units==1 and rec.previous_units==16

@pytest.mark.parametrize('field,value',[('max_discount_percent',100),('min_margin_percent',100),('lookback_days',1),('high_inventory_days',0)])
def test_policy_validation(field,value):
    with pytest.raises(ValueError): PromotionPolicy(**{field:value})

@pytest.mark.parametrize('changes',[{'promotion_type':'none'},{'promotional_price':Decimal('1')},{'confidence':1.1},{'risk_level':'danger'},{'discount_percentage':100}])
async def test_output_schema(db_session,changes):
    from app.schemas.promotion import PromotionRecommendation
    _,_,s=await candidate(db_session)
    data=PromotionAgent().recommend(s).model_dump();data.update(changes)
    with pytest.raises(ValueError): PromotionRecommendation.model_validate(data)

async def test_no_implicit_flush(db_session):
    _,product,_=await candidate(db_session)
    from app.models.merchant import Merchant
    pending=Merchant(name='Pending',email='pending@promo.test',store_name='Pending')
    db_session.add(pending)
    await PromotionAgent().analyze(product.id,db_session)
    assert pending.id is None

async def test_saved_promotion_payload(db_session):
    from app.services.store.catalog import get_saved_recommendations
    scope,product,_=await candidate(db_session)
    await generate_and_persist_recommendation(product.id,db_session)
    rows=await get_saved_recommendations(db_session,scope['merchant'])
    assert rows[0].payload.promotion_type=='discount'

@pytest.mark.parametrize('case',['missing','invalid_price','reservations'])
async def test_api_invalid_data(db_session,async_client,case):
    _,product,_=await candidate(db_session)
    inv=await db_session.scalar(select(Inventory).where(Inventory.product_id==product.id))
    if case=='missing': await db_session.delete(inv);await db_session.commit();db_session.expire(product,['inventory'])
    if case=='invalid_price': product.selling_price=Decimal(0);await db_session.commit()
    if case=='reservations': inv.reserved_quantity=inv.quantity+1;await db_session.commit()
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try: assert (await async_client.post('/api/v1/promotion/recommend',json={'product_id':product.id})).status_code==422
    finally: app.dependency_overrides.clear()
