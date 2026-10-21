"""Reliability migration retains existing agent runs and linked recommendations."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_upgrade_and_downgrade_preserve_history(tmp_path):
    path = tmp_path / "reliability.sqlite"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    def migrate(direction, revision):
        result = subprocess.run([sys.executable, "-m", "alembic", direction, revision], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    migrate("upgrade", "15_accounts")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO merchants(id,name,email,store_name,created_at,updated_at) VALUES(1,'Demo','migration@example.test','Demo',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.execute("INSERT INTO agent_runs(id,agent_name,status) VALUES(1,'orchestrator','completed')")
        connection.execute("INSERT INTO recommendations(id,merchant_id,agent_run_id,recommendation_type,title,status,confidence,created_at) VALUES(1,1,1,'pricing','Legacy','pending',.8,CURRENT_TIMESTAMP)")
    migrate("upgrade", "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT merchant_id FROM agent_runs WHERE id=1").fetchone() == (None,)
        assert connection.execute("SELECT agent_run_id FROM recommendations").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM auth_rate_limits").fetchone() == (0,)
    migrate("downgrade", "15_accounts")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT agent_name FROM agent_runs").fetchone() == ("orchestrator",)
        assert connection.execute("SELECT agent_run_id FROM recommendations").fetchone() == (1,)
    migrate("upgrade", "head")
