"""Verify a synthetic-data production deployment without changing merchant data.

No credentials, migrations, seeding, approvals or action execution are performed.
Use --check-frontend to also inspect the published SPA and its API build setting.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class CheckFailure(RuntimeError):
    """A sanitized, actionable hosting verification failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def fetch(url: str, body: dict | None = None, origin: str | None = None,
          method: str | None = None) -> tuple[int, str, object]:
    headers = {"Content-Type": "application/json"}
    if origin:
        headers.update({"Origin": origin})
    if method == "OPTIONS":
        headers.update({"Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type"})
    req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        response = urlopen(req, timeout=60)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError, OSError):
        raise CheckFailure("HTTP connection failed; check DNS, HTTPS and provider availability.") from None
    with response:
        return response.code, response.read().decode("utf-8", errors="replace"), response.headers


def api_request(base: str, path: str, body: dict | None = None,
                origin: str | None = None) -> tuple[int, object, object]:
    status, text, headers = fetch(base + path, body, origin)
    try:
        payload = json.loads(text)
    except ValueError:
        raise CheckFailure(f"{path}: HTTP {status}, expected API JSON. Check deployment protection, "
                           "project root and failed builds. Response body omitted.") from None
    return status, payload, headers


def verify_api(base: str, frontend: str) -> dict[str, object]:
    checks: dict[str, object] = {}
    status, health, _ = api_request(base, "/health")
    require(status == 200 and health == {"status": "ok"}, "/health must return HTTP 200 and status=ok.")
    status, health, _ = api_request(base, "/api/v1/health/detailed")
    require(status == 200 and isinstance(health, dict) and health.get("database") == "connected"
            and health.get("environment") == "production" and health.get("redis") == "disabled",
            "Detailed health must report production, database=connected and redis=disabled.")
    checks["health"] = health
    status, docs, _ = fetch(base + "/docs")
    require(status == 200 and "swagger-ui" in docs.lower(), "/docs must serve FastAPI Swagger UI.")
    checks["docs"] = "passed"
    status, merchants, _ = api_request(base, "/api/v1/merchants")
    require(status == 200 and isinstance(merchants, list) and bool(merchants),
            "No demo merchants available. Explicitly migrate and seed the empty disposable database.")
    merchant = merchants[0]["id"]
    status, products, _ = api_request(base, f"/api/v1/products?merchant_id={merchant}")
    require(status == 200 and isinstance(products, dict) and bool(products.get("products")),
            "Seeded demo products are unavailable.")
    product = products["products"][0]["id"]
    checks["products"] = products["total_products"]
    require(api_request(base, f"/api/v1/inventory?merchant_id={merchant}")[0] == 200,
            "Inventory request failed.")
    agents = ("pricing", "restock", "promotion", "listing")
    for agent in agents:
        status, result, _ = api_request(base, f"/api/v1/{agent}/recommend",
                                        {"merchant_id": merchant, "product_id": product})
        require(status == 200 and isinstance(result, dict) and result.get("product_id") == product,
                f"{agent} did not return a scoped specialist recommendation.")
    checks["agents"] = list(agents)
    status, plan, _ = api_request(base, "/api/v1/orchestrate",
                                {"merchant_id": merchant, "goal": "balanced_growth"})
    require(status == 200 and isinstance(plan, dict) and plan.get("products_analyzed", 0) > 0
            and plan.get("complete") is True and bool(plan.get("agent_results"))
            and all(row.get("success") is True for row in plan["agent_results"]),
            "Balanced Growth must analyze products and return successful specialist results.")
    checks["balanced_growth"] = "passed"
    for path in ("actions", "action-history"):
        require(api_request(base, f"/api/v1/{path}?merchant_id={merchant}")[0] == 200,
                f"{path} read failed.")
    # Invalid bodies ensure no valid write can occur even if a gate regresses.
    for path in ("/api/v1/actions", "/api/v1/actions/2147483647/approve",
                 "/api/v1/actions/2147483647/reject", "/api/v1/actions/2147483647/execute",
                 "/api/v1/integrations/shopify/sync"):
        require(api_request(base, path, {})[0] == 403, f"Production must block {path} with HTTP 403.")
    for path in ("status", "last-sync"):
        route = f"/api/v1/integrations/shopify/{path}?merchant_id={merchant}"
        require(api_request(base, route)[0] == 403, f"Production must block Shopify {path}.")
    checks["production_write_and_integration_gates"] = "preserved"
    for origin, allowed in ((frontend, True), ("https://unknown.invalid", False)):
        _, _, headers = api_request(base, "/health", origin=origin)
        require((headers.get("Access-Control-Allow-Origin") == origin) is allowed,
                "Exact-origin CORS response is incorrect.")
        status, _, headers = fetch(base + "/api/v1/orchestrate", origin=origin, method="OPTIONS")
        require((status == 200 and headers.get("Access-Control-Allow-Origin") == origin) is allowed,
                "CORS preflight is incorrect.")
    checks["cors"] = "exact origin and preflight passed; unknown origin rejected"
    return checks


def verify_frontend(frontend: str, base: str) -> dict[str, object]:
    status, index, _ = fetch(frontend + "/")
    require(status == 200 and 'id="root"' in index, "Frontend does not serve the React application.")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index)
    require(bool(scripts), "Frontend has no JavaScript bundle.")
    require(all(src.startswith("/assets/") for src in scripts), "Unexpected frontend script location.")
    bundles = [fetch(frontend + src) for src in scripts]
    require(all(status == 200 for status, _, _ in bundles)
            and any(base in text for _, text, _ in bundles),
            "Published JavaScript must contain the actual backend origin; rebuild with VITE_API_URL.")
    routes = ("dashboard", "products", "inventory", "ai-manager", "recommendations",
              "agent-activity", "approvals", "action-history", "integrations")
    for route in routes:
        status, page, _ = fetch(frontend + "/" + route)
        require(status == 200 and 'id="root"' in page
                and re.findall(r'<script[^>]+src="([^"]+)"', page) == scripts,
                f"Direct frontend route /{route} does not serve the same SPA.")
    require(fetch(frontend + "/assets/cartpilot-nonexistent-verification-file.js")[0] == 404,
            "A missing asset must return 404 rather than SPA HTML.")
    return {"direct_routes": list(routes), "api_build_origin": "passed", "missing_asset": "404",
            "browser_data_loading": "manual browser verification required"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frontend-origin", default="https://cartpilot.example.test")
    parser.add_argument("--check-frontend", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    frontend = args.frontend_origin.rstrip("/")
    for origin in (base, frontend):
        parsed = urlsplit(origin)
        require(parsed.scheme in ("http", "https") and bool(parsed.netloc)
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment and not parsed.path,
                "Provide HTTP(S) origins without credentials, query strings or paths.")
    checks = verify_api(base, frontend)
    if args.check_frontend:
        checks["frontend"] = verify_frontend(frontend, base)
    if args.output:
        args.output.write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    try:
        main()
    except CheckFailure as error:
        raise SystemExit(f"Deployment verification failed: {error}") from None
