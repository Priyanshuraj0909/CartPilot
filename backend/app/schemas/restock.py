"""Validated inputs, policy, and advisory restock output."""
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from app.core.config import settings
from app.schemas.pricing import RiskLevel


class RestockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_id: int | None = Field(default=None, gt=0, strict=True)
    product_id: int = Field(gt=0, strict=True)


class RestockPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    lookback_days: int = Field(default=settings.RESTOCK_LOOKBACK_DAYS, gt=0)
    lead_time_days: float = Field(default=settings.DEFAULT_LEAD_TIME_DAYS, ge=0)
    safety_stock_days: float = Field(default=settings.SAFETY_STOCK_DAYS, ge=0)
    max_reorder_quantity: int = Field(default=settings.MAX_REORDER_QUANTITY, gt=0)


class RestockRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    product_id: int = Field(gt=0)
    current_inventory: int = Field(ge=0)
    available_inventory: int = Field(ge=0)
    sales_velocity: float = Field(ge=0)
    estimated_days_remaining: float | None = Field(ge=0)
    recommended_quantity: int = Field(ge=0)
    reason: str = Field(min_length=5)
    confidence: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    reorder_point: int = Field(ge=0)
    lead_time_days: float = Field(ge=0)
    safety_stock: int = Field(ge=0)
    projected_demand_during_lead_time: float = Field(ge=0)
    stockout_risk: bool

    @computed_field
    @property
    def estimated_daily_sales(self) -> float:
        """Phase 4 specification name; identical to shared sales velocity."""
        return self.sales_velocity

    @model_validator(mode="after")
    def validate_inventory(self) -> "RestockRecommendation":
        if self.available_inventory > self.current_inventory:
            raise ValueError("Available inventory cannot exceed physical inventory.")
        if self.sales_velocity == 0 and self.estimated_days_remaining is not None:
            raise ValueError("Zero demand must have null estimated days remaining.")
        return self
