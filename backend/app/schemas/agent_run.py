"""Pydantic schemas for AgentRun entity."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict
from app.models.agent_run import AgentRunStatus


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
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
