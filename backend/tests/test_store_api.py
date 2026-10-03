"""Read-only dashboard contracts and merchant scoping."""
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.api.deps import get_database_session
from app.main import app
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.recommendation import Recommendation
from tests.orchestration_helpers import make_store
from app.services.pricing.persistence import generate_and_persist_recommendation


@pytest.fixture
async def store_api(db_session):
    async def override():
        yield db_session
    app.dependency_overrides[get_database_session] = override
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_catalog_data_and_scope(async_client, store_api):
    store = await make_store(store_api)
    response = await async_client.get(f"/api/v1/products?merchant_id={store['merchant']}")
    assert response.status_code == 200
    data = response.json()
    assert data['total_products'] == 2 and data['recent_orders'] == 7
    assert Decimal(data['revenue']) == Decimal('69930')
    assert [p['id'] for p in data['products']] == [store['low'], store['healthy']]
    low = data['products'][0]
    assert low['inventory']['available_quantity'] == 8 and low['sales_velocity'] == 5
    assert low['inventory_status'] == 'Critical' and low['stockout_risk']
    assert data['potential_stockouts'] == 1


@pytest.mark.asyncio
async def test_inventory_endpoint(async_client, store_api):
    store = await make_store(store_api)
    response = await async_client.get(f"/api/v1/inventory?merchant_id={store['merchant']}")
    assert response.status_code == 200 and len(response.json()) == 2


@pytest.mark.asyncio
async def test_merchant_list_omits_email(async_client, store_api):
    await make_store(store_api)
    response = await async_client.get('/api/v1/merchants')
    assert response.status_code == 200 and len(response.json()) == 2
    assert 'email' not in response.json()[0]


@pytest.mark.asyncio
async def test_saved_proposals_are_real_and_scoped(async_client, store_api):
    store = await make_store(store_api)
    await generate_and_persist_recommendation(store['low'], store_api)
    await store_api.commit()
    response = await async_client.get(f"/api/v1/recommendations?merchant_id={store['merchant']}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1 and data[0]['status'] == 'pending'
    assert data[0]['payload']['recommended_price'] == 1048.95
    response = await async_client.get(f"/api/v1/recommendations?merchant_id={store['other']}")
    assert response.json() == []


@pytest.mark.asyncio
async def test_catalog_pagination(async_client, store_api):
    store = await make_store(store_api)
    response = await async_client.get(f"/api/v1/products?merchant_id={store['merchant']}&limit=1")
    assert response.json()['has_more'] and len(response.json()['products']) == 1
    response = await async_client.get(f"/api/v1/products?merchant_id={store['merchant']}&limit=1&offset=1")
    assert not response.json()['has_more'] and response.json()['products'][0]['id'] == store['healthy']


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['products', 'inventory', 'recommendations'])
async def test_unknown_merchant(async_client, store_api, path):
    response = await async_client.get(f'/api/v1/{path}?merchant_id=999')
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_endpoints_do_not_mutate(async_client, store_api):
    store = await make_store(store_api)
    prices = (await store_api.execute(select(Product.id, Product.selling_price))).all()
    stock = (await store_api.execute(select(Inventory.id, Inventory.quantity, Inventory.reserved_quantity))).all()
    for path in ['products', 'inventory', 'recommendations']:
        response = await async_client.get(f"/api/v1/{path}?merchant_id={store['merchant']}")
        assert response.status_code == 200
    store_api.expire_all()
    assert (await store_api.execute(select(Product.id, Product.selling_price))).all() == prices
    assert (await store_api.execute(select(Inventory.id, Inventory.quantity, Inventory.reserved_quantity))).all() == stock
    assert await store_api.scalar(select(func.count(Recommendation.id))) == 0


@pytest.mark.asyncio
async def test_foreign_product_reference_is_not_exposed(async_client, store_api):
    store = await make_store(store_api)
    store_api.add(Recommendation(merchant_id=store['merchant'], product_id=store['foreign'],
        recommendation_type='pricing', title='Incorrect foreign reference', confidence=.5, status='pending'))
    await store_api.commit()
    response = await async_client.get(f"/api/v1/recommendations?merchant_id={store['merchant']}")
    assert response.status_code == 200 and response.json() == []


@pytest.mark.asyncio
async def test_missing_and_invalid_inventory_are_readable(async_client, store_api):
    store = await make_store(store_api)
    inventory = (await store_api.execute(select(Inventory).where(Inventory.product_id == store['low']))).scalar_one()
    inventory.reserved_quantity = inventory.quantity + 1
    healthy_inventory = (await store_api.execute(select(Inventory).where(Inventory.product_id == store['healthy']))).scalar_one()
    await store_api.delete(healthy_inventory)
    await store_api.commit()
    store_api.expire_all()
    response = await async_client.get(f"/api/v1/products?merchant_id={store['merchant']}")
    assert response.status_code == 200
    assert [item['inventory_status'] for item in response.json()['products']] == ['Invalid', 'Missing']
