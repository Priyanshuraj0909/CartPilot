"""Prepare a rejected 50% pricing proposal in the isolated four-product demo only."""
import json
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8012"


def request(path: str, body: dict | None = None):
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main() -> None:
    health = request("/api/v1/health/detailed")
    if health["environment"] != "test":
        raise RuntimeError("This helper only runs against the isolated test-mode demo on port 8012.")
    merchants = request("/api/v1/merchants")
    merchant = next(m["id"] for m in merchants if m["store_name"] == "Four-product Demo")
    catalog = request(f"/api/v1/products?merchant_id={merchant}")
    product = next(p["id"] for p in catalog["products"] if p["name"] == "Wireless Mouse")
    recommendation = request("/api/v1/pricing/recommend", {"merchant_id": merchant, "product_id": product})
    proposal = {**recommendation, "recommended_price": round(float(recommendation["current_price"]) * 1.5, 2),
                "price_change_percent": 50}
    action = request("/api/v1/actions", {"merchant_id": merchant, "agent": "pricing", "recommendation": proposal})
    assert action["status"] == "failed" and not action["policy"]["is_valid"]
    print(json.dumps({"action_id": action["id"], "status": action["status"],
                      "violations": action["policy"]["violations"]}, indent=2))


if __name__ == "__main__":
    main()
