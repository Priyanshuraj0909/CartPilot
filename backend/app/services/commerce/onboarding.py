"""Bounded provider catalog ingestion; unknown supplier costs stay unknown."""
from decimal import Decimal
import ipaddress
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.price_history import PriceHistory
from app.schemas.commerce import Contract
from app.services.commerce.ingestion import ingest


class ImportedProduct(Contract):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    category: str = Field(min_length=1, max_length=100)
    selling_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    quantity: int = Field(ge=0, le=1000000, strict=True)


def provider_url(source: str) -> str:
    url = "https://dummyjson.com/products?limit=100" if source == "dummyjson" else settings.COMMERCE_CATALOG_API_URL
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "Configure an HTTPS catalog API without embedded credentials.")
    if source == "configured" and parsed.query:
        raise HTTPException(422, "Configure a catalog endpoint without query credentials; use the backend bearer-token setting.")
    if parsed.hostname in {"localhost", "metadata.google.internal"} or parsed.hostname.endswith((".local", ".internal")):
        raise HTTPException(422, "Private catalog addresses are not supported.")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise HTTPException(422, "Private catalog addresses are not supported.")
    except ValueError:
        pass  # Host is an owner-configured DNS name, not a client-supplied URL.
    return url


async def import_provider(session: AsyncSession, merchant_id: int, source: str) -> dict:
    url = provider_url(source)
    headers = {}
    if source == "configured" and settings.COMMERCE_CATALOG_API_TOKEN.get_secret_value():
        headers["Authorization"] = "Bearer " + settings.COMMERCE_CATALOG_API_TOKEN.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 2000000:
                        raise ValueError("Catalog response exceeds 2 MB")
                    content.extend(chunk)
        import json
        data = json.loads(content)
        rows = data["products"] if isinstance(data, dict) else data
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("Provider must return between 1 and 100 products")
        products = [ImportedProduct(sku=str(row.get("sku") or f"API-{source}-{row['id']}"),
            name=row.get("name") or row["title"], description=row.get("description", ""),
            category=row["category"], selling_price=Decimal(str(row["price"])).quantize(Decimal(".01")),
            quantity=row["stock"]) for row in rows]
        if len({row.sku for row in products}) != len(products):
            raise ValueError("Duplicate provider SKUs")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, ValidationError):
        raise HTTPException(503, "Catalog provider returned unavailable or invalid data. No products imported.") from None
    existing = set((await session.scalars(select(Product.sku).where(Product.merchant_id == merchant_id,
        Product.sku.in_([row.sku for row in products])))).all())
    imported = 0
    for row in products:
        if row.sku in existing:
            continue
        product = Product(merchant_id=merchant_id, **row.model_dump(exclude={"quantity"}), cost_price=None, status="active", source="local")
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=row.quantity, reserved_quantity=0, unavailable_quantity=0,
            reorder_point=10, reorder_quantity=50))
        session.add(PriceHistory(product_id=product.id, old_price=row.selling_price,
            new_price=row.selling_price, reason="Merchant API catalog onboarding; cost unverified"))
        imported += 1
    await session.commit()
    return {"imported": imported, "skipped": len(existing), "costs": "unknown; verify before margin-sensitive actions",
        "currency": "INR interpretation; verify supplier numeric currency before publication"}


async def seed_demo(session: AsyncSession, merchant_id: int) -> dict:
    text = "sku,name,category,description,cost_price,selling_price,quantity\n" + "\n".join([
        "DEMO-MOUSE,Quiet Wireless Mouse,Electronics,Wireless computer mouse with quiet clicks,450,899,35",
        "DEMO-KEYBOARD,Everyday Keyboard,Electronics,Compact wired keyboard,800,1499,22",
        "DEMO-TOTE,Canvas Tote,Accessories,Canvas tote with carry handles,250,599,40",
        "DEMO-JOURNAL,Notes Journal,Stationery,Plain paper notebook,120,299,60",
        "DEMO-BOTTLE,Steel Water Bottle,Home,Reusable steel bottle,300,699,28",
        "DEMO-LAMP,Desk Lamp,Home,Adjustable reading lamp,600,1199,18"])
    return await ingest(session, merchant_id, text)
