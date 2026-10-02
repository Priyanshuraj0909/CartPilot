"""Database seeding utility generating realistic e-commerce mock datasets.

Generates:
- 1 Storefront Merchant
- 25 Diverse catalog products
- Realistic inventory levels (including edge conditions for low stock)
- 110 Historical orders with multi-item order lines
- Historical price modification events
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import random
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import Base
from app.models.inventory import Inventory
from app.models.merchant import Merchant
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.price_history import PriceHistory
from app.models.product import Product

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cartpilot.seed")

# Deterministic seed for reproducible mock generation
SEED_RANDOM = random.Random(42)

SAMPLE_PRODUCTS_DATA = [
    # Electronics
    ("SKU-EL-001", "Wireless Noise-Canceling Headphones", "Premium over-ear headphones with 40h battery.", "Electronics", Decimal("85.00"), Decimal("199.99"), 45, 3, 15, 50),
    ("SKU-EL-002", "Smart Fitness Tracker Watch", "Waterproof fitness watch with heart rate and sleep tracking.", "Electronics", Decimal("35.00"), Decimal("79.99"), 85, 5, 20, 60),
    ("SKU-EL-003", "Ultra-Slim Mechanical Keyboard", "Low-profile RGB mechanical keyboard with brown switches.", "Electronics", Decimal("45.00"), Decimal("119.50"), 12, 2, 15, 40), # Low stock
    ("SKU-EL-004", "4K Ultra-HD Webcam", "Autofocus stream camera with stereo noise-canceling mic.", "Electronics", Decimal("28.00"), Decimal("69.99"), 60, 4, 15, 45),
    ("SKU-EL-005", "10-in-1 USB-C Multiport Hub", "Aluminum docking hub with HDMI, Ethernet, and 100W PD.", "Electronics", Decimal("18.00"), Decimal("49.99"), 110, 8, 25, 75),

    # Apparel
    ("SKU-AP-001", "Weatherproof Commuter Jacket", "Breathable waterproof hooded shell for all-season cycling.", "Apparel", Decimal("55.00"), Decimal("145.00"), 30, 2, 10, 30),
    ("SKU-AP-002", "Merino Wool Baselayer Crew", "100% Merino wool thermal long-sleeve athletic top.", "Apparel", Decimal("32.00"), Decimal("78.00"), 8, 1, 15, 35), # Critically low stock
    ("SKU-AP-003", "Organic Cotton Everyday Tee", "Pre-shrunk heavyweight combed organic cotton t-shirt.", "Apparel", Decimal("8.50"), Decimal("26.00"), 240, 15, 40, 100),
    ("SKU-AP-004", "Water-Repellent Cargo Joggers", "Stretch performance joggers with zippered utility pockets.", "Apparel", Decimal("22.00"), Decimal("64.00"), 75, 4, 20, 50),
    ("SKU-AP-005", "All-Weather Transit Backpack 28L", "Ballistic nylon commuter backpack with padded laptop sleeve.", "Apparel", Decimal("42.00"), Decimal("110.00"), 25, 3, 10, 25),

    # Home & Kitchen
    ("SKU-HK-001", "Precision Cold Brew Coffee Maker", "Glass pitcher with fine laser-cut stainless steel filter.", "Home & Kitchen", Decimal("12.00"), Decimal("34.99"), 95, 6, 20, 50),
    ("SKU-HK-002", "Pre-Seasoned Cast Iron Skillet 10in", "Heavy-duty cast iron pan with silicone handle holder.", "Home & Kitchen", Decimal("16.00"), Decimal("39.99"), 50, 2, 15, 40),
    ("SKU-HK-003", "Digital Kitchen Gram Scale", "High-precision 0.1g kitchen scale with tare function.", "Home & Kitchen", Decimal("9.00"), Decimal("24.50"), 130, 7, 25, 60),
    ("SKU-HK-004", "Ceramic Pour-Over Coffee Dripper", "Artisan ceramic dripper for consistent slow-drip brewing.", "Home & Kitchen", Decimal("7.50"), Decimal("22.00"), 40, 1, 15, 30),
    ("SKU-HK-005", "Insulated Stainless Tumbler 24oz", "Vacuum-insulated travel mug with spill-resistant lid.", "Home & Kitchen", Decimal("8.00"), Decimal("28.00"), 180, 10, 30, 80),

    # Sports & Outdoors
    ("SKU-SO-001", "Carbon Fiber Trekking Poles", "Collapsible ultralight hiking poles with cork grips.", "Sports & Outdoors", Decimal("24.00"), Decimal("65.00"), 14, 2, 15, 30), # Low stock
    ("SKU-SO-002", "Hydration Running Vest 5L", "Breathable trail running vest including two 500ml flasks.", "Sports & Outdoors", Decimal("29.00"), Decimal("74.99"), 42, 3, 15, 40),
    ("SKU-SO-003", "Compact Parachute Camping Hammock", "Double camping hammock with tree-friendly straps and carabiners.", "Sports & Outdoors", Decimal("14.00"), Decimal("36.00"), 88, 5, 20, 50),
    ("SKU-SO-004", "Stainless Bike Multi-Tool 16-in-1", "Pocket tool featuring allen hex keys, spoke wrenches, chain tool.", "Sports & Outdoors", Decimal("11.00"), Decimal("29.99"), 92, 4, 20, 50),
    ("SKU-SO-005", "Quick-Dry Antimicrobial Towel", "Fast-absorbing compact microfiber towel for gym and travel.", "Sports & Outdoors", Decimal("6.00"), Decimal("18.00"), 150, 8, 30, 60),

    # Workspace & Office
    ("SKU-WO-001", "Vegan Leather Desk Mat 36x18in", "Water-resistant smooth desk pad with non-slip suede base.", "Workspace", Decimal("10.00"), Decimal("28.50"), 120, 6, 25, 60),
    ("SKU-WO-002", "Ergonomic Aluminum Laptop Stand", "Adjustable folding laptop riser with ventilation cutouts.", "Workspace", Decimal("15.00"), Decimal("42.00"), 65, 4, 15, 40),
    ("SKU-WO-003", "Anti-Blue Light Computer Glasses", "Lightweight TR90 frames with anti-reflective coating.", "Workspace", Decimal("7.00"), Decimal("25.00"), 110, 5, 20, 50),
    ("SKU-WO-004", "Cable Management Spine & Tray", "Under-desk modular cable spine and power strip holder.", "Workspace", Decimal("12.50"), Decimal("32.00"), 55, 3, 15, 35),
    ("SKU-WO-005", "LED Screen Bar Monitor Light", "Asymmetric optical monitor lamp with touch brightness dial.", "Workspace", Decimal("21.00"), Decimal("58.00"), 9, 1, 15, 35), # Low stock
]


async def seed_database(session: AsyncSession) -> Tuple[Merchant, List[Product], List[Order]]:
    """Populate database with merchant, 25 products, inventory, and 110 orders."""
    logger.info("Checking for existing merchant records...")
    result = await session.execute(select(Merchant).where(Merchant.email == "owner@apexstorefront.com"))
    existing_merchant = result.scalar_one_or_none()

    if existing_merchant is not None:
        logger.info("Existing merchant found (id=%d). Skipping seed to preserve existing records.", existing_merchant.id)
        prod_res = await session.execute(select(Product).where(Product.merchant_id == existing_merchant.id))
        products = list(prod_res.scalars().all())
        order_res = await session.execute(select(Order).where(Order.merchant_id == existing_merchant.id))
        orders = list(order_res.scalars().all())
        return existing_merchant, products, orders

    # 1. Create Default Merchant
    merchant = Merchant(
        name="Elena Rostova",
        email="owner@apexstorefront.com",
        store_name="Apex Commerce Store",
    )
    session.add(merchant)
    await session.flush()
    logger.info("Created Merchant: %s (id=%d)", merchant.store_name, merchant.id)

    # 2. Create 25 Catalog Products & Inventory
    created_products: List[Product] = []
    now_utc = datetime.now(timezone.utc)

    for item in SAMPLE_PRODUCTS_DATA:
        sku, name, desc, category, cost, price, stock_qty, reserved_qty, reorder_pt, reorder_qty = item
        product = Product(
            merchant_id=merchant.id,
            sku=sku,
            name=name,
            description=desc,
            category=category,
            cost_price=cost,
            selling_price=price,
            status="active",
        )
        session.add(product)
        await session.flush()

        inventory = Inventory(
            product_id=product.id,
            quantity=stock_qty,
            reserved_quantity=reserved_qty,
            reorder_point=reorder_pt,
            reorder_quantity=reorder_qty,
        )
        session.add(inventory)

        # Historical price change entry
        price_history = PriceHistory(
            product_id=product.id,
            old_price=round(price * Decimal("0.90"), 2),
            new_price=price,
            reason="Catalog launch initialization",
            changed_at=now_utc - timedelta(days=SEED_RANDOM.randint(35, 60)),
        )
        session.add(price_history)
        created_products.append(product)

    await session.flush()
    logger.info("Created %d products with inventory and price history records.", len(created_products))

    # 3. Create 110 Orders with line items spanning the past 30 days
    created_orders: List[Order] = []
    order_statuses = [
        OrderStatus.DELIVERED.value,
        OrderStatus.DELIVERED.value,
        OrderStatus.SHIPPED.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.PENDING.value,
        OrderStatus.CANCELLED.value,
    ]

    for i in range(1, 111):
        order_num = f"ORD-{now_utc.year}-{i:05d}"
        days_ago = SEED_RANDOM.uniform(0.1, 30.0)
        ordered_time = now_utc - timedelta(days=days_ago)
        status = SEED_RANDOM.choice(order_statuses)
        customer_ref = f"cust_{SEED_RANDOM.randint(1001, 1999)}@example.com"

        order = Order(
            merchant_id=merchant.id,
            order_number=order_num,
            customer_reference=customer_ref,
            status=status,
            total_amount=Decimal("0.00"),
            ordered_at=ordered_time,
            created_at=ordered_time,
        )
        session.add(order)
        await session.flush()

        # Add 1 to 4 distinct items per order
        num_items = SEED_RANDOM.choices([1, 2, 3, 4], weights=[0.45, 0.35, 0.15, 0.05])[0]
        selected_products = SEED_RANDOM.sample(created_products, k=min(num_items, len(created_products)))

        running_total = Decimal("0.00")
        for prod in selected_products:
            item_qty = SEED_RANDOM.choices([1, 2, 3], weights=[0.8, 0.15, 0.05])[0]
            unit_price = prod.selling_price
            subtotal = unit_price * item_qty
            running_total += subtotal

            line_item = OrderItem(
                order_id=order.id,
                product_id=prod.id,
                quantity=item_qty,
                unit_price=unit_price,
                subtotal=subtotal,
            )
            session.add(line_item)

        order.total_amount = running_total
        created_orders.append(order)

    await session.commit()
    logger.info("Successfully committed seed dataset: 1 merchant, %d products, %d orders.", len(created_products), len(created_orders))
    return merchant, created_products, created_orders


async def main():
    """Main execution entry point when run as a script."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await seed_database(session)

    await engine.dispose()
    logger.info("Seeding script completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
