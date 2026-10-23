"""Workflow migration preserves existing shopper capabilities and draft carts."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_workflow_migration_preserves_existing_cart(tmp_path):
    database = tmp_path / "workflows.sqlite"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    def migrate(direction, revision):
        result = subprocess.run([sys.executable, "-m", "alembic", direction, revision],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    migrate("upgrade", "17_commerce")
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO merchants(id,name,email,store_name,created_at,updated_at) VALUES(1,'Demo','workflow@example.test','Demo',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.execute("INSERT INTO shopper_sessions(token_hash,merchant_id,expires_at) VALUES(?,1,2000000000)", ("a" * 64,))
        connection.execute("INSERT INTO shopping_carts(id,merchant_id,shopper_hash,status,budget_paise,total_paise,items,created_at,expires_at) VALUES('old-cart',1,?,'draft',100,100,'[]',1,2000000000)", ("a" * 64,))
    migrate("upgrade", "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM shopping_carts WHERE id='old-cart'").fetchone() == ("draft",)
        for table in ("shopping_conversations", "commerce_operations", "commerce_rules", "shopper_handoffs"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(shopper_handoffs)")}
        assert "source_shopper_hash" in columns
    migrate("downgrade", "17_commerce")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM shopping_carts WHERE id='old-cart'").fetchone() == ("draft",)
    migrate("upgrade", "head")
