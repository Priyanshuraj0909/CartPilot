"""Client credentials caching, one-time renewal and strict retry budgets."""
import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings
from app.integrations.shopify.client import ShopifyClient, ShopifyError
from app.integrations.shopify.queries import Query


def config(**overrides):
    return Settings(_env_file=None, SHOPIFY_STORE_DOMAIN="fixture-store.myshopify.com", SHOPIFY_CLIENT_ID="fixture-client", SHOPIFY_CLIENT_SECRET="fixture-secret", SHOPIFY_MERCHANT_ID=1, **overrides)


def token_response(**overrides):
    return httpx.Response(200, json={"access_token": "fixture-token", "scope": "read_products, read_inventory,read_orders", "expires_in": 86399, **overrides})


async def no_sleep(delay):
    return None


async def test_token_cached_for_concurrent_reads():
    token_calls = []
    async def handler(request):
        if request.url.path.endswith("access_token"):
            token_calls.append(request)
            await asyncio.sleep(0)
            assert parse_qs(request.content.decode())["grant_type"] == ["client_credentials"]
            return token_response()
        assert request.headers["X-Shopify-Access-Token"] == "fixture-token"
        return httpx.Response(200, json={"data": {"ok": True}})
    client = ShopifyClient(config(), transport=httpx.MockTransport(handler))
    assert await asyncio.gather(*(client.read(Query.SHOP) for _ in range(4))) == [{"ok": True}] * 4
    assert len(token_calls) == 1


async def test_token_renewed_before_expiry(monkeypatch):
    clock = [1000]
    monkeypatch.setattr("app.integrations.shopify.client.time.monotonic", lambda: clock[0])
    calls = []
    def handler(request):
        calls.append(request)
        return token_response(expires_in=120)
    client = ShopifyClient(config(), transport=httpx.MockTransport(handler))
    await client._get_access_token()
    clock[0] = 1059
    await client._get_access_token()
    assert len(calls) == 1
    clock[0] = 1060
    await client._get_access_token()
    assert len(calls) == 2


async def test_401_refreshes_once_then_reuses_token_through_retries():
    token_calls, api_calls = [], []
    replies = [401, 503, 200]
    def handler(request):
        if request.url.path.endswith("access_token"):
            token_calls.append(request)
            return token_response(access_token=f"token-{len(token_calls)}")
        api_calls.append(request)
        return httpx.Response(replies.pop(0), json={"data": {"ok": True}})
    client = ShopifyClient(config(SHOPIFY_MAX_RETRIES=1), transport=httpx.MockTransport(handler), sleep=no_sleep)
    assert await client.read(Query.SHOP) == {"ok": True}
    assert len(token_calls) == 2
    assert [r.headers["X-Shopify-Access-Token"] for r in api_calls] == ["token-1", "token-2", "token-2"]


@pytest.mark.parametrize("status", [401, 503])
async def test_auth_and_network_budgets_are_independent(status):
    token_calls, api_calls = [], []
    def handler(request):
        if request.url.path.endswith("access_token"):
            token_calls.append(request)
            return token_response()
        api_calls.append(request)
        return httpx.Response(status)
    client = ShopifyClient(config(SHOPIFY_MAX_RETRIES=0), transport=httpx.MockTransport(handler), sleep=no_sleep)
    with pytest.raises(ShopifyError):
        await client.read(Query.SHOP)
    assert len(token_calls) == (2 if status == 401 else 1)
    assert len(api_calls) == (2 if status == 401 else 1)


@pytest.mark.parametrize("patch", [{"access_token": " "}, {"expires_in": 60}, {"expires_in": True}, {"expires_in": "86399"}, {"scope": "read_products"}, {"scope": None}])
async def test_malformed_or_insufficient_token_is_rejected(patch):
    client = ShopifyClient(config(), transport=httpx.MockTransport(lambda _: token_response(**patch)))
    with pytest.raises(ShopifyError) as error:
        await client.read(Query.SHOP)
    assert error.value.code == "token_response"


async def test_token_failure_is_sanitized(caplog):
    client = ShopifyClient(config(), transport=httpx.MockTransport(lambda _: httpx.Response(401, text="fixture-secret")))
    with pytest.raises(ShopifyError) as error:
        await client.read(Query.SHOP)
    assert "fixture-secret" not in str(error.value) + caplog.text


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_token_provider_outage_is_not_reported_as_bad_credentials(status):
    client = ShopifyClient(config(), transport=httpx.MockTransport(lambda _: httpx.Response(status, text="private-provider-error")))
    with pytest.raises(ShopifyError) as error:
        await client.read(Query.SHOP)
    assert error.value.status_code == 503 and error.value.code == "token_unavailable"
    assert "private-provider-error" not in str(error.value)


@pytest.mark.parametrize("field,value", [("SHOPIFY_AUTO_SYNC_INTERVAL_SECONDS", 59), ("SHOPIFY_AUTO_SYNC_INTERVAL_SECONDS", 86401)])
def test_worker_interval_boundaries(field, value):
    with pytest.raises(ValueError):
        config(**{field: value})
