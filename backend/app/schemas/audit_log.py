"""Pydantic schemas for AuditLog entity."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Response representing an audit log entry."""
    id: int
    merchant_id: int | None = None
    entity_type: str
    entity_id: str
    event_type: str
    message: str
    metadata: dict[str, Any] | None = Field(default=None, alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
