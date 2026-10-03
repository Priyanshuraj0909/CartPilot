"""Pydantic schemas for PriceHistory entity."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas._time import utc_timestamp


class PriceHistoryResponse(BaseModel):
    """Historical record of product price adjustment."""
    id: int
    product_id: int
    old_price: Decimal = Field(..., ge=0)
    new_price: Decimal = Field(..., ge=0)
    changed_at: datetime
    reason: str | None = None

    @field_validator("changed_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime:
        return utc_timestamp(value)

    model_config = ConfigDict(from_attributes=True)
