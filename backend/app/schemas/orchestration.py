"""Typed advisory orchestration contracts and supported business goals."""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
from app.core.config import settings
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.restock import RestockRecommendation
from app.schemas.listing import ListingRecommendation
from app.schemas.promotion import PromotionRecommendation


class Goal(StrEnum):
    MAXIMIZE_REVENUE = "maximize_revenue"
    STOCKOUT_PREVENTION = "avoid_stockouts"
    EXCESS_REDUCTION = "reduce_excess_inventory"
    PERFORMANCE = "improve_product_performance"
    CATALOG = "improve_catalog_quality"
    BALANCED = "balanced_growth"

    OPTIMIZE_PRICING = "optimize pricing"
    INCREASE_REVENUE = "increase revenue"
    AVOID_STOCKOUTS = "avoid stockouts"
    PROTECT_INVENTORY = "protect inventory"
    REVENUE_AND_STOCKOUTS = "increase revenue while avoiding stockouts"
    REVENUE_AND_HEALTH = "improve revenue while maintaining inventory health"
    MOVE_SLOW_INVENTORY = "move slow inventory"
    INCREASE_SELL_THROUGH = "increase sell-through"
    REDUCE_EXCESS_INVENTORY = "reduce excess inventory"
    SLOW_REVENUE = "improve revenue from slow-moving products"
    ALL_HEALTH = "increase revenue while maintaining healthy inventory"


    IMPROVE_LISTINGS = "improve product listings"
    CATALOG_QUALITY = "improve catalog quality"
    DISCOVERABILITY = "improve product discoverability"
    PRODUCT_INFORMATION = "optimize product information"
    PRODUCT_PERFORMANCE = "improve product performance"
    LISTING_AND_INVENTORY = "improve listings while protecting inventory"


class AgentName(StrEnum):
    PRICING = "pricing"
    RESTOCK = "restock"
    PROMOTION = "promotion"
    LISTING = "listing"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Constraints(BaseModel):
    """Requests may tighten existing global safety limits, never loosen them."""
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    max_price_increase_percent: float = Field(default=settings.MAX_PRICE_INCREASE_PERCENT, ge=0, le=settings.MAX_PRICE_INCREASE_PERCENT)
    max_price_decrease_percent: float = Field(default=settings.MAX_PRICE_DECREASE_PERCENT, ge=0, le=settings.MAX_PRICE_DECREASE_PERCENT)
    max_promotion_discount_percent: float = Field(default=settings.MAX_PROMOTION_DISCOUNT_PERCENT, ge=0, le=settings.MAX_PROMOTION_DISCOUNT_PERCENT)
    max_reorder_quantity: int = Field(default=settings.MAX_REORDER_QUANTITY, gt=0, le=settings.MAX_REORDER_QUANTITY, strict=True)


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    merchant_id: int = Field(gt=0, strict=True)
    goal: Goal
    product_ids: list[Annotated[int, Field(gt=0, strict=True)]] | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=100, ge=1, le=100, strict=True)
    constraints: Constraints = Field(default_factory=Constraints)

    @field_validator("goal", mode="before")
    @classmethod
    def normalize_goal(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = " ".join(value.strip().lower().rstrip(".").split())
            if normalized == "improve revenue while avoiding stockouts":
                normalized = Goal.REVENUE_AND_STOCKOUTS.value
            return normalized
        return value

    @field_validator("product_ids")
    @classmethod
    def unique_products(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(set(value)) != len(value):
            raise ValueError("Product IDs must be unique.")
        return sorted(value)


    @model_validator(mode="after")
    def legacy_scope(self) -> "OrchestrationRequest":
        if self.product_ids is None and "_" not in self.goal.value:
            raise ValueError("Legacy goals require explicit product IDs.")
        return self


class AgentError(BaseModel):
    code: Literal["invalid_agent_input", "agent_failed", "invalid_agent_output"]
    message: str


class AgentResult(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    agent_name: AgentName
    product_id: int = Field(gt=0)
    success: bool
    recommendation: PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation | None = None
    risk_level: RiskLevel = RiskLevel.HIGH
    confidence: float = Field(default=0, ge=0, le=1)
    error: AgentError | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "AgentResult":
        if self.success:
            expected = {AgentName.PRICING: PricingRecommendation, AgentName.RESTOCK: RestockRecommendation, AgentName.PROMOTION: PromotionRecommendation, AgentName.LISTING: ListingRecommendation}[self.agent_name]
            if not isinstance(self.recommendation, expected) or self.error is not None:
                raise ValueError("Successful agent result requires a matching recommendation and no error.")
            if self.product_id != self.recommendation.product_id:
                raise ValueError("Agent result belongs to another product.")
            if self.risk_level != self.recommendation.risk_level or self.confidence != self.recommendation.confidence:
                raise ValueError("Agent result metrics must match its recommendation.")
        elif self.recommendation is not None or self.error is None:
            raise ValueError("Failed agent result requires an error and no recommendation.")
        return self


class Conflict(BaseModel):
    type: Literal["pricing_inventory_conflict", "promotion_inventory_conflict", "pricing_promotion_conflict"] = "pricing_inventory_conflict"
    severity: RiskLevel = RiskLevel.HIGH
    product_id: int = Field(gt=0)
    message: str
    resolution: str


class Relationship(BaseModel):
    type: Literal["synergy"] = "synergy"
    product_id: int = Field(gt=0)
    message: str


class PlanRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    agent: AgentName
    product_id: int = Field(gt=0)
    priority: Priority
    action: Literal["restock", "review_inventory", "review_price_change", "hold_price", "monitor_inventory", "review_promotion", "no_promotion", "review_listing"]
    recommended_price: Decimal | None = Field(default=None, gt=0)
    recommended_quantity: int | None = Field(default=None, ge=0)
    deferred: bool = False
    coordination_reason: str

    @field_serializer("recommended_price")
    def serialize_price(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class RecommendationRelationship(BaseModel):
    product_id: int = Field(gt=0)
    agent_a: AgentName
    agent_b: AgentName
    relationship_type: Literal["conflict", "synergy", "independent", "dependency"]
    severity: RiskLevel
    explanation: str
    recommended_resolution: str


class ProductOpportunity(BaseModel):
    product_id: int
    product_name: str
    pricing_opportunity: bool
    stockout_risk: bool
    excess_inventory: bool
    listing_issue: bool
    listing_quality: float | None = Field(default=None, ge=0, le=1)
    inventory_known: bool
    active: bool = True
    selected_agents: list[AgentName]
    selection_reasons: dict[AgentName, str]


class OpportunitySummary(BaseModel):
    pricing_opportunities: list[int] = Field(default_factory=list)
    restock_risks: list[int] = Field(default_factory=list)
    promotion_opportunities: list[int] = Field(default_factory=list)
    listing_issues: list[int] = Field(default_factory=list)


class PrioritizedAction(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    id: str
    rank: int = Field(ge=1)
    product_id: int
    product_name: str
    agent: AgentName
    action_type: Literal["price_change", "restock", "promotion", "listing_update", "review_inventory"]
    priority: Priority
    priority_score: float = Field(ge=0, le=1)
    reason: str
    confidence: float = Field(ge=0, le=1)
    risk: RiskLevel
    blocked: bool = False
    blocked_reason: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    approval_candidate: bool = True


class ActionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    merchant_id: int = Field(gt=0)
    goal: Goal
    summary: str
    selected_agents: list[AgentName]
    selection_reason: str
    recommendations: list[PlanRecommendation]
    agent_results: list[AgentResult]
    conflicts: list[Conflict]
    relationships: list[Relationship]
    overall_risk: RiskLevel
    overall_confidence: float = Field(ge=0, le=1)
    approval_required: Literal[True] = True
    complete: bool
    created_at: datetime
    products_analyzed: int = 0
    opportunities: list[ProductOpportunity] = Field(default_factory=list)
    opportunity_summary: OpportunitySummary = Field(default_factory=OpportunitySummary)
    recommendation_relationships: list[RecommendationRelationship] = Field(default_factory=list)
    prioritized_actions: list[PrioritizedAction] = Field(default_factory=list)
    blocked_actions: list[PrioritizedAction] = Field(default_factory=list)
    omitted_actions: list[PrioritizedAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scope_has_more: bool = False
