"""Pydantic schemas for PriceHistory entity."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class PriceHistoryResponse(BaseModel):
    """Historical record of product price adjustment."""
    id: int
    product_id: int
    old_price: Decimal = Field(..., ge=0)
    new_price: Decimal = Field(..., ge=0)
    changed_at: datetime
    reason: str | None = None

    model_config = ConfigDict(from_attributes=True)
