"""Restock API validation and safety contracts."""
from decimal import Decimal
import pytest
from sqlalchemy import func, select
from app.api.deps import get_database_session
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.recommendation import Recommendation


@pytest.fixture
async def restock_api_session(db_session):
    async def override():
        yield db_session
    app.dependency_overrides[get_database_session] = override
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_database_session, None)


async def create_product(session, quantity=50, reserved=45, units=56, inventory=True):
    merchant = Merchant(name="Restock API", email="restock-api@test.com", store_name="Test")
    session.add(merchant)
    await session.flush()
    product = Product(merchant_id=merchant.id, sku="TEST", name="Test", category="Test",
                      cost_price=Decimal("50"), selling_price=Decimal("100"))
    session.add(product)
    await session.flush()
    if inventory:
        session.add(Inventory(product_id=product.id, quantity=quantity, reserved_quantity=reserved, reorder_point=10, reorder_quantity=40))
    if units:
        order = Order(merchant_id=merchant.id, order_number="TEST", status="confirmed", total_amount=Decimal(units * 100))
        session.add(order)
        await session.flush()
        session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=units, unit_price=Decimal("100"), subtotal=Decimal(units * 100)))
    await session.commit()
    return product.id


@pytest.mark.asyncio
async def test_api_happy_path_and_no_mutation(async_client, restock_api_session):
    session = restock_api_session
    product_id = await create_product(session)
    response = await async_client.post("/api/v1/restock/recommend", json={"product_id": product_id})
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_quantity"] == 63
    assert data["available_inventory"] == 5 and data["risk_level"] == "high"
    assert data["sales_velocity"] == data["estimated_daily_sales"] == 4
    session.expire_all()
    inventory = (await session.execute(select(Inventory))).scalar_one()
    assert (inventory.quantity, inventory.reserved_quantity) == (50, 45)
    product = await session.get(Product, product_id)
    assert product.selling_price == Decimal("100")
    assert await session.scalar(select(func.count(Recommendation.id))) == 0


@pytest.mark.asyncio
async def test_unknown_product(async_client, restock_api_session):
    response = await async_client.post("/api/v1/restock/recommend", json={"product_id": 999})
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"product_id": -1}, {"product_id": 0}, {"product_id": True}, {"product_id": "1"}, {"product_id": 1.5}])
async def test_invalid_request(async_client, restock_api_session, payload):
    response = await async_client.post("/api/v1/restock/recommend", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_inventory_error(async_client, restock_api_session):
    product_id = await create_product(restock_api_session, inventory=False)
    response = await async_client.post("/api/v1/restock/recommend", json={"product_id": product_id})
    assert response.status_code == 422
    assert "no inventory record" in response.json()["detail"]


@pytest.mark.asyncio
async def test_impossible_reserved_inventory(async_client, restock_api_session):
    product_id = await create_product(restock_api_session, quantity=5, reserved=10)
    response = await async_client.post("/api/v1/restock/recommend", json={"product_id": product_id})
    assert response.status_code == 422
    assert "Reserved inventory" in response.json()["detail"]


@pytest.mark.asyncio
async def test_zero_demand_json_null(async_client, restock_api_session):
    product_id = await create_product(restock_api_session, quantity=5, reserved=0, units=0)
    response = await async_client.post("/api/v1/restock/recommend", json={"product_id": product_id})
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_days_remaining"] is None
    assert data["recommended_quantity"] == 0 and data["confidence"] == 0.2
