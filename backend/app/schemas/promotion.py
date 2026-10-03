"""Validated, advisory-only discount contracts."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_serializer
from app.core.config import settings
from app.schemas.pricing import RiskLevel


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0, strict=True)
    merchant_id: int | None = Field(default=None, gt=0, strict=True)


class PromotionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    lookback_days: int = Field(default=settings.PROMOTION_LOOKBACK_DAYS, ge=2)
    max_discount_percent: Decimal = Field(default=Decimal(str(settings.MAX_PROMOTION_DISCOUNT_PERCENT)), ge=0, lt=100)
    min_margin_percent: Decimal = Field(default=Decimal(str(settings.PROMOTION_MIN_MARGIN_PERCENT)), ge=0, lt=100)
    high_inventory_days: float = Field(default=settings.HIGH_INVENTORY_DAYS_THRESHOLD, gt=0)
    slow_sales_threshold: float = Field(default=settings.SLOW_SALES_THRESHOLD, ge=0)
    zero_sales_inventory: int = Field(default=settings.PROMOTION_ZERO_SALES_MIN_INVENTORY, gt=0)
    trend_change_percent: float = Field(default=settings.PROMOTION_TREND_CHANGE_PERCENT, ge=0, lt=100)
    mild_discount: Decimal = Field(default=Decimal(str(settings.PROMOTION_MILD_DISCOUNT_PERCENT)), ge=0, lt=100)
    moderate_discount: Decimal = Field(default=Decimal(str(settings.PROMOTION_MODERATE_DISCOUNT_PERCENT)), ge=0, lt=100)
    severe_discount: Decimal = Field(default=Decimal(str(settings.PROMOTION_SEVERE_DISCOUNT_PERCENT)), ge=0, lt=100)


class PromotionRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")
    product_id: int = Field(gt=0)
    current_price: Decimal = Field(gt=0)
    cost_price: Decimal = Field(ge=0)
    promotion_recommended: bool
    promotion_type: Literal["none", "discount"]
    discount_percentage: Decimal = Field(ge=0, lt=100)
    promotional_price: Decimal = Field(gt=0)
    reason: str = Field(min_length=5)
    confidence: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    available_inventory: int = Field(ge=0)
    sales_velocity: float = Field(ge=0)
    sales_trend: Literal["increasing", "stable", "declining", "insufficient_data"]
    gross_margin_percent: float
    retained_margin_percent: float
    days_of_inventory: float | None = Field(ge=0)
    recent_units: int = Field(ge=0)
    previous_units: int = Field(ge=0)
    expected_effect: str = Field(min_length=5)

    @field_serializer("current_price", "cost_price", "discount_percentage", "promotional_price")
    def money(self, value: Decimal) -> float:
        return float(value)

    @model_validator(mode="after")
    def coherent_discount(self) -> "PromotionRecommendation":
        if self.promotion_recommended != (self.promotion_type == "discount" and self.discount_percentage > 0):
            raise ValueError("Promotion flag, type and discount must agree.")
        if not self.promotion_recommended and (self.discount_percentage != 0 or self.promotional_price != self.current_price or self.promotion_type != "none"):
            raise ValueError("No promotion must preserve the current price.")
        if self.promotion_recommended:
            expected = (self.current_price * (1 - self.discount_percentage / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            if self.promotional_price != expected or self.promotional_price < self.cost_price:
                raise ValueError("Discount must match its price and cannot fall below cost.")
        return self
