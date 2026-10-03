"""Isolated Alembic migration preserves demo records and avoids lossy downgrade."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest

@pytest.mark.parametrize('blocked',[None,'cost','stock'])
def test_shopify_migration(tmp_path,blocked):
    path=tmp_path/'migration.sqlite'
    env={**os.environ,'DATABASE_URL':f'sqlite+aiosqlite:///{path}'}
    def migrate(revision,direction='upgrade'):
        return subprocess.run([sys.executable,'-m','alembic',direction,revision],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True)
    assert migrate('9a10guarded').returncode==0
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO merchants(id,name,email,store_name,created_at,updated_at) VALUES(1,'Demo','migration@example.test','Demo',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        c.execute("INSERT INTO products(id,merchant_id,sku,name,category,cost_price,selling_price,status,created_at,updated_at) VALUES(1,1,'DEMO','Demo','Demo',40,100,'active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        c.execute("INSERT INTO inventory(id,product_id,quantity,reserved_quantity,reorder_point,reorder_quantity,updated_at) VALUES(1,1,12,2,10,50,CURRENT_TIMESTAMP)")
    upgraded=migrate('head');assert upgraded.returncode==0,upgraded.stderr
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT sku,cost_price,source FROM products').fetchone()==('DEMO',40,'local')
        assert c.execute('SELECT quantity,reserved_quantity,unavailable_quantity FROM inventory').fetchone()==(12,2,0)
        assert len(c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('shopify_connections','external_product_mappings','external_order_mappings')").fetchall())==3
        if blocked=='cost': c.execute('UPDATE products SET cost_price=NULL')
        if blocked=='stock': c.execute('UPDATE inventory SET unavailable_quantity=1')
    result=migrate('9a10guarded','downgrade')
    if blocked:
        assert result.returncode!=0
        with sqlite3.connect(path) as c:
            assert c.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='11shopify_read_only'
    else:
        assert result.returncode==0,result.stderr
        with sqlite3.connect(path) as c: assert c.execute('SELECT sku,cost_price FROM products').fetchone()==('DEMO',40)
