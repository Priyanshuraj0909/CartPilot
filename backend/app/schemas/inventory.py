"""Pydantic schemas for Inventory entity."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas._time import utc_timestamp


class InventoryBase(BaseModel):
    """Base inventory thresholds and stock levels."""
    quantity: int = Field(default=0, ge=0, description="Total physical units in stock")
    reserved_quantity: int = Field(default=0, ge=0, description="Units allocated to active unfulfilled orders")
    unavailable_quantity: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=10, ge=0, description="Threshold triggering restocking alerts")
    reorder_quantity: int = Field(default=50, ge=0, description="Standard batch reorder quantity")


class InventoryUpdate(BaseModel):
    """Payload for adjusting product inventory levels."""
    quantity: int | None = Field(None, ge=0)
    reserved_quantity: int | None = Field(None, ge=0)
    reorder_point: int | None = Field(None, ge=0)
    reorder_quantity: int | None = Field(None, ge=0)


class InventoryResponse(InventoryBase):
    """Response model representing inventory details."""
    id: int
    product_id: int
    available_quantity: int
    is_low_stock: bool
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime:
        return utc_timestamp(value)

    model_config = ConfigDict(from_attributes=True)
