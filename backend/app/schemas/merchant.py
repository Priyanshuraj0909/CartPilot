"""Pydantic schemas for Merchant entity."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[\w\.\+-]+@[\w\.-]+\.[a-zA-Z]{2,}$"


class MerchantBase(BaseModel):
    """Base merchant attributes."""
    name: str = Field(..., min_length=1, max_length=255, description="Merchant contact or legal name")
    email: str = Field(..., pattern=EMAIL_PATTERN, description="Unique merchant contact email")
    store_name: str = Field(..., min_length=1, max_length=255, description="Public store display name")


class MerchantCreate(MerchantBase):
    """Payload for registering a new merchant."""
    pass


class MerchantUpdate(BaseModel):
    """Payload for updating an existing merchant."""
    name: str | None = Field(None, min_length=1, max_length=255)
    email: str | None = Field(None, pattern=EMAIL_PATTERN)
    store_name: str | None = Field(None, min_length=1, max_length=255)


class MerchantResponse(MerchantBase):
    """Response model representing a persisted merchant."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
