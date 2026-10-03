"""Extend existing actions with a guarded lifecycle and deduplication key.

Revision ID: 9a10guarded
Revises: 926d82e261cb
"""
from alembic import op
import sqlalchemy as sa

revision = "9a10guarded"
down_revision = "926d82e261cb"
branch_labels = None
depends_on = None

OLD = "status IN ('pending', 'approved', 'executed', 'failed', 'cancelled')"
NEW = "status IN ('pending', 'validated', 'awaiting_approval', 'approved', 'rejected', 'executing', 'executed', 'failed', 'cancelled')"


def upgrade() -> None:
    with op.batch_alter_table("actions") as batch:
        batch.drop_constraint("chk_action_status_valid", type_="check")
        batch.create_check_constraint("chk_action_status_valid", NEW)
        batch.add_column(sa.Column("workflow_key", sa.String(100), nullable=True))
        batch.add_column(sa.Column("risk_level", sa.String(10), nullable=False, server_default="high"))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.create_unique_constraint("uq_action_workflow_key", ["workflow_key"])


def downgrade() -> None:
    # Preserve legacy status compatibility without silently enabling unsafe execution.
    op.execute("UPDATE actions SET status = 'cancelled' WHERE status NOT IN ('pending', 'approved', 'executed', 'failed', 'cancelled')")
    with op.batch_alter_table("actions") as batch:
        batch.drop_constraint("uq_action_workflow_key", type_="unique")
        batch.drop_constraint("chk_action_status_valid", type_="check")
        batch.create_check_constraint("chk_action_status_valid", OLD)
        for column in ("workflow_key", "risk_level", "created_at", "updated_at"):
            batch.drop_column(column)
