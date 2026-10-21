"""Pydantic schemas for AgentRun entity."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
from app.models.agent_run import AgentRunStatus
from app.schemas._time import utc_timestamp


class AgentRunBase(BaseModel):
    """Base agent run attributes."""
    agent_name: str
    status: str = AgentRunStatus.STARTED.value
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_message: str | None = None


class AgentRunResponse(AgentRunBase):
    """Response representing an agent run."""
    id: int
    merchant_id: int | None = None
    started_at: datetime
    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return utc_timestamp(value) if value else None

    model_config = ConfigDict(from_attributes=True)
