"""Auth budgets survive requests, expire predictably, and fail closed."""
import hashlib
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.deps import get_database_session
from app.core.config import Settings, settings
from app.main import app
from app.models.auth_rate_limit import AuthRateLimit
from app.services.auth_limits import record_attempt


@pytest.fixture
async def limited_client(async_client, db_session, monkeypatch):
    async def override():
        yield db_session
    app.dependency_overrides[get_database_session] = override
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_IDENTITY_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PEER_ATTEMPTS", 10)
    monkeypatch.setattr("app.services.auth_limits.time.time", lambda: 1000)
    try:
        yield async_client, db_session
    finally:
        app.dependency_overrides.clear()


async def test_identity_budget_and_case_normalization(limited_client):
    client, session = limited_client
    for email, expected in [("Owner@example.test", 401), ("owner@EXAMPLE.test", 401), ("owner@example.test", 429)]:
        result = await client.post("/api/v1/auth/login", json={"email": email, "password": "incorrect long password"})
        assert result.status_code == expected
    assert result.headers["retry-after"] == "900"
    assert result.headers["cache-control"] == "no-store"
    counters = (await session.scalars(select(AuthRateLimit))).all()
    assert all(len(counter.key) == 64 for counter in counters)
    assert "owner" not in repr([counter.key for counter in counters])


async def test_peer_budget_covers_invalid_requests_and_ignores_spoofed_headers(limited_client, monkeypatch):
    client, _ = limited_client
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PEER_ATTEMPTS", 1)
    for spoof, expected in [("1.1.1.1", 422), ("2.2.2.2", 429)]:
        response = await client.post("/api/v1/auth/signup", json={}, headers={"X-Forwarded-For": spoof})
        assert response.status_code == expected


async def test_budget_recovers_at_exact_expiry(limited_client, monkeypatch):
    client, _ = limited_client
    body = {"store_name": "Missing", "password": "incorrect long password", "new_email": "new@example.test"}
    for expected in [401, 401, 429]:
        assert (await client.post("/api/v1/auth/recover-email", json=body)).status_code == expected
    monkeypatch.setattr("app.services.auth_limits.time.time", lambda: 1900)
    assert (await client.post("/api/v1/auth/recover-email", json=body)).status_code == 401


async def test_independent_routes_and_identities(limited_client):
    client, _ = limited_client
    for _ in range(2):
        await client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "incorrect long password"})
    assert (await client.post("/api/v1/auth/login", json={"email": "b@example.test", "password": "incorrect long password"})).status_code == 401
    assert (await client.post("/api/v1/auth/signup", json={})).status_code == 422


async def test_shared_counter_and_saturated_boundary(db_session):
    key = hashlib.sha256(b"shared-key").hexdigest()
    assert await record_attempt(db_session, key, 1, 100, 60) == 0
    assert await record_attempt(db_session, key, 1, 159, 60) == 1
    assert await record_attempt(db_session, key, 1, 159, 60) == 1
    assert (await db_session.get(AuthRateLimit, key)).attempts == 2
    assert await record_attempt(db_session, key, 1, 160, 60) == 0


async def test_limit_storage_failure_does_not_allow_login(limited_client, monkeypatch):
    client, _ = limited_client
    monkeypatch.setattr("app.services.auth_limits.record_attempt", AsyncMock(side_effect=OperationalError("private", {}, Exception("secret"))))
    response = await client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "incorrect long password"})
    assert response.status_code == 503
    assert "secret" not in response.text and "private" not in response.text


@pytest.mark.parametrize("field,value", [("AUTH_RATE_LIMIT_WINDOW_SECONDS", 59), ("AUTH_RATE_LIMIT_IDENTITY_ATTEMPTS", 0), ("AUTH_RATE_LIMIT_PEER_ATTEMPTS", 10001)])
def test_invalid_limit_configuration(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})
