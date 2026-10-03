"""Inventory model tracking product stock levels and reorder parameters."""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Inventory(Base):
    """Inventory levels and replenishment thresholds for a product."""

    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("unavailable_quantity >= 0", name="chk_inventory_unavailable_non_negative"),
        CheckConstraint("quantity >= 0", name="chk_inventory_quantity_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="chk_inventory_reserved_non_negative"),
        CheckConstraint("reorder_point >= 0", name="chk_inventory_reorder_point_non_negative"),
        CheckConstraint("reorder_quantity >= 0", name="chk_inventory_reorder_quantity_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unavailable_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="inventory")

    @property
    def available_quantity(self) -> int:
        """Calculate unreserved stock available for immediate fulfillment."""
        return max(0, self.quantity - self.reserved_quantity - (self.unavailable_quantity or 0))

    @property
    def is_low_stock(self) -> bool:
        """Indicate whether available stock has dipped to or below the reorder point."""
        return self.available_quantity <= self.reorder_point

    def __repr__(self) -> str:
        return f"<Inventory(id={self.id}, product_id={self.product_id}, qty={self.quantity}, reserved={self.reserved_quantity})>"
