import os
import socket
import contextlib
import pytest


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(timeout)
            try:
                return sock.connect_ex((host, port)) == 0
            except OSError:
                return False
    except PermissionError:
        # Some sandboxes disallow raw socket creation; treat as "closed" so tests skip gracefully.
        return False


@pytest.fixture(scope="session")
def gateway_base_url() -> str:
    # Public entrypoint for integration and smoke tests
    return os.getenv("GATEWAY_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def services_running() -> bool:
    # Consider services "running" if the gateway port is open
    url = os.getenv("GATEWAY_URL", "http://localhost:8000")
    host_port = url.split("://", 1)[-1]
    host, port_str = host_port.split(":") if ":" in host_port else (host_port, "8000")
    try:
        port = int(port_str)
    except ValueError:
        port = 8000
    return _is_port_open(host, port)


def pytest_collection_modifyitems(items):
    # Auto-skip integration/performance if services aren’t running or not explicitly enabled
    run_integration = os.getenv("RUN_INTEGRATION", "0") in {"1", "true", "yes"}
    run_performance = os.getenv("RUN_PERFORMANCE", "0") in {"1", "true", "yes"}

    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(pytest.mark.skip(reason="Set RUN_INTEGRATION=1 to enable integration tests"))
        if "performance" in item.keywords and not run_performance:
            item.add_marker(pytest.mark.skip(reason="Set RUN_PERFORMANCE=1 to enable performance tests"))
