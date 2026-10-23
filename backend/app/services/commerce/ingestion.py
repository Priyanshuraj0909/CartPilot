"""Atomic, bounded CSV onboarding reusing the merchant product contract."""
import csv
import io
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.management import ProductInput
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.price_history import PriceHistory

COLUMNS = {"sku", "name", "category", "description", "cost_price", "selling_price", "quantity"}


def parse_csv(text: str) -> list[ProductInput]:
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        if set(reader.fieldnames or []) != COLUMNS or len(reader.fieldnames or []) != len(COLUMNS):
            raise HTTPException(422, "Use the catalog template headers.")
        products = []
        seen = set()
        for row in reader:
            if len(products) >= 500 or None in row or any(value is None for value in row.values()):
                raise HTTPException(422, "Catalog supports at most 500 complete rows.")
            values = dict(row)
            values["quantity"] = int(values["quantity"])
            product = ProductInput.model_validate(values)
            if product.sku in seen:
                raise HTTPException(422, "Duplicate SKU in catalog upload.")
            seen.add(product.sku)
            products.append(product)
        if not products:
            raise HTTPException(422, "Catalog upload is empty.")
        return products
    except (csv.Error, ValueError, ValidationError, TypeError):
        raise HTTPException(422, "Invalid catalog row. Check prices, stock and required fields.") from None


async def ingest(session: AsyncSession, merchant_id: int, text: str) -> dict:
    products = parse_csv(text)
    existing = {product.sku: product for product in (await session.scalars(select(Product).where(
        Product.merchant_id == merchant_id, Product.sku.in_([row.sku for row in products])))).all()}
    # Existing SKUs are rejected before writing: an onboarding file must never
    # silently replace prices, source mappings or existing stock quantities.
    if existing:
        raise HTTPException(409, "Catalog contains an existing SKU. Edit existing products in Manage Store.")
    for body in products:
        values = body.model_dump(exclude={"quantity"})
        product = Product(merchant_id=merchant_id, **values, status="active", source="local")
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=body.quantity, reserved_quantity=0,
            unavailable_quantity=0, reorder_point=10, reorder_quantity=50))
        session.add(PriceHistory(product_id=product.id, old_price=body.selling_price,
            new_price=body.selling_price, reason="Merchant CSV catalog onboarding"))
    await session.commit()
    return {"imported": len(products)}
