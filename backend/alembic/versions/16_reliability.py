"""Shared auth limits and tenant-scoped orchestration history."""
from alembic import op
import sqlalchemy as sa

revision = "16_reliability"
down_revision = "15_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("merchant_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_agent_runs_merchant", "merchants", ["merchant_id"], ["id"])
        batch.create_index("ix_agent_runs_merchant_id", ["merchant_id"])


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_index("ix_agent_runs_merchant_id")
        batch.drop_constraint("fk_agent_runs_merchant", type_="foreignkey")
        batch.drop_column("merchant_id")
    op.drop_table("auth_rate_limits")
