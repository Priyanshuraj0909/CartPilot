"""Strict intent, recovery, resolution and merchandising contracts."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.commerce import Contract, Confirmation, CartRequest


class ChatRequest(Contract):
    message: str = Field(min_length=1, max_length=1000)
    budget_paise: int | None = Field(None, ge=1, le=100000000, strict=True)
    cart_id: UUID | None = None


class ResolutionRequest(Confirmation):
    action: Literal["cancel", "refund", "reconcile", "recover", "return_review"]
    request_key: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    amount_paise: int | None = Field(None, ge=1, le=100000000, strict=True)
    reason: str = Field("Customer requested review", min_length=1, max_length=300)


class ReturnReview(Confirmation):
    decision: Literal["approve", "reject", "received"]


class AddCartItem(Confirmation):
    product_id: int = Field(gt=0, le=2147483647, strict=True)
    quantity: int = Field(1, ge=1, le=20, strict=True)
    source: Literal["manual", "upsell"] = "manual"


class ReplaceCartItem(AddCartItem):
    original_product_id: int = Field(gt=0, le=2147483647, strict=True)


class CompatibilityPair(Contract):
    category_a: str = Field(min_length=1, max_length=100)
    category_b: str = Field(min_length=1, max_length=100)
    weight: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def normalized(self) -> "CompatibilityPair":
        self.category_a = self.category_a.casefold()
        self.category_b = self.category_b.casefold()
        if self.category_a == self.category_b:
            raise ValueError("Choose two different categories.")
        return self


class GrowthRule(Contract):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["feature_category", "recovery_offer", "seasonal_feature"]
    category: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    discount_percent: int = Field(0, ge=0, le=20, strict=True)
    season: Literal["summer", "monsoon", "winter", "transition"] | None = None
    campaign_name: str = Field("", max_length=100)
    starts_at: int | None = Field(None, ge=0, strict=True)
    ends_at: int | None = Field(None, ge=0, strict=True)

    @model_validator(mode="after")
    def dates(self) -> "GrowthRule":
        if self.starts_at is not None and self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("Campaign end must follow its start.")
        return self


class RulesRequest(Contract):
    compatibility: list[CompatibilityPair] = Field(default_factory=list, max_length=100)
    growth_rules: list[GrowthRule] = Field(default_factory=list, max_length=50)
    scheduler_enabled: bool = False
    interval_seconds: int = Field(300, ge=60, le=86400, strict=True)

    @model_validator(mode="after")
    def unique_rules(self) -> "RulesRequest":
        if len({r.id for r in self.growth_rules}) != len(self.growth_rules):
            raise ValueError("Rule IDs must be unique.")
        pairs = [tuple(sorted((p.category_a, p.category_b))) for p in self.compatibility]
        if len(set(pairs)) != len(pairs):
            raise ValueError("Category pairs must be unique.")
        return self


class HandoffRequest(Contract):
    token: str = Field(min_length=32, max_length=128)


class ProviderImport(Confirmation):
    source: Literal["dummyjson", "configured"] = "dummyjson"


class RecoveryOfferRequest(Confirmation):
    request_key: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
