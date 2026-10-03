"""Revocable merchant accounts and sessions."""
from alembic import op
import sqlalchemy as sa
revision = '15_accounts'
down_revision = '11shopify_read_only'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('accounts',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('merchant_id',sa.Integer(),sa.ForeignKey('merchants.id'),nullable=False,unique=True),sa.Column('email',sa.String(255),nullable=False,unique=True),sa.Column('password_hash',sa.String(255),nullable=False))
    op.create_table('account_sessions',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('account_id',sa.Integer(),sa.ForeignKey('accounts.id',ondelete='CASCADE'),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_account_sessions_account_id','account_sessions',['account_id'])

def downgrade():
    op.drop_table('account_sessions')
    op.drop_table('accounts')
