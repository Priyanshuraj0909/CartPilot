"""Pydantic schemas for Recommendation entity."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.recommendation import RecommendationStatus


class RecommendationBase(BaseModel):
    """Base recommendation attributes."""
    recommendation_type: str = Field(..., max_length=100)
    title: str = Field(..., max_length=255)
    description: str | None = None
    recommended_value: dict[str, Any] | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default=RecommendationStatus.PENDING.value)


class RecommendationCreate(RecommendationBase):
    """Payload for registering an agent recommendation."""
    merchant_id: int
    product_id: int | None = None
    agent_run_id: int | None = None


class RecommendationResponse(RecommendationBase):
    """Response representing an agent recommendation."""
    id: int
    merchant_id: int
    product_id: int | None = None
    agent_run_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
