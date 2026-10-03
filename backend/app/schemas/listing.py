"""Typed advisory listing quality contracts; no publication state."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import settings
from app.schemas.pricing import RiskLevel


class ListingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0, strict=True)
    merchant_id: int | None = Field(default=None, gt=0, strict=True)


class ListingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    min_title_length: int = Field(default=settings.MIN_TITLE_LENGTH, gt=0)
    max_title_length: int = Field(default=settings.MAX_TITLE_LENGTH, gt=0, le=255)
    min_description_length: int = Field(default=settings.MIN_DESCRIPTION_LENGTH, gt=0)
    max_description_length: int = Field(default=settings.MAX_DESCRIPTION_LENGTH, gt=0)
    poor_quality_threshold: float = Field(default=settings.LISTING_POOR_QUALITY_THRESHOLD, ge=0, le=1)

    @model_validator(mode="after")
    def ordered_lengths(self) -> "ListingPolicy":
        if self.min_title_length > self.max_title_length or self.min_description_length > self.max_description_length:
            raise ValueError("Minimum listing lengths cannot exceed maximum lengths.")
        return self


class ListingRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, extra="forbid")
    product_id: int = Field(gt=0)
    current_title: str
    recommended_title: str = Field(min_length=settings.MIN_TITLE_LENGTH, max_length=settings.MAX_TITLE_LENGTH)
    current_description: str | None
    recommended_description: str = Field(min_length=1, max_length=settings.MAX_DESCRIPTION_LENGTH)
    issues: list[str]
    suggestions: list[str]
    missing_attributes: list[str]
    quality_score: float = Field(ge=0, le=1)
    recommended_keywords: list[str]
    category_consistency: Literal["consistent", "inconsistent", "unverified", "missing"]
    confidence: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    reason: str = Field(min_length=5)

    @model_validator(mode="after")
    def nonblank_content(self) -> "ListingRecommendation":
        if not self.recommended_title.strip() or not self.recommended_description.strip():
            raise ValueError("Recommended listing content cannot be blank.")
        return self
