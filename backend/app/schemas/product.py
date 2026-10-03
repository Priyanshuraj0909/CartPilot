"""Pydantic schemas for Product entity."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas._time import utc_timestamp
from app.schemas.inventory import InventoryResponse
from app.schemas.price_history import PriceHistoryResponse


class ProductBase(BaseModel):
    """Base product attributes."""
    sku: str = Field(..., min_length=1, max_length=100, description="Merchant unique stock-keeping unit")
    name: str = Field(..., min_length=1, max_length=255, description="Product catalog title")
    description: str | None = Field(None, description="Detailed product description")
    category: str = Field(..., min_length=1, max_length=100, description="Product taxonomy category")
    cost_price: Decimal | None = Field(..., ge=0, description="Unit acquisition / production cost")
    selling_price: Decimal = Field(..., ge=0, description="Storefront retail price")
    status: str = Field(default="active", max_length=50, description="Listing status: active, draft, archived")


class ProductCreate(ProductBase):
    """Payload for creating a new product under a merchant."""
    merchant_id: int = Field(..., description="ID of merchant owning the product")
    initial_quantity: int = Field(default=0, ge=0, description="Optional starting inventory quantity")
    reorder_point: int = Field(default=10, ge=0)
    reorder_quantity: int = Field(default=50, ge=0)


class ProductUpdate(BaseModel):
    """Payload for partial updates to a product."""
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(None, min_length=1, max_length=100)
    cost_price: Decimal | None = Field(None, ge=0)
    selling_price: Decimal | None = Field(None, ge=0)
    status: str | None = Field(None, max_length=50)


class ProductResponse(ProductBase):
    """Product summary response."""
    source: str = "local"
    id: int
    merchant_id: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime:
        return utc_timestamp(value)

    model_config = ConfigDict(from_attributes=True)


class ProductDetailResponse(ProductResponse):
    """Detailed product response including inventory and price history."""
    inventory: InventoryResponse | None = None
    price_history: list[PriceHistoryResponse] = []

    model_config = ConfigDict(from_attributes=True)
