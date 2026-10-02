"""Pydantic schemas for Order and OrderItem entities."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from app.models.order import OrderStatus


class OrderItemBase(BaseModel):
    """Base order line item attributes."""
    product_id: int
    quantity: int = Field(..., gt=0, description="Purchased quantity")
    unit_price: Decimal = Field(..., ge=0, description="Unit price at moment of sale")
    subtotal: Decimal = Field(..., ge=0, description="Line item subtotal (quantity * unit_price)")


class OrderItemCreate(BaseModel):
    """Line item payload when placing an order."""
    product_id: int
    quantity: int = Field(..., gt=0)
    unit_price: Decimal | None = Field(None, ge=0, description="Defaults to product selling price if omitted")


class OrderItemResponse(OrderItemBase):
    """Response representing an order line item."""
    id: int
    order_id: int

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    """Base order attributes."""
    order_number: str = Field(..., max_length=100)
    customer_reference: str | None = Field(None, max_length=255)
    status: str = Field(default=OrderStatus.PENDING.value)
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0)


class OrderCreate(BaseModel):
    """Payload for placing a new customer order."""
    merchant_id: int
    order_number: str = Field(..., min_length=1, max_length=100)
    customer_reference: str | None = Field(None, max_length=255)
    status: str = Field(default=OrderStatus.PENDING.value)
    ordered_at: datetime | None = None
    items: list[OrderItemCreate] = Field(..., min_length=1, description="List of items in order")


class OrderResponse(OrderBase):
    """Response representing high-level order metadata."""
    id: int
    merchant_id: int
    ordered_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderDetailResponse(OrderResponse):
    """Detailed order response containing line items."""
    items: list[OrderItemResponse] = []

    model_config = ConfigDict(from_attributes=True)
