"""Action model representing execution commands derived from recommendations."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recommendation import Recommendation


class ActionStatus(StrEnum):
    """Execution status of an action."""
    PENDING = "pending"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    EXECUTING = "executing"
    APPROVED = "approved"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Action(Base):
    """Simulated or physical action generated from an approved recommendation."""

    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("workflow_key", name="uq_action_workflow_key"),
        CheckConstraint(
            "status IN ('pending', 'validated', 'awaiting_approval', 'approved', 'rejected', 'executing', 'executed', 'failed', 'cancelled')",
            name="chk_action_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default=ActionStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    workflow_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(10), default="high", server_default="high", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    recommendation: Mapped["Recommendation"] = relationship("Recommendation", back_populates="actions")

    def __repr__(self) -> str:
        return f"<Action(id={self.id}, type='{self.action_type}', status='{self.status}')>"
