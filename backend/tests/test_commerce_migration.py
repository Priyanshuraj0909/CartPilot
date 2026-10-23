"""Phase 17 upgrade/downgrade retains existing merchant and catalog rows."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_commerce_migration_round_trip(tmp_path):
    path = tmp_path / "commerce.sqlite"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    def migrate(direction, revision):
        result = subprocess.run([sys.executable, "-m", "alembic", direction, revision], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    migrate("upgrade", "16_reliability")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO merchants(id,name,email,store_name,created_at,updated_at) VALUES(1,'Demo','commerce@example.test','Demo',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
    migrate("upgrade", "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM merchants WHERE id=1").fetchone() == ("Demo",)
        for table in ("commerce_policies", "shopper_sessions", "shopping_carts", "commerce_events", "commerce_models"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    migrate("downgrade", "16_reliability")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM merchants WHERE id=1").fetchone() == ("Demo",)
    migrate("upgrade", "head")
