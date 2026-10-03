"""Load existing product text only; no inventory or sales dependency."""
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product


class ListingSignals(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    product_id: int = Field(gt=0)
    merchant_id: int = Field(gt=0)
    title: str
    description: str | None = None
    category: str | None = None
    sku: str
    current_price: Decimal = Field(ge=0)
    status: str


async def extract_listing_signals(product_id: int, session: AsyncSession) -> ListingSignals | None:
    product = await session.get(Product, product_id)
    if product is None:
        return None
    return ListingSignals(product_id=product.id, merchant_id=product.merchant_id,
        title=product.name, description=product.description, category=product.category,
        sku=product.sku, current_price=product.selling_price, status=product.status)
