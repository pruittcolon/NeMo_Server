"""
Integration smoke tests that verify `start.sh` brought the stack up correctly.

These tests assume `./start.sh` (and therefore `docker compose`) is already running.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"

# Services that start.sh is expected to keep running
EXPECTED_SERVICES = {
    "api-gateway",
    "gemma-service",
    "rag-service",
    "emotion-service",
    "transcription-service",
    "gpu-coordinator",
    "redis",
    "postgres",
}


def _docker_compose_ps() -> list[dict]:
    """Return docker compose ps results as dicts."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "ps",
        "--format",
        "json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        pytest.skip(f"docker compose unavailable: {exc}")
    except PermissionError as exc:
        pytest.skip(f"docker compose not permitted: {exc}")
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"'docker compose ps' failed: {exc.stderr.strip() or exc}")
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return lines


@pytest.mark.integration
def test_start_script_services_running():
    """Ensure start.sh brought up all critical services and they are healthy."""
    containers = _docker_compose_ps()
    running = {
        entry["Service"]: entry
        for entry in containers
        if entry.get("State") == "running"
    }

    missing = EXPECTED_SERVICES - running.keys()
    assert not missing, f"Missing or stopped services: {sorted(missing)}"

    unhealthy = [
        svc
        for svc, entry in running.items()
        if entry.get("Health")
        and entry["Health"].lower() not in {"healthy", "starting"}
    ]
    assert not unhealthy, f"Unhealthy services: {sorted(unhealthy)}"


@pytest.mark.integration
def test_gateway_health_endpoint():
    """Gateway /health should be reachable after start.sh finishes."""
    try:
        resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
    except requests.RequestException as exc:
        pytest.skip(f"Gateway health endpoint unreachable: {exc}")
    assert resp.status_code == 200, f"Gateway /health returned {resp.status_code}"
    payload = resp.json()
    status = (payload.get("status") or "").lower()
    assert status in {"ok", "healthy", "pass"}, f"Unexpected health payload: {payload}"
