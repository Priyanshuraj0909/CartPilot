"""Shared database demo setup for orchestration tests."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem


async def make_store(session):
    now = datetime.now(timezone.utc)
    merchant = Merchant(name="Demo", email="demo-orch@test.com", store_name="Demo")
    other = Merchant(name="Other", email="other-orch@test.com", store_name="Other")
    session.add_all([merchant, other])
    await session.flush()
    products = []
    for index, owner in enumerate([merchant, merchant, other]):
        product = Product(merchant_id=owner.id, sku=f"ORCH-{index}", name="Wireless Mouse" if index == 0 else "Healthy Product",
                          category="Electronics", cost_price=Decimal("500"), selling_price=Decimal("999"))
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=12 if index == 0 else 100,
                              reserved_quantity=4 if index == 0 else 0, reorder_point=10, reorder_quantity=40))
        products.append(product)
    for index in range(7):
        order = Order(merchant_id=merchant.id, order_number=f"DEMO-{index}", status="delivered",
                      total_amount=Decimal("9990"), ordered_at=now - timedelta(days=index + 1))
        session.add(order)
        await session.flush()
        session.add(OrderItem(order_id=order.id, product_id=products[0].id, quantity=10,
                              unit_price=Decimal("999"), subtotal=Decimal("9990")))
    await session.commit()
    return {"merchant": merchant.id, "other": other.id, "low": products[0].id,
            "healthy": products[1].id, "foreign": products[2].id, "as_of": now}
