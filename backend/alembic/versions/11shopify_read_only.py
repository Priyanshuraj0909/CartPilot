"""Read-only Shopify identities and honest cost/inventory representation."""
from alembic import op
import sqlalchemy as sa
revision='11shopify_read_only'
down_revision='9a10guarded'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('products') as batch:
        batch.alter_column('cost_price',existing_type=sa.Numeric(10,2),nullable=True)
        batch.add_column(sa.Column('source',sa.String(16),nullable=False,server_default='local'))
    with op.batch_alter_table('inventory') as batch:
        batch.add_column(sa.Column('unavailable_quantity',sa.Integer(),nullable=False,server_default='0'))
        batch.create_check_constraint('chk_inventory_unavailable_non_negative','unavailable_quantity >= 0')
    op.create_table('shopify_connections',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('merchant_id',sa.Integer(),sa.ForeignKey('merchants.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('store_domain',sa.String(80),nullable=False,unique=True),sa.Column('currency',sa.String(3)),
        sa.Column('sync_in_progress',sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column('last_sync',sa.JSON()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_table('external_product_mappings',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('connection_id',sa.Integer(),sa.ForeignKey('shopify_connections.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('product_id',sa.Integer(),sa.ForeignKey('products.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('external_product_id',sa.String(100),nullable=False),sa.Column('external_variant_id',sa.String(100),nullable=False),
        sa.Column('inventory_item_id',sa.String(100),nullable=False),sa.Column('external_sku',sa.String(255)),
        sa.Column('source_updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('last_synced_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('inventory_synced_at',sa.DateTime(timezone=True)),sa.Column('inventory_snapshot',sa.JSON()),
        sa.UniqueConstraint('connection_id','external_variant_id',name='uq_shopify_variant'))
    op.create_table('external_order_mappings',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('connection_id',sa.Integer(),sa.ForeignKey('shopify_connections.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('orders.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('external_order_id',sa.String(100),nullable=False),sa.Column('last_synced_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('connection_id','external_order_id',name='uq_shopify_order'))

def downgrade():
    # Never invent costs to satisfy the old NOT NULL column during downgrade.
    connection=op.get_bind()
    if connection.execute(sa.text('SELECT COUNT(*) FROM products WHERE cost_price IS NULL')).scalar():
        raise RuntimeError('Downgrade requires genuine cost values for all products; unknown costs cannot be fabricated.')
    if connection.execute(sa.text('SELECT COUNT(*) FROM inventory WHERE unavailable_quantity > 0')).scalar():
        raise RuntimeError('Downgrade would lose unavailable stock safety information; reconcile inventory first.')
    op.drop_table('external_order_mappings');op.drop_table('external_product_mappings');op.drop_table('shopify_connections')
    with op.batch_alter_table('inventory') as batch:
        batch.drop_constraint('chk_inventory_unavailable_non_negative',type_='check');batch.drop_column('unavailable_quantity')
    with op.batch_alter_table('products') as batch:
        batch.drop_column('source');batch.alter_column('cost_price',existing_type=sa.Numeric(10,2),nullable=False)
