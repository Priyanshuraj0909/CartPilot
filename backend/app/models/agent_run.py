"""AgentRun model tracking execution cycles of specialist agents."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import CheckConstraint, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recommendation import Recommendation


class AgentRunStatus(StrEnum):
    """Execution status of an agent execution cycle."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRun(Base):
    """Audit record of an AI agent execution run."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name="chk_agent_run_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default=AgentRunStatus.STARTED.value,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    input_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AgentRun(id={self.id}, agent='{self.agent_name}', status='{self.status}')>"
