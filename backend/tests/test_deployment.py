"""Deployment configuration, sanitization and optional infrastructure contracts."""
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from app.core.config import Settings, settings
from app.main import app

@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_managed_database_url_normalizes(scheme):
    config = Settings(_env_file=None, DATABASE_URL=f"{scheme}://demo:p%40ss@db.example.test/store?sslmode=require")
    url = make_url(config.DATABASE_URL)
    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p@ss"
    assert url.query == {"ssl": "require"}

@pytest.mark.parametrize("values", [
    {"ENVIRONMENT": "staging"}, {"PORT": 0}, {"PORT": 65536},
    {"DATABASE_URL": "invalid-sensitive-value"},
    {"ENVIRONMENT": "production", "DATABASE_URL": ""},
    {"ENVIRONMENT": "production", "LOG_LEVEL": "DEBUG"},
])
def test_invalid_deployment_config_is_sanitized(values):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "invalid-sensitive-value" not in str(error.value)
    assert "input_value" not in str(error.value)

@pytest.mark.parametrize("port", [1, 65535])
def test_port_boundaries(port):
    assert Settings(_env_file=None, PORT=port).PORT == port

@pytest.mark.parametrize("mode,local", [("development", True), ("test", True), ("production", False)])
def test_environment_policy(mode, local):
    config = Settings(_env_file=None, ENVIRONMENT=mode, DATABASE_URL="sqlite+aiosqlite:///:memory:")
    assert config.is_local_environment is local
    assert app.debug is False

async def test_disabled_redis_never_connects_and_database_health_remains_ok(async_client, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")
    async def connected(): return True
    monkeypatch.setattr("app.api.v1.health.check_db_connection", connected)
    from app.core import redis
    monkeypatch.setattr(redis, "get_redis_client", lambda: pytest.fail("Disabled Redis must not connect"))
    assert await redis.check_redis_connection() is False
    response = await async_client.get("/api/v1/health/detailed")
    assert response.json()["status"] == "ok"
    assert response.json()["redis"] == "disabled"

async def test_production_preserves_write_and_integration_gates(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    for path, body in [("/api/v1/actions", {}), ("/api/v1/integrations/shopify/sync", {"merchant_id": 1})]:
        assert (await async_client.post(path, json=body)).status_code == 403
    assert (await async_client.get("/api/v1/integrations/shopify/status?merchant_id=1")).status_code == 403


def test_optional_shopify_merchant_can_be_unset_in_host_environment():
    assert Settings(_env_file=None, SHOPIFY_MERCHANT_ID="").SHOPIFY_MERCHANT_ID is None


async def test_database_connection_refusal_is_sanitized_503(async_client):
    from app.api.deps import get_database_session
    class Unavailable:
        async def execute(self, statement):
            raise ConnectionRefusedError("private-connection-details")
        @property
        def no_autoflush(self):
            from contextlib import nullcontext
            return nullcontext()
    async def override():
        yield Unavailable()
    app.dependency_overrides[get_database_session] = override
    try:
        response = await async_client.get("/api/v1/merchants")
        assert response.status_code == 503
        assert response.json() == {"detail": "Store data is temporarily unavailable; try again."}
        assert "private-connection-details" not in response.text
    finally:
        app.dependency_overrides.pop(get_database_session, None)

@pytest.mark.parametrize("mode", ["pooled", "null"])
def test_database_pool_modes(mode):
    assert Settings(_env_file=None, DATABASE_POOL_MODE=mode).DATABASE_POOL_MODE == mode


def test_unknown_pool_mode_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_POOL_MODE="unbounded")


async def test_serverless_pool_releases_connections(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from sqlalchemy import text
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'serverless.sqlite'}", poolclass=NullPool)
    try:
        for _ in range(2):
            async with engine.connect() as connection:
                assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()
