"""PriceHistory model tracking historical price adjustments."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class PriceHistory(Base):
    """Historical audit of price modifications for a product."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory(id={self.id}, product_id={self.product_id}, old={self.old_price}, new={self.new_price})>"
