"""Tests for health check endpoints and core routing."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_health_returns_ok(async_client: AsyncClient):
    """Happy path: GET /health returns 200 and {'status': 'ok'} as per Phase 1 spec."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_v1_health_returns_ok(async_client: AsyncClient):
    """Happy path: GET /api/v1/health returns 200 and {'status': 'ok'}."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_detailed_health_probe(async_client: AsyncClient):
    """Verify detailed health probe returns complete service diagnostics."""
    response = await async_client.get("/api/v1/health/detailed")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert payload["app"] == "CartPilot"
    assert "database" in payload
    assert "redis" in payload
    assert payload["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_root_info_metadata(async_client: AsyncClient):
    """Happy path: GET / returns metadata and documentation link."""
    response = await async_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "CartPilot"
    assert payload["status"] == "online"
    assert payload["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_invalid_endpoint_returns_404(async_client: AsyncClient):
    """Failure case: Requesting an unknown endpoint returns 404 Not Found."""
    response = await async_client.get("/non-existent-path")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_method_not_allowed_on_health(async_client: AsyncClient):
    """Failure case / boundary: POST to /health returns 405 Method Not Allowed."""
    response = await async_client.post("/health", json={"dummy": "data"})
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_cors_headers_present(async_client: AsyncClient):
    """Boundary condition: Verify CORS headers allow requests from frontend."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = await async_client.options("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
