"""Persisted summaries enforce tenant ownership and expose partial results."""
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.deps import get_database_session
from app.core.config import settings
from app.main import app
from app.models.agent_run import AgentRun
from app.models.inventory import Inventory
from tests.orchestration_helpers import make_store


@pytest.fixture
async def history_client(async_client, db_session):
    async def override():
        yield db_session
    app.dependency_overrides[get_database_session] = override
    try:
        yield async_client, db_session, await make_store(db_session)
    finally:
        app.dependency_overrides.clear()


async def run_plan(client, store):
    return await client.post("/api/v1/orchestrate", json={
        "merchant_id": store["merchant"], "goal": "increase revenue while avoiding stockouts", "product_ids": [store["low"]],
    })


async def test_saved_summary_pagination_and_utc(history_client):
    client, session, store = history_client
    for _ in range(2):
        assert (await run_plan(client, store)).status_code == 200
    # Legacy rows have no provable owner and must never appear in a tenant feed.
    session.add(AgentRun(agent_name="orchestrator", status="completed"))
    await session.commit()
    url = f"/api/v1/agent-runs?merchant_id={store['merchant']}"
    rows = (await client.get(url)).json()
    assert len(rows) == 2 and rows[0]["id"] > rows[1]["id"]
    assert rows[0]["output_summary"]["complete"] is True
    assert rows[0]["output_summary"]["products_analyzed"] == 1
    assert rows[0]["started_at"].endswith("Z") and rows[0]["completed_at"].endswith("Z")
    assert (await client.get(url + "&offset=1&limit=1")).json() == rows[1:]
    assert (await client.get(url + "&offset=2")).json() == []


async def test_partial_plan_is_saved(history_client):
    client, session, store = history_client
    inventory = await session.scalar(select(Inventory).where(Inventory.product_id == store["low"]))
    await session.delete(inventory)
    await session.commit()
    assert (await run_plan(client, store)).status_code == 200
    rows = (await client.get(f"/api/v1/agent-runs?merchant_id={store['merchant']}")).json()
    assert rows[0]["output_summary"]["complete"] is False
    assert rows[0]["output_summary"]["failed_analyses"] > 0


@pytest.mark.parametrize("query,status", [("", 422), ("?merchant_id=-1", 422), ("?merchant_id=99999", 404), ("?merchant_id=1&limit=101", 422), ("?merchant_id=1&offset=-1", 422)])
async def test_invalid_scope_or_page(history_client, query, status):
    client, _, _ = history_client
    assert (await client.get("/api/v1/agent-runs" + query)).status_code == status


async def test_authenticated_history_blocks_foreign_store(history_client, monkeypatch):
    client, _, store = history_client
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    signup = await client.post("/api/v1/auth/signup", json={"email": "history@example.test", "name": "History", "store_name": "History", "password": "correct horse battery staple"})
    headers = {"Authorization": "Bearer " + signup.json()["token"]}
    assert (await client.get(f"/api/v1/agent-runs?merchant_id={store['merchant']}", headers=headers)).status_code == 403
    own = signup.json()["user"]["merchant_id"]
    assert (await client.get(f"/api/v1/agent-runs?merchant_id={own}", headers=headers)).json() == []
    assert (await client.get(f"/api/v1/agent-runs?merchant_id={own}")).status_code == 401


async def test_summary_storage_failure_is_sanitized(history_client, monkeypatch):
    client, _, store = history_client
    monkeypatch.setattr("app.api.v1.orchestration.save_plan_run", AsyncMock(side_effect=OperationalError("private", {}, Exception("secret"))))
    response = await run_plan(client, store)
    assert response.status_code == 503
    assert "secret" not in response.text and "private" not in response.text
