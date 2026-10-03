"""API endpoint tests for Pricing Agent recommendations."""

from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_database_session
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product


@pytest.fixture
async def override_db_dependency(db_session: AsyncSession):
    """Override FastAPI database session dependency with test SQLite session."""
    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_database_session] = _get_test_db
    yield db_session
    app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_pricing_api_happy_path(
    async_client: AsyncClient,
    override_db_dependency: AsyncSession,
):
    """Happy path: POST /api/v1/pricing/recommend returns 200 and structured recommendation."""
    session = override_db_dependency
    merchant = Merchant(name="API Merchant", email="api@test.com", store_name="API Store")
    session.add(merchant)
    await session.flush()

    prod = Product(
        merchant_id=merchant.id,
        sku="SKU-API-001",
        name="API Test Headset",
        category="Electronics",
        cost_price=Decimal("45.00"),
        selling_price=Decimal("99.99"),
    )
    session.add(prod)
    await session.commit()

    response = await async_client.post(
        "/api/v1/pricing/recommend",
        json={"product_id": prod.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == prod.id
    assert float(data["current_price"]) == 99.99
    assert "recommended_price" in data
    assert "reason" in data
    assert "confidence" in data
    assert "risk_level" in data
    assert 0.0 <= data["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_pricing_api_product_not_found(
    async_client: AsyncClient,
    override_db_dependency: AsyncSession,
):
    """Failure case: Requesting a non-existent product ID returns 404 Not Found."""
    response = await async_client.post(
        "/api/v1/pricing/recommend",
        json={"product_id": 999999},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pricing_api_invalid_payload(
    async_client: AsyncClient,
    override_db_dependency: AsyncSession,
):
    """Failure case: Invalid payload (negative or string ID) returns 422 Unprocessable Entity."""
    # Negative product_id
    res_neg = await async_client.post("/api/v1/pricing/recommend", json={"product_id": -5})
    assert res_neg.status_code == 422

    # String product_id
    res_str = await async_client.post("/api/v1/pricing/recommend", json={"product_id": "invalid_id"})
    assert res_str.status_code == 422


@pytest.mark.asyncio
async def test_pricing_api_preserves_actual_catalog_price(
    async_client: AsyncClient,
    override_db_dependency: AsyncSession,
):
    """CRITICAL SAFETY: Verify calling the pricing API does NOT alter Product.selling_price in DB."""
    session = override_db_dependency
    merchant = Merchant(name="Safety Merchant", email="safety@test.com", store_name="Safety Store")
    session.add(merchant)
    await session.flush()

    initial_price = Decimal("150.00")
    prod = Product(
        merchant_id=merchant.id,
        sku="SKU-SAFE-001",
        name="Safety Camera",
        category="Electronics",
        cost_price=Decimal("80.00"),
        selling_price=initial_price,
    )
    session.add(prod)
    await session.commit()

    # Call recommendation API
    response = await async_client.post("/api/v1/pricing/recommend", json={"product_id": prod.id})
    assert response.status_code == 200

    # Directly re-query database to assert catalog price was not mutated
    query = select(Product).where(Product.id == prod.id)
    db_result = await session.execute(query)
    unaltered_product = db_result.scalar_one()

    assert unaltered_product.selling_price == initial_price, (
        f"API VIOLATION: Product price in database was modified from {initial_price} to {unaltered_product.selling_price}!"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("price,cost", [("0", "10"), ("100", "120")])
async def test_pricing_api_rejects_unsafe_prices(async_client, override_db_dependency, price, cost):
    session = override_db_dependency
    merchant = Merchant(name="Invalid", email="invalid@test.com", store_name="Invalid")
    session.add(merchant)
    await session.flush()
    product = Product(merchant_id=merchant.id, sku="INVALID", name="Invalid", category="Test",
                      cost_price=Decimal(cost), selling_price=Decimal(price))
    session.add(product)
    await session.commit()
    response = await async_client.post("/api/v1/pricing/recommend", json={"product_id": product.id})
    assert response.status_code == 422
    await session.refresh(product)
    assert product.selling_price == Decimal(price)


@pytest.mark.asyncio
async def test_missing_inventory_with_strong_sales_holds_price(async_client, override_db_dependency):
    from app.models.order import Order
    from app.models.order_item import OrderItem
    session = override_db_dependency
    merchant = Merchant(name="Missing", email="missing@test.com", store_name="Missing")
    session.add(merchant)
    await session.flush()
    product = Product(merchant_id=merchant.id, sku="MISSING", name="Missing", category="Test",
                      cost_price=Decimal("50"), selling_price=Decimal("100"))
    session.add(product)
    await session.flush()
    order = Order(merchant_id=merchant.id, order_number="MISSING", status="delivered", total_amount=Decimal("2000"))
    session.add(order)
    await session.flush()
    session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=20,
                          unit_price=Decimal("100"), subtotal=Decimal("2000")))
    await session.commit()
    response = await async_client.post("/api/v1/pricing/recommend", json={"product_id": product.id})
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_price"] == data["current_price"] == 100
    assert data["confidence"] == 0.2
    assert data["risk_level"] == "high"
    assert "Inventory data is unavailable" in data["reason"]
