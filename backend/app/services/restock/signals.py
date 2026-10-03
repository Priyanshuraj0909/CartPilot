"""Restock inputs adapted from the existing sales and inventory read service."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pricing.signals import ProductPricingSignals, extract_pricing_signals


class MissingInventoryError(ValueError):
    """An inventory record is required to assess replenishment."""


class RestockSignals(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    reserved_quantity: int = Field(ge=0)
    unavailable_quantity: int = Field(default=0, ge=0)
    reorder_point: int = Field(ge=0)
    reorder_quantity: int = Field(ge=0)
    sales_velocity: float = Field(ge=0)
    recent_orders: int = Field(ge=0)
    has_sufficient_data: bool
    status: str = "active"

    @model_validator(mode="after")
    def validate_reservations(self) -> "RestockSignals":
        if self.reserved_quantity + self.unavailable_quantity > self.quantity:
            raise ValueError("Reserved inventory cannot exceed physical quantity.")
        return self

    @property
    def available_inventory(self) -> int:
        return self.quantity - self.reserved_quantity - self.unavailable_quantity


async def extract_restock_signals(
    product_id: int, session: AsyncSession, lookback_days: int,
    as_of: datetime | None = None,
) -> RestockSignals | None:
    """Reuse Phase 3's non-cancelled sales window, history, and inventory inputs."""
    signals = await extract_pricing_signals(product_id, session, lookback_days, as_of)
    if signals is None:
        return None
    return restock_signals_from_snapshot(signals)


def restock_signals_from_snapshot(signals: ProductPricingSignals) -> RestockSignals:
    """Adapt a preloaded business snapshot with the same inventory validation."""
    if not signals.has_inventory:
        raise MissingInventoryError("Product has no inventory record; verify stock before restocking.")
    return RestockSignals(
        product_id=signals.product_id, quantity=signals.total_quantity,
        reserved_quantity=signals.reserved_quantity, unavailable_quantity=signals.unavailable_quantity, reorder_point=signals.reorder_point,
        reorder_quantity=signals.reorder_quantity, sales_velocity=signals.sales_velocity,
        recent_orders=signals.orders_count_lookback,
        has_sufficient_data=signals.has_sufficient_data, status=signals.status,
    )
