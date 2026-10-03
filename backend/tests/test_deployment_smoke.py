"""Hosting checker failures must be actionable, secret-safe and read-only."""
import importlib.util
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location(
    "deployment_smoke", Path(__file__).resolve().parents[2] / "scripts/deployment_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
BASE = "https://backend.example.test"
FRONTEND = "https://frontend.example.test"


@pytest.fixture
def serving_api(monkeypatch):
    calls = []
    def fetch(url, body=None, origin=None, method=None):
        calls.append((url, body, method))
        if method == "OPTIONS":
            return (200, "OK", {"Access-Control-Allow-Origin": FRONTEND}) if origin == FRONTEND else (400, "Denied", {})
        headers = {"Access-Control-Allow-Origin": FRONTEND} if origin == FRONTEND else {}
        path = url.removeprefix(BASE)
        if path == "/docs":
            return 200, "<html>swagger-ui</html>", headers
        if body == {} or "/integrations/shopify/" in path:
            return 403, json.dumps({"detail": "Local only"}), headers
        if path == "/health":
            payload = {"status": "ok"}
        elif path == "/api/v1/health/detailed":
            payload = {"database": "connected", "redis": "disabled", "environment": "production"}
        elif path == "/api/v1/merchants":
            payload = [{"id": 1}]
        elif path.startswith("/api/v1/products"):
            payload = {"products": [{"id": 1}], "total_products": 25}
        elif path == "/api/v1/orchestrate":
            payload = {"products_analyzed": 25, "complete": True, "agent_results": [{"success": True}]}
        elif path.endswith("/recommend"):
            payload = {"product_id": 1}
        else:
            payload = []
        return 200, json.dumps(payload), headers
    monkeypatch.setattr(smoke, "fetch", fetch)
    return calls, fetch


def test_verified_api_never_sends_valid_action_or_sync_payload(serving_api):
    calls, _ = serving_api
    result = smoke.verify_api(BASE, FRONTEND)
    assert result["products"] == 25
    assert result["balanced_growth"] == "passed"
    writes = [(url, body) for url, body, _ in calls if body is not None
              and ("/actions" in url or "/shopify/" in url)]
    assert len(writes) == 5 and all(body == {} for _, body in writes)


@pytest.mark.parametrize("status", [401, 404, 500])
def test_non_json_hosting_error_is_sanitized(monkeypatch, status):
    monkeypatch.setattr(smoke, "fetch", lambda *a, **k: (status, "<html>private-token</html>", {}))
    with pytest.raises(smoke.CheckFailure, match=f"HTTP {status}") as error:
        smoke.api_request(BASE, "/health")
    assert "private-token" not in str(error.value)
    assert "deployment protection" in str(error.value)


def test_http_error_body_is_read_without_raising(monkeypatch):
    def denied(*args, **kwargs):
        raise HTTPError(BASE, 403, "Forbidden", {}, BytesIO(b'{"detail":"Local only"}'))
    monkeypatch.setattr(smoke, "urlopen", denied)
    assert smoke.api_request(BASE, "/api/v1/actions", {})[:2] == (403, {"detail": "Local only"})


def test_partial_orchestration_is_not_reported_as_verified(monkeypatch, serving_api):
    _, original = serving_api
    def partial(url, *args, **kwargs):
        if url.endswith("/orchestrate"):
            return 200, json.dumps({"products_analyzed": 25, "agent_results": [{"success": False}]}), {}
        return original(url, *args, **kwargs)
    monkeypatch.setattr(smoke, "fetch", partial)
    with pytest.raises(smoke.CheckFailure, match="Balanced Growth"):
        smoke.verify_api(BASE, FRONTEND)


@pytest.mark.parametrize("bad_state", ["empty_merchants", "disconnected", "development", "wildcard_cors"])
def test_unready_or_unsafe_deployment_fails(monkeypatch, serving_api, bad_state):
    _, original = serving_api
    def faulty(url, *args, **kwargs):
        status, payload, headers = original(url, *args, **kwargs)
        if bad_state == "empty_merchants" and url.endswith("/merchants"):
            payload = "[]"
        if url.endswith("/health/detailed") and bad_state in ("disconnected", "development"):
            data = json.loads(payload)
            data["database" if bad_state == "disconnected" else "environment"] = bad_state
            payload = json.dumps(data)
        if bad_state == "wildcard_cors" and kwargs.get("origin") == FRONTEND:
            headers = {"Access-Control-Allow-Origin": "*"}
        return status, payload, headers
    monkeypatch.setattr(smoke, "fetch", faulty)
    with pytest.raises(smoke.CheckFailure):
        smoke.verify_api(BASE, FRONTEND)


@pytest.mark.parametrize("fault", [None, "stale_bundle", "route_404", "asset_fallback"])
def test_frontend_routes_and_api_build_setting(monkeypatch, fault):
    index = '<div id="root"></div><script type="module" src="/assets/app.js"></script>'
    def frontend(url, *args, **kwargs):
        if url.endswith("/assets/app.js"):
            return 200, "http://localhost:8000" if fault == "stale_bundle" else BASE, {}
        if url.endswith("cartpilot-nonexistent-verification-file.js"):
            return (200, index, {}) if fault == "asset_fallback" else (404, "missing", {})
        if url.endswith("/products") and fault == "route_404":
            return 404, "missing", {}
        return 200, index, {}
    monkeypatch.setattr(smoke, "fetch", frontend)
    if fault:
        with pytest.raises(smoke.CheckFailure):
            smoke.verify_frontend(FRONTEND, BASE)
    else:
        result = smoke.verify_frontend(FRONTEND, BASE)
        assert len(result["direct_routes"]) == 9
        assert result["browser_data_loading"] == "manual browser verification required"
