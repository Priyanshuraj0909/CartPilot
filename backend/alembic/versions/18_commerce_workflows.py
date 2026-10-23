"""Durable conversation and guarded recovery/resolution workflows."""
from alembic import op
import sqlalchemy as sa

revision = "18_commerce_workflows"
down_revision = "17_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("shopping_conversations",
        sa.Column("shopper_hash", sa.String(64), sa.ForeignKey("shopper_sessions.token_hash", ondelete="CASCADE"), primary_key=True),
        sa.Column("messages", sa.JSON(), nullable=False), sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False))
    op.create_table("commerce_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("shopping_carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False), sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("provider_id", sa.String(100)), sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("cart_id", "request_key", name="uq_commerce_operation_request"))
    op.create_index("ix_commerce_operations_cart_id", "commerce_operations", ["cart_id"])
    op.create_table("commerce_rules",
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("compatibility", sa.JSON(), nullable=False), sa.Column("growth_rules", sa.JSON(), nullable=False),
        sa.Column("scheduler_enabled", sa.Boolean(), nullable=False), sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.BigInteger(), nullable=False), sa.Column("last_result", sa.JSON(), nullable=False))
    op.create_table("shopper_handoffs",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("shopping_carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_shopper_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False), sa.Column("redeemed", sa.Boolean(), nullable=False))
    op.create_index("ix_shopper_handoffs_cart_id", "shopper_handoffs", ["cart_id"])


def downgrade() -> None:
    for table in ("shopper_handoffs", "commerce_rules", "commerce_operations", "shopping_conversations"):
        op.drop_table(table)
