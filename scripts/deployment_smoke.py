"""Read-only HTTP checks against an isolated production-mode deployment.

Usage: python scripts/deployment_smoke.py --url http://127.0.0.1:8013
No credentials, migrations, seeding or action execution are performed.
"""
import argparse
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frontend-origin", default="https://cartpilot.example.test")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    checks: dict[str, object] = {}

    def request(path: str, body: dict | None = None, origin: str | None = None) -> tuple[int, object, object]:
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(req, timeout=20) as response:
                return response.status, json.load(response), response.headers
        except HTTPError as error:
            return error.code, json.load(error), error.headers

    assert request("/health")[1] == {"status": "ok"}
    status, health, _ = request("/api/v1/health/detailed")
    assert status == 200 and health["database"] == "connected"
    checks["health"] = health
    status, merchants, _ = request("/api/v1/merchants")
    assert status == 200 and merchants, "Explicitly seed only the disposable demo DB before this check."
    merchant = merchants[0]["id"]
    status, products, _ = request(f"/api/v1/products?merchant_id={merchant}")
    assert status == 200 and products["products"]
    product = products["products"][0]["id"]
    checks["products"] = products["total_products"]
    assert request(f"/api/v1/inventory?merchant_id={merchant}")[0] == 200
    for agent in ("pricing", "restock", "promotion", "listing"):
        assert request(f"/api/v1/{agent}/recommend", {"merchant_id": merchant, "product_id": product})[0] == 200
    checks["agents"] = ["pricing", "restock", "promotion", "listing"]
    assert request("/api/v1/orchestrate", {"merchant_id": merchant, "goal": "balanced_growth"})[0] == 200
    for path in ("actions", "action-history"):
        assert request(f"/api/v1/{path}?merchant_id={merchant}")[0] == 200
    assert request("/api/v1/actions", {})[0] == 403
    assert request(f"/api/v1/integrations/shopify/status?merchant_id={merchant}")[0] == 403
    checks["production_write_and_integration_gates"] = "preserved"
    for origin, allowed in ((args.frontend_origin, True), ("https://unknown.invalid", False)):
        _, _, headers = request("/health", origin=origin)
        assert (headers.get("Access-Control-Allow-Origin") == origin) is allowed
    checks["cors"] = "known origin allowed; unknown origin not trusted"
    if args.output:
        args.output.write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
