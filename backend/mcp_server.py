"""Minimal MCP stdio adapter over the guarded HTTP API. No database access.

Run from backend with its virtualenv. Credentials are owner-provided environment
variables, never tool arguments. Human cart approval stays outside this adapter.
"""
import asyncio
import json
import os
import sys
import time
from urllib.parse import urlparse
from uuid import UUID
import httpx
from pydantic import Field, ValidationError
from app.schemas.commerce import Contract, CartRequest, SearchRequest


class Empty(Contract):
    pass


class ProductRequest(Contract):
    product_id: int = Field(gt=0)


class CartId(Contract):
    cart_id: UUID


TOOLS = {
    "search_catalog": (SearchRequest, "Search products using budget, category, learned and semantic signals; results never execute actions."),
    "get_product": (ProductRequest, "Read a product from this store's bounded public catalog."),
    "propose_cart": (CartRequest, "Create a server-priced draft cart. Does not approve, charge, reserve stock or place an order."),
    "get_cart": (CartId, "Read the current state of a cart owned by this shopper session."),
    "get_order_audit_trail": (CartId, "Verify and read the shopper's cart mandate chain. Test activity is not a real order."),
}


class Adapter:
    def __init__(self) -> None:
        self.base = os.environ.get("CARTPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")
        parsed = urlparse(self.base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Use HTTPS or a local API URL without embedded credentials.")
        self.merchant = int(os.environ.get("CARTPILOT_MERCHANT_ID", "1"))
        if self.merchant <= 0:
            raise ValueError("Merchant ID must be positive.")
        self.token = ""
        self.expires_at = 0

    async def api(self, path: str, body: dict | None = None) -> dict:
        headers = {}
        account = os.environ.get("CARTPILOT_ACCOUNT_TOKEN", "")
        if account:
            headers["Authorization"] = f"Bearer {account}"
        if self.token:
            headers["X-CartPilot-Buyer"] = self.token
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request("GET" if body is None else "POST", self.base + "/api/v1/commerce" + path,
                headers=headers, **({"json": body} if body is not None else {}))
            response.raise_for_status()
            return response.json()

    async def call(self, name: str, arguments: dict) -> dict:
        if name not in TOOLS:
            raise ValueError("Unknown tool.")
        contract, _ = TOOLS[name]
        body = contract.model_validate(arguments).model_dump(mode="json")
        if name == "get_product":
            store = await self.api(f"/storefront/{self.merchant}")
            product = next((p for p in store["products"] if p["id"] == body["product_id"]), None)
            if product is None:
                raise ValueError("Product not found in the bounded catalog.")
            return product
        if not self.token or self.expires_at <= time.time():
            # Never silently replace an expired session when accessing an existing
            # cart: its capability must not be confused with a new shopper identity.
            if name in {"get_cart", "get_order_audit_trail"}:
                raise ValueError("This adapter has no active cart session. Start with search or propose_cart.")
            identity = await self.api("/sessions", {"merchant_id": self.merchant})
            self.token, self.expires_at = identity["token"], identity["expires_at"]
        if name == "search_catalog":
            return await self.api("/search", body)
        if name == "propose_cart":
            return await self.api("/carts", body)
        suffix = "/audit" if name == "get_order_audit_trail" else ""
        return await self.api(f"/carts/{body['cart_id']}{suffix}")


async def dispatch(adapter: Adapter, message: dict) -> dict | None:
    request_id = message.get("id")
    if "id" not in message:
        return None
    reply = {"jsonrpc": "2.0", "id": request_id}
    method = message.get("method")
    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return {**reply, "error": {"code": -32600, "message": "Invalid request"}}
    if method == "initialize":
        return {**reply, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
            "serverInfo": {"name": "cartpilot-shopping", "version": "1.0.0"},
            "instructions": "Shopping tools create drafts only. A human must review/approve and separately confirm checkout through the application. Never claim test carts are real purchases."}}
    if method == "ping":
        return {**reply, "result": {}}
    if method == "tools/list":
        return {**reply, "result": {"tools": [{"name": name, "description": description,
            "inputSchema": model.model_json_schema(), "annotations": {"readOnlyHint": name != "propose_cart",
            "destructiveHint": False, "openWorldHint": False}} for name, (model, description) in TOOLS.items()]}}
    if method != "tools/call":
        return {**reply, "error": {"code": -32601, "message": "Method not found"}}
    params = message.get("params")
    if not isinstance(params, dict) or not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
        return {**reply, "error": {"code": -32602, "message": "Invalid tool parameters"}}
    try:
        data = await adapter.call(params["name"], params.get("arguments", {}))
        result = {"content": [{"type": "text", "text": json.dumps(data)}], "isError": False}
    except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
        result = {"content": [{"type": "text", "text": "Shopping request failed. Check arguments, store publication and session expiry. No purchase was executed."}], "isError": True}
    return {**reply, "result": result}


async def main() -> None:
    adapter = Adapter()
    while True:
        line = await asyncio.to_thread(sys.stdin.buffer.readline, 1048577)
        if not line:
            break
        try:
            if len(line) > 1048576:
                raise ValueError()
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError()
            result = await dispatch(adapter, message)
        except (ValueError, UnicodeDecodeError):
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON request"}}
        if result is not None:
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
