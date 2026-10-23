"""Isolated buyer commerce tables; existing catalog and sales remain intact."""
from alembic import op
from app.models.commerce import CommercePolicy, ShopperSession, ShoppingCart, CommerceEvent, CommerceModel

revision = "17_commerce"
down_revision = "16_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for model in (CommercePolicy, ShopperSession, ShoppingCart, CommerceEvent, CommerceModel):
        model.__table__.create(op.get_bind())


def downgrade() -> None:
    for model in (CommerceModel, CommerceEvent, ShoppingCart, ShopperSession, CommercePolicy):
        model.__table__.drop(op.get_bind())
