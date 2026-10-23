"""MCP protocol envelope, strict tool schemas and sanitized upstream failures."""
import httpx
import pytest
from mcp_server import Adapter, dispatch


async def test_initialization_and_tool_discovery():
    adapter = Adapter()
    result = await dispatch(adapter, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert result["result"]["protocolVersion"] == "2025-06-18"
    listing = await dispatch(adapter, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert "propose_cart" in names
    assert "approve_cart" not in names
    assert "checkout" in names
    assert await dispatch(adapter, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


async def test_invalid_tool_arguments_and_method():
    adapter = Adapter()
    result = await dispatch(adapter, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "propose_cart", "arguments": {"budget_paise": 0, "items": []}}})
    assert result["result"]["isError"]
    invalid = await dispatch(adapter, {"jsonrpc": "2.0", "id": 2, "method": "bad"})
    assert invalid["error"]["code"] == -32601


async def test_mcp_search_happy_path_and_provider_failure(monkeypatch):
    adapter = Adapter()
    async def success(path, body=None):
        return {"token": "fixture", "expires_at": 9999999999} if path == "/sessions" else {"products": []}
    monkeypatch.setattr(adapter, "api", success)
    result = await dispatch(adapter, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_catalog", "arguments": {"query": "mouse"}}})
    assert not result["result"]["isError"]
    async def failure(*args):
        raise httpx.ConnectError("private credentials and provider details")
    monkeypatch.setattr(adapter, "api", failure)
    result = await dispatch(adapter, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_catalog", "arguments": {"query": "mouse"}}})
    assert result["result"]["isError"]
    assert "private credentials" not in str(result)


def test_remote_http_rejected(monkeypatch):
    monkeypatch.setenv("CARTPILOT_API_URL", "http://remote.example.test")
    with pytest.raises(ValueError):
        Adapter()


async def test_checkout_tool_only_hands_off_and_never_calls_payment_api(monkeypatch):
    adapter = Adapter()
    adapter.token, adapter.expires_at = "fixture", 9999999999
    calls = []
    async def api(path, body=None):
        calls.append(path)
        return {"path": "/shop/1#handoff=fixture"} if path.endswith("handoff") else {"status": "draft"}
    monkeypatch.setattr(adapter, "api", api)
    result = await adapter.call("checkout", {"cart_id": "00000000-0000-0000-0000-000000000001"})
    assert result["requires_human_confirmation"]
    assert all(not path.endswith("checkout") for path in calls)
    assert calls[-1].endswith("handoff")


async def test_growth_tools_do_not_create_shopper_sessions(monkeypatch):
    adapter = Adapter()
    calls = []
    async def api(path, body=None):
        calls.append(path)
        return {"opportunities": []}
    monkeypatch.setattr(adapter, "api", api)
    await adapter.call("get_growth_opportunities", {})
    assert calls == ["/merchant/opportunities"]
