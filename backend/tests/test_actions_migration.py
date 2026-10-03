"""Upgrade/downgrade preserve legacy rows and create Phase 9 constraints."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_action_migration(tmp_path):
    path=tmp_path/'migration.sqlite'
    env={**os.environ,'DATABASE_URL':f'sqlite+aiosqlite:///{path}'}
    cwd=Path(__file__).resolve().parents[1]
    def migrate(revision,command='upgrade'):
        result=subprocess.run([sys.executable,'-m','alembic',command,revision],cwd=cwd,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    migrate('926d82e261cb')
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO merchants (id,name,email,store_name,created_at,updated_at) VALUES (1,'Demo','migration@test.com','Demo',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO recommendations (id,merchant_id,recommendation_type,title,status,confidence,created_at) VALUES (1,1,'pricing','Legacy','pending',.8,CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO actions (id,recommendation_id,action_type,status) VALUES (1,1,'price_change','approved')")
    migrate('head')
    with sqlite3.connect(path) as conn:
        row=conn.execute('SELECT status,workflow_key,risk_level,created_at FROM actions').fetchone()
        assert row[0]=='approved' and row[1] is None and row[2]=='high' and row[3]
        conn.execute("UPDATE actions SET status='awaiting_approval',workflow_key='recommendation:1' WHERE id=1")
    migrate('926d82e261cb','downgrade')
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM actions').fetchone()[0]=='cancelled'
