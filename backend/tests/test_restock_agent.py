"""Database integration: shared analytics and strictly advisory behavior."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.agents.restock_agent import RestockAgent
from app.agents.pricing_agent import ProductNotFoundError
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.recommendation import Recommendation
from app.models.action import Action
from app.models.approval import Approval
from app.schemas.restock import RestockPolicy
from app.services.restock.persistence import generate_and_persist_recommendation
from app.services.restock.signals import MissingInventoryError


@pytest.fixture
async def restock_product(db_session):
    merchant = Merchant(name="Restock", email="restock@test.com", store_name="Restock")
    db_session.add(merchant)
    await db_session.flush()
    product = Product(merchant_id=merchant.id, sku="RESTOCK", name="Restock Item", category="Test",
                      cost_price=Decimal("50"), selling_price=Decimal("100"))
    db_session.add(product)
    await db_session.flush()
    inventory = Inventory(product_id=product.id, quantity=50, reserved_quantity=45, reorder_point=10, reorder_quantity=40)
    db_session.add(inventory)
    now = datetime.now(timezone.utc)
    for i in range(7):
        order = Order(merchant_id=merchant.id, order_number=f"RESTOCK-{i}", status="delivered",
                      total_amount=Decimal("800"), ordered_at=now - timedelta(days=i + 1))
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=8,
                                unit_price=Decimal("100"), subtotal=Decimal("800")))
    await db_session.commit()
    return product.id, inventory.id, now


@pytest.mark.asyncio
async def test_agent_reads_shared_signals(db_session, restock_product):
    product_id, _, now = restock_product
    agent = RestockAgent()
    result = await agent.analyze(product_id, db_session, as_of=now)
    assert result.sales_velocity == 4 and result.available_inventory == 5
    assert result.recommended_quantity == 63
    assert result == await agent.analyze(product_id, db_session, as_of=now)
    assert (await db_session.scalar(select(func.count(Recommendation.id)))) == 0


@pytest.mark.asyncio
async def test_no_inventory_or_price_mutation_and_pending_persistence(db_session, restock_product):
    product_id, inventory_id, _ = restock_product
    result = await RestockAgent().analyze(product_id, db_session)
    assert result.recommended_quantity > 0
    await generate_and_persist_recommendation(product_id, db_session)
    await db_session.commit()
    db_session.expire_all()
    inventory = await db_session.get(Inventory, inventory_id)
    product = await db_session.get(Product, product_id)
    assert (inventory.quantity, inventory.reserved_quantity, inventory.reorder_quantity) == (50, 45, 40)
    assert product.selling_price == Decimal("100")
    proposal = (await db_session.execute(select(Recommendation))).scalar_one()
    assert proposal.recommendation_type == "restock" and proposal.status == "pending"
    assert proposal.merchant_id == product.merchant_id
    assert proposal.recommended_value["recommended_quantity"] == result.recommended_quantity
    assert await db_session.scalar(select(func.count(Action.id))) == 0
    assert await db_session.scalar(select(func.count(Approval.id))) == 0
    assert await db_session.scalar(select(func.count(Order.id))) == 7


@pytest.mark.asyncio
async def test_missing_product(db_session):
    with pytest.raises(ProductNotFoundError):
        await RestockAgent().analyze(99999, db_session)


@pytest.mark.asyncio
async def test_missing_inventory(db_session, restock_product):
    product_id, inventory_id, _ = restock_product
    await db_session.delete(await db_session.get(Inventory, inventory_id))
    await db_session.commit()
    db_session.expire_all()
    with pytest.raises(MissingInventoryError):
        await RestockAgent().analyze(product_id, db_session)


@pytest.mark.asyncio
async def test_custom_lookback_reuses_sales_window(db_session, restock_product):
    product_id, _, now = restock_product
    result = await RestockAgent(RestockPolicy(lookback_days=7)).analyze(product_id, db_session, as_of=now)
    assert result.sales_velocity == 8


@pytest.mark.asyncio
async def test_persistence_caller_can_rollback(db_session, restock_product):
    product_id, _, _ = restock_product
    await generate_and_persist_recommendation(product_id, db_session)
    assert await db_session.scalar(select(func.count(Recommendation.id))) == 1
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Recommendation.id))) == 0
