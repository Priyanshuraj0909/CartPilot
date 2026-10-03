"""Pydantic schemas for Pricing Agent recommendations and requests."""

from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class RiskLevel(StrEnum):
    """Controlled risk assessment classifications for recommendations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PricingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_id: int | None = Field(default=None, gt=0, strict=True)
    """Request payload for generating a pricing recommendation."""
    product_id: int = Field(..., gt=0, strict=True, description="Unique database identifier of the target product")


class PricingRecommendation(BaseModel):
    """Structured, immutable pricing recommendation produced by the Pricing Agent."""

    product_id: int = Field(..., gt=0, description="Product identifier")
    current_price: Decimal = Field(..., gt=Decimal("0.00"), description="Existing catalog selling price")
    recommended_price: Decimal = Field(..., gt=Decimal("0.00"), description="Recommended new price proposal")
    reason: str = Field(..., min_length=5, description="Deterministic business rationale explaining the recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Deterministic confidence score between 0.0 and 1.0")
    risk_level: RiskLevel = Field(..., description="Categorized risk assessment (low, medium, high)")
    price_change_percent: float = Field(..., description="Percentage delta relative to current price")
    sales_velocity: float = Field(..., ge=0.0, description="Average daily units sold over the lookback window")
    inventory_quantity: int = Field(..., ge=0, description="Available stock quantity at time of analysis")
    cost_price: Decimal = Field(..., ge=Decimal("0.00"), description="Unit cost floor for the product")

    @model_validator(mode="after")
    def validate_pricing_guardrails(self) -> "PricingRecommendation":
        """Enforce strict schema-level guardrail assertions."""
        if self.recommended_price < self.cost_price:
            raise ValueError(
                f"Below-cost violation: recommended_price ({self.recommended_price}) "
                f"cannot be less than cost_price ({self.cost_price})"
            )
        return self

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        frozen=True,
        allow_inf_nan=False,
    )

    @field_serializer("current_price", "recommended_price", "cost_price")
    def serialize_money(self, value: Decimal) -> float:
        return float(value)
