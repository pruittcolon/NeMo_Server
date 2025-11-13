import os
import pytest
import httpx


@pytest.mark.integration
def test_transcripts_recent_via_gateway(gateway_base_url):
    # RAG route is proxied by the gateway at /api/transcripts/recent
    limit = int(os.getenv("TRANSCRIPTS_LIMIT", "1"))
    url = f"{gateway_base_url}/api/transcripts/recent?limit={limit}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
    except httpx.RequestError as exc:
        pytest.skip(f"Gateway not reachable ({exc})")
    # In a fresh environment this may be:
    # 200 with data, 404 with no data, or 401 if auth is required
    assert resp.status_code in {200, 401, 404}, resp.text
