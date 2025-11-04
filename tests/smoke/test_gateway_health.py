import pytest
import httpx


@pytest.mark.smoke
def test_gateway_health(gateway_base_url, services_running):
    if not services_running:
        pytest.skip("Gateway not running; skipping smoke test")
    url = f"{gateway_base_url}/health"
    with httpx.Client(timeout=5.0) as client:
        resp = client.get(url)
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        body = resp.json()
        assert body.get("status") in {"healthy", "ok", "ready"}
