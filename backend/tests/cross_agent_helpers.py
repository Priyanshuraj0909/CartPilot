"""Four-product merchant fixture for goal-driven planning and isolated demos."""
from datetime import timedelta
from decimal import Decimal
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from tests.test_promotion import candidate

GOOD_DESCRIPTION = 'Wireless USB connectivity with battery power, compatible with Windows and macOS. Dimensions: 12 cm. Verified product details supplied by the merchant.'

async def four_products(session):
    scope, speaker, _ = await candidate(session)
    mouse = await session.get(Product, scope['low'])
    mouse.description = GOOD_DESCRIPTION
    speaker.name = 'Bluetooth Speaker Desktop Audio'
    speaker.description = GOOD_DESCRIPTION
    products = [mouse, speaker]
    for name, stock, description, recent in [
        ('Headphones', 50, None, 1),
        ('Keyboard Desktop USB Wired', 20, GOOD_DESCRIPTION, 7),
    ]:
        p = Product(merchant_id=scope['merchant'], sku=f'PH10-{len(products)}', name=name,
            category='Electronics', cost_price=Decimal('500'), selling_price=Decimal('999'),
            description=description, created_at=scope['as_of']-timedelta(days=60))
        session.add(p); await session.flush()
        session.add(Inventory(product_id=p.id, quantity=stock, reserved_quantity=0, reorder_point=10, reorder_quantity=40))
        for index, (days, quantity) in enumerate([(40,2), (30,2), (3,recent)]):
            order = Order(merchant_id=scope['merchant'], order_number=f'PH10-{p.id}-{index}', status='delivered',
                total_amount=999*quantity, ordered_at=scope['as_of']-timedelta(days=days))
            session.add(order); await session.flush()
            session.add(OrderItem(order_id=order.id, product_id=p.id, quantity=quantity, unit_price=999, subtotal=999*quantity))
        products.append(p)
    await session.commit()
    scope['products'] = [p.id for p in products]
    return scope
