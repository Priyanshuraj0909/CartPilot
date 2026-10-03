"""Listing quality, grounding, API scope, persistence and no-write guarantees."""
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from app.agents.listing_agent import ListingAgent
from app.api.deps import get_database_session
from app.main import app
from app.models.product import Product
from app.models.merchant import Merchant
from app.models.recommendation import Recommendation
from app.schemas.listing import ListingPolicy, ListingRecommendation
from app.services.listing.signals import ListingSignals
from app.services.listing.persistence import generate_and_persist_recommendation
from tests.orchestration_helpers import make_store


def listing(**changes) -> ListingSignals:
    values = dict(product_id=1,merchant_id=1,title='Wireless Mouse',description='2.4 GHz wireless mouse with USB receiver',category='Electronics',sku='MOUSE-001',current_price=Decimal('100'),status='active')
    values.update(changes)
    return ListingSignals(**values)


@pytest.mark.parametrize('title,description,issue',[
    ('Mouse','Wireless mouse.','Title is too short'),
    ('Wireless Mouse','','Description is missing'),
    ('Wireless Mouse',None,'Description is missing'),
    ('Wireless Mouse','Wireless Mouse.','Description duplicates the title'),
    ('  Wireless   Mouse  ','Useful details.','Title formatting needs cleanup'),
    ('Wireless Mouse','<p>2.4 GHz wireless mouse</p>','Description formatting needs cleanup'),
])
def test_quality_issues(title,description,issue):
    rec=ListingAgent().recommend(listing(title=title,description=description))
    assert issue in rec.issues and 0<=rec.quality_score<=1 and 0<=rec.confidence<=1
    assert rec.recommended_description.strip()


def test_good_listing_preserved():
    s=listing(title='2.4 GHz Wireless Mouse with USB Receiver',description='2.4 GHz wireless mouse with a USB receiver, compatible with Windows. Battery powered, with dimensions of 10 cm. Use the receiver to connect to your computer.')
    rec=ListingAgent().recommend(s)
    assert rec.quality_score==1 and not rec.issues
    assert rec.recommended_title==s.title and rec.recommended_description==s.description
    assert rec.risk_level=='low'


@pytest.mark.parametrize('description',['2.4 GHz wireless mouse with USB receiver','Not Bluetooth compatible. Wireless mouse with USB receiver.','<script>Bluetooth RGB rechargeable battery silent click</script>2.4 GHz wireless mouse with USB receiver'])
def test_no_hallucinations(description):
    rec=ListingAgent().recommend(listing(description=description))
    output=f'{rec.recommended_title} {rec.recommended_description}'
    if 'Not Bluetooth' in description:
        assert 'Not Bluetooth compatible' in output
    else:
        assert 'Bluetooth' not in output
    for feature in ['RGB','rechargeable','silent click','16000 DPI']: assert feature not in output


def test_insufficient_context():
    rec=ListingAgent().recommend(listing(title='Product',description=None,category=None,sku='P-1'))
    assert rec.risk_level=='high' and rec.confidence==.2 and rec.category_consistency=='missing'
    assert 'Verify the product category' in ' '.join(rec.suggestions)


@pytest.mark.parametrize('category,expected',[('Electronics','consistent'),('Clothing','inconsistent'),('Specialty','unverified'),('', 'missing')])
def test_category(category,expected):
    rec=ListingAgent().recommend(listing(category=category))
    assert rec.category_consistency==expected


def test_missing_attributes_are_verification_requests():
    rec=ListingAgent().recommend(listing())
    assert 'connectivity' not in rec.missing_attributes and 'power' in rec.missing_attributes
    assert 'Verify and add power details if applicable.' in rec.suggestions
    assert 'battery' not in rec.recommended_description


def test_determinism_and_keywords_grounded():
    s=listing();rec=ListingAgent().recommend(s)
    assert rec==ListingAgent().recommend(s)
    assert set(rec.recommended_keywords)<={'wireless','mouse','electronics'}


@pytest.mark.parametrize('changes',[{'title':''},{'title':'   '},{'current_price':Decimal('NaN')},{'current_price':Decimal('-1')}])
def test_invalid_source(changes):
    with pytest.raises(ValueError): ListingAgent().recommend(listing(**changes))


@pytest.mark.parametrize('changes',[{'min_title_length':121},{'max_title_length':0},{'min_description_length':2001},{'poor_quality_threshold':1.1}])
def test_invalid_policy(changes):
    with pytest.raises(ValueError): ListingPolicy(**changes)


def test_long_content_does_not_cut_claims():
    rec=ListingAgent().recommend(listing(title='A'*250,description='Not waterproof '+ 'x'*2100))
    assert rec.recommended_title=='Product — MOUSE-001'
    assert rec.recommended_description=='Listing details require merchant verification.'
    assert 'waterproof' not in rec.recommended_description


@pytest.mark.parametrize('changes',[{'recommended_title':''},{'recommended_description':' '},{'quality_score':1.01},{'confidence':-.1},{'risk_level':'unsafe'},{'recommended_title':'x'*121}])
def test_schema_bounds(changes):
    data=ListingAgent().recommend(listing()).model_dump();data.update(changes)
    with pytest.raises(ValueError): ListingRecommendation.model_validate(data)


async def test_api_read_only_and_scope(db_session,async_client):
    scope=await make_store(db_session)
    p=await db_session.get(Product,scope['low']);before=(p.name,p.description,p.selling_price,p.category)
    async def override(): yield db_session
    app.dependency_overrides[get_database_session]=override
    try:
        for _ in range(2):
            r=await async_client.post('/api/v1/listing/recommend',json={'product_id':p.id,'merchant_id':scope['merchant']})
            assert r.status_code==200 and r.json()['recommended_description']
        await db_session.refresh(p);assert (p.name,p.description,p.selling_price,p.category)==before
        assert await db_session.scalar(select(func.count(Recommendation.id)))==0
        assert (await async_client.post('/api/v1/listing/recommend',json={'product_id':p.id,'merchant_id':scope['other']})).status_code==403
        assert (await async_client.post('/api/v1/listing/recommend',json={'product_id':9999})).status_code==404
        assert (await async_client.post('/api/v1/listing/recommend',json={'product_id':True})).status_code==422
        p.name='';await db_session.commit()
        assert (await async_client.post('/api/v1/listing/recommend',json={'product_id':p.id})).status_code==422
    finally: app.dependency_overrides.clear()


async def test_no_implicit_flush(db_session):
    scope=await make_store(db_session)
    pending=Merchant(name='Pending',email='pending@listing.test',store_name='Pending')
    db_session.add(pending)
    await ListingAgent().analyze(scope['low'],db_session)
    assert pending.id is None


async def test_pending_persistence_rollback(db_session):
    scope=await make_store(db_session)
    await generate_and_persist_recommendation(scope['low'],db_session)
    row=await db_session.scalar(select(Recommendation))
    assert row.status=='pending' and row.recommendation_type=='listing'
    await db_session.rollback();assert await db_session.scalar(select(func.count(Recommendation.id)))==0


async def test_database_failure(async_client,monkeypatch):
    async def fail(*args,**kwargs): raise SQLAlchemyError('private connection details')
    monkeypatch.setattr(ListingAgent,'analyze',fail)
    r=await async_client.post('/api/v1/listing/recommend',json={'product_id':1})
    assert r.status_code==503 and 'private' not in r.text
