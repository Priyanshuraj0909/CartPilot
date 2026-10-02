"""Approval model representing human-in-the-loop decisions on recommendations."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recommendation import Recommendation


class ApprovalStatus(StrEnum):
    """Status of merchant approval review."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Approval(Base):
    """Human-in-the-loop review and sign-off record for an agent recommendation."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="chk_approval_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default=ApprovalStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    recommendation: Mapped["Recommendation"] = relationship("Recommendation", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<Approval(id={self.id}, rec_id={self.recommendation_id}, status='{self.status}', by='{self.approved_by}')>"
