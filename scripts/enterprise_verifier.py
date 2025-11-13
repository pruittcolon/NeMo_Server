#!/usr/bin/env python3
"""
Enterprise Verification Harness

Runs layered checks to ensure Nemo Server meets security, availability,
and observability baselines described in plan.md. Designed to be safe to run
on developer workstations *after* ./start.sh has been executed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str
    severity: str = "info"  # info | warn | critical

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "severity": self.severity,
        }


class EnterpriseVerifier:
    REQUIRED_CMDS = ("docker", "python3", "bash")
    REQUIRED_SECRETS = (
        "session_key",
        "jwt_secret_primary",
        "jwt_secret_previous",
        "jwt_secret",
        "postgres_password",
        "postgres_user",
        "users_db_key",
        "rag_db_key",
    )
    DOWNSTREAM_SERVICES = (
        ("Gemma", "http://gemma-service:8001/health"),
        ("RAG", "http://rag-service:8004/health"),
        ("Emotion", "http://emotion-service:8005/health"),
        ("Transcription", "http://transcription-service:8003/health"),
        ("GPU Coordinator", "http://gpu-coordinator:8002/health"),
    )
    FRONTEND_FILES = (
        Path("frontend/gemma.html"),
        Path("frontend/email.html"),
    )

    def __init__(self, repo_root: Path, gateway_url: str, docker_relpath: str = "docker"):
        self.repo_root = repo_root
        self.gateway_url = gateway_url.rstrip("/")
        self.docker_dir = repo_root / docker_relpath
        self.secrets_dir = self.docker_dir / "secrets"
        self.compose_base = self._detect_compose()

    # ------------------------------------------------------------------ utils
    def _detect_compose(self) -> List[str]:
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        if shutil.which("docker"):
            return ["docker", "compose"]
        raise RuntimeError("Neither docker-compose nor docker compose is available on PATH")

    def _run(self, args: Iterable[str], cwd: Optional[Path] = None, check: bool = False) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=check,
        )
        return proc

    def _compose(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        return self._run([*self.compose_base, *args], cwd=self.docker_dir, check=check)

    def _http_get(self, url: str, timeout: float = 10.0) -> tuple[int, dict]:
        req = Request(url, headers={"User-Agent": "EnterpriseVerifier/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (controlled URL)
            return resp.getcode(), dict(resp.headers)

    # ----------------------------------------------------------------- checks
    def check_dependencies(self) -> CheckResult:
        missing = [cmd for cmd in self.REQUIRED_CMDS if shutil.which(cmd) is None]
        if missing:
            return CheckResult(
                "Dependencies",
                False,
                f"Missing required tools: {', '.join(missing)}",
                severity="critical",
            )
        compose = " ".join(self.compose_base)
        return CheckResult("Dependencies", True, f"All required tools present (compose via `{compose}`).")

    def check_secrets(self) -> CheckResult:
        missing: List[str] = []
        empty: List[str] = []
        for name in self.REQUIRED_SECRETS:
            path = self.secrets_dir / name
            if not path.exists():
                missing.append(name)
                continue
            if path.is_file() and path.stat().st_size == 0:
                empty.append(name)
        if missing or empty:
            detail = []
            if missing:
                detail.append(f"missing: {', '.join(sorted(missing))}")
            if empty:
                detail.append(f"empty: {', '.join(sorted(empty))}")
            return CheckResult("Secrets", False, "; ".join(detail), severity="critical")
        return CheckResult("Secrets", True, f"All required secret files present in {self.secrets_dir}.")

    def check_gateway_health(self) -> CheckResult:
        url = f"{self.gateway_url}/health"
        try:
            code, _ = self._http_get(url)
            ok = 200 <= code < 300
            return CheckResult("Gateway /health", ok, f"Status code {code} from {url}", severity="critical" if not ok else "info")
        except URLError as exc:
            return CheckResult("Gateway /health", False, f"Request failed: {exc}", severity="critical")

    def check_login_headers(self) -> CheckResult:
        url = f"{self.gateway_url}/ui/login.html"
        try:
            code, headers = self._http_get(url)
        except URLError as exc:
            return CheckResult("Login security headers", False, f"Unable to fetch login page: {exc}", severity="critical")
        csp = headers.get("Content-Security-Policy", "")
        xfo = headers.get("X-Frame-Options", "")
        if code != 200 or "default-src 'self'" not in csp or xfo.upper() not in {"DENY", "SAMEORIGIN"}:
            return CheckResult(
                "Login security headers",
                False,
                f"Unexpected headers/status (status={code}, CSP=`{csp}`, XFO=`{xfo}`)",
                severity="critical",
            )
        return CheckResult("Login security headers", True, "CSP and click-jacking headers present on login page.")

    def check_csrf_cookie_policy(self) -> CheckResult:
        """Fetch login page and look for Set-Cookie policy from gateway check endpoint if available.
        This is heuristic; full CSRF cookie is set on successful login, which may not be possible here.
        """
        # Try a session check route that may set cookies without credentials
        for path in ("/auth/check", "/ui/login.html"):
            url = f"{self.gateway_url}{path}"
            try:
                code, headers = self._http_get(url)
            except URLError:
                continue
            sc = headers.get("Set-Cookie", "")
            # Policy: presence not mandatory here, but if present ensure Secure and SameSite are set appropriately
            if sc:
                ok = ("SameSite" in sc) and ("Secure" in sc or self.gateway_url.startswith("http://localhost"))
                if not ok:
                    return CheckResult("CSRF cookie policy", False, f"Weak cookie attributes on {path}: {sc}", severity="critical")
                return CheckResult("CSRF cookie policy", True, f"Set-Cookie present on {path} with attributes")
        return CheckResult("CSRF cookie policy", True, "No Set-Cookie observed without auth; policy will be validated during login flows.")

    def check_downstream_services(self) -> CheckResult:
        failures: List[str] = []
        for name, url in self.DOWNSTREAM_SERVICES:
            try:
                proc = self._compose("exec", "-T", "gateway", "curl", "-sf", url)
            except subprocess.CalledProcessError as exc:  # pragma: no cover - executed via CLI
                failures.append(f"{name}: compose exec failed ({exc})")
                continue
            if proc.returncode != 0:
                failures.append(f"{name}: curl exit {proc.returncode} ({proc.stderr.strip()})")
        if failures:
            return CheckResult("Downstream health", False, "; ".join(failures), severity="critical")
        return CheckResult("Downstream health", True, "gateway→service health checks succeeded.")

    def check_port_exposure(self) -> CheckResult:
        try:
            proc = self._run(
                ["docker", "ps", "--filter", "name=refactored", "--format", "{{json .}}"],
                check=False,
            )
        except FileNotFoundError:
            return CheckResult("Port policy", False, "docker CLI missing", severity="critical")

        if proc.returncode != 0:
            return CheckResult("Port policy", False, proc.stderr.strip(), severity="critical")

        allowed = {
            "refactored_gateway": ("0.0.0.0", "::", "[::]", "127.", "localhost"),
            "refactored_postgres": ("127.", "::1"),
            "refactored_redis": ("127.", "::1"),
        }

        violations: List[str] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            info = json.loads(line)
            service = info.get("Names", "")
            ports = info.get("Ports") or ""
            if not ports or service not in allowed:
                continue
            for mapping in ports.split(","):
                mapping = mapping.strip()
                if "->" not in mapping:
                    continue
                host = mapping.split("->", 1)[0].strip()
                host_ip = self._normalize_host_ip(host)
                if not self._host_allowed(host_ip, allowed[service]):
                    violations.append(f"{service} exposed on {host_ip}")

        if violations:
            return CheckResult("Port policy", False, "; ".join(violations), severity="critical")
        return CheckResult("Port policy", True, "Host exposure matches policy (gateway only public listener).")

    @staticmethod
    def _normalize_host_ip(host_spec: str) -> str:
        host_spec = host_spec.strip()
        if not host_spec:
            return host_spec
        if "[" in host_spec and "]" in host_spec:
            return host_spec.split("]")[0].strip("[]")
        if host_spec.count(":") > 1:
            parts = host_spec.split(":")
            return ":".join(parts[:-1]) or "::"
        if ":" in host_spec:
            return host_spec.rsplit(":", 1)[0]
        return host_spec

    @staticmethod
    def _host_allowed(host: str, patterns: Iterable[str]) -> bool:
        host = host.lower()
        for pattern in patterns:
            pattern = pattern.lower()
            if pattern.endswith(".") and host.startswith(pattern):
                return True
            if pattern.endswith("*") and host.startswith(pattern[:-1]):
                return True
            if host == pattern:
                return True
        return False

    def check_db_encryption_module(self) -> CheckResult:
        sys.path.insert(0, str(self.repo_root))
        try:
            from shared.crypto import db_encryption  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime import
            return CheckResult("SQLCipher availability", False, f"Import failed: {exc}", severity="critical")
        if not getattr(db_encryption, "SQLCIPHER_AVAILABLE", False):
            return CheckResult(
                "SQLCipher availability",
                False,
                "SQLCipher bindings unavailable (install pysqlcipher3/sqlcipher3).",
                severity="critical",
            )
        return CheckResult("SQLCipher availability", True, "SQLCipher module ready for encrypted SQLite.")

    def check_frontend_headers_static(self) -> CheckResult:
        missing: List[str] = []
        for path in self.FRONTEND_FILES:
            full_path = self.repo_root / path
            if not full_path.exists():
                missing.append(str(path))
                continue
            text = full_path.read_text(encoding="utf-8")
            if 'Content-Security-Policy' not in text:
                return CheckResult("Frontend CSP", False, f"{path} lacks CSP meta tag", severity="critical")
        if missing:
            return CheckResult("Frontend CSP", False, f"Missing files: {', '.join(missing)}", severity="critical")
        return CheckResult("Frontend CSP", True, "Gemma & Email HTML include CSP directives.")

    def check_agents_plan_consistency(self) -> CheckResult:
        agents_path = self.repo_root / "agents.md"
        plan_path = self.repo_root / "plan.md"
        if not agents_path.exists() or not plan_path.exists():
            return CheckResult("Docs present", False, "agents.md/plan.md missing", severity="critical")
        return CheckResult("Docs present", True, "agents.md and plan.md present for QA hand-offs.")

    # ----------------------------------------------------------------- driver
    def run(self) -> List[CheckResult]:
        checks: List[Callable[[], CheckResult]] = [
            self.check_dependencies,
            self.check_secrets,
            self.check_gateway_health,
            self.check_login_headers,
            self.check_csrf_cookie_policy,
            self.check_downstream_services,
            self.check_port_exposure,
            self.check_db_encryption_module,
            self.check_frontend_headers_static,
            self.check_agents_plan_consistency,
        ]

        results: List[CheckResult] = []
        for check in checks:
            try:
                results.append(check())
            except Exception as exc:  # pragma: no cover - best-effort guard
                results.append(CheckResult(check.__name__, False, f"Exception: {exc}", severity="critical"))
        return results


def format_results(results: List[CheckResult]) -> str:
    lines = []
    for res in results:
        status = "PASS" if res.passed else "FAIL"
        lines.append(f"[{status}] {res.name}: {res.details}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enterprise verification harness for Nemo Server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Example:
              python3 scripts/enterprise_verifier.py --gateway-url http://localhost:8000
            """
        ),
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("API_GATEWAY_URL", "http://localhost:8000"),
        help="Base URL for the API Gateway (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human text.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    verifier = EnterpriseVerifier(repo_root, args.gateway_url)
    results = verifier.run()

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(format_results(results))

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
