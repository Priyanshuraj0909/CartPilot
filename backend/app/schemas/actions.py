"""Explicit action inputs, immutable payloads and approval responses."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.restock import RestockRecommendation
from app.schemas.promotion import PromotionRecommendation
from app.schemas.listing import ListingRecommendation
from app.models.action import ActionStatus

RecommendationValue = PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation


class ActionType(StrEnum):
    PRICE = "price_change"
    RESTOCK = "restock"
    PROMOTION = "promotion"
    LISTING = "listing_update"


class PayloadBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    product_id: int = Field(gt=0, strict=True)


class PricePayload(PayloadBase):
    kind: Literal["price_change"] = "price_change"
    old_price: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    new_price: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    expected_cost: Decimal = Field(ge=0, decimal_places=2, max_digits=10)


class RestockPayload(PayloadBase):
    kind: Literal["restock"] = "restock"
    quantity: int = Field(gt=0, strict=True)


class PromotionPayload(PayloadBase):
    kind: Literal["promotion"] = "promotion"
    old_price: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    expected_cost: Decimal = Field(ge=0, decimal_places=2, max_digits=10)
    discount_percentage: Decimal = Field(gt=0, lt=100, decimal_places=2)
    promotional_price: Decimal = Field(gt=0, decimal_places=2, max_digits=10)


class ListingPayload(PayloadBase):
    kind: Literal["listing_update"] = "listing_update"
    old_title: str
    old_description: str | None
    expected_category: str | None
    expected_sku: str
    new_title: str = Field(min_length=1, max_length=255)
    new_description: str = Field(min_length=1)


ActionPayload = Annotated[PricePayload | RestockPayload | PromotionPayload | ListingPayload, Field(discriminator="kind")]


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_id: int = Field(gt=0, strict=True)
    recommendation_id: int | None = Field(default=None, gt=0, strict=True)
    agent: Literal["pricing", "restock", "promotion", "listing"] | None = None
    recommendation: RecommendationValue | None = None

    @model_validator(mode="after")
    def one_source(self) -> "ActionCreate":
        if self.recommendation_id is not None:
            if self.agent is not None or self.recommendation is not None:
                raise ValueError("Use a saved recommendation or an inline recommendation, not both.")
        elif self.agent is None or self.recommendation is None:
            raise ValueError("An inline source requires agent and typed recommendation.")
        return self


class ActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_id: int = Field(gt=0, strict=True)
    actor: str = Field(default="development-merchant", min_length=1, max_length=255, pattern=r"\S")
    comment: str | None = Field(default=None, max_length=2000)


class ExecutionRequest(ActionDecision):
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Execution requires explicit boolean confirmation.")
        return value


class PolicyValidationResult(BaseModel):
    is_valid: bool
    policy_name: str
    violations: list[str]
    warnings: list[str] = Field(default_factory=list)
    requires_approval: Literal[True] = True
    risk_level: RiskLevel


class ActionResponse(BaseModel):
    id: int
    recommendation_id: int
    merchant_id: int
    product_id: int
    product_name: str
    agent: str
    reason: str
    action_type: ActionType
    payload: ActionPayload
    status: ActionStatus
    risk_level: RiskLevel
    approval_required: Literal[True] = True
    execution_mode: Literal["local_mutation", "simulated"]
    created_at: datetime
    executed_at: datetime | None
    approved_by: str | None
    approval_status: str
    comment: str | None
    policy: PolicyValidationResult
    result: dict | None

    @field_validator("created_at", "executed_at")
    @classmethod
    def utc_dates(cls, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class ActionAuditResponse(BaseModel):
    id: int
    action_id: int
    merchant_id: int
    event_type: str
    message: str
    metadata: dict | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_date(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
