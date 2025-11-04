#!/usr/bin/env python3
"""
Security Implementation Verification Script
Verifies that all security phases are properly implemented
"""

import os
import sys
from pathlib import Path
import json

def print_section(title):
    """Print section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def check_secrets():
    """Verify all required secrets exist"""
    print_section("Phase 5: Docker Secrets Verification")
    
    base_dir = Path(__file__).parent.parent  # Go up from scripts/ to root
    secrets_dir = base_dir / "docker" / "secrets"
    
    required_secrets = [
        "jwt_secret",
        "session_key",
        "postgres_user",
        "postgres_password",
        "users_db_key",
        "rag_db_key",
        "redis_password",
        "huggingface_token"
    ]
    
    all_exist = True
    for secret in required_secrets:
        secret_file = secrets_dir / secret
        if secret_file.exists():
            size = secret_file.stat().st_size
            perms = oct(secret_file.stat().st_mode)[-3:]
            if perms in {"600", "640", "644"}:
                print(f"  ✅ {secret:25s} ({size:4d} bytes)")
            else:
                print(f"  ❌ {secret:25s} (perms: {perms}, expected 644)")
                all_exist = False
        else:
            print(f"  ❌ {secret:25s} MISSING")
            all_exist = False
    
    return all_exist

def check_compose_config():
    """Verify docker-compose.yml has proper security config"""
    print_section("Phase 4 & 5: Docker Compose Configuration")
    
    base_dir = Path(__file__).parent.parent  # Go up from scripts/ to root
    compose_file = base_dir / "docker" / "docker-compose.yml"
    
    if not compose_file.exists():
        print("  ❌ docker-compose.yml not found")
        return False
    
    content = compose_file.read_text()
    
    checks = {
        "Redis bound to loopback": "127.0.0.1:6379:6379" in content,
        "Postgres bound to loopback": "127.0.0.1:5432:5432" in content,
        "Secrets section defined": "secrets:" in content and "file: ./secrets/" in content,
        "Gateway has secrets": "api-gateway:" in content and "secrets:" in content.split("api-gateway:")[1].split("\n\n")[0],
        "Internal services no host ports": "# ports:" in content or "ports:" not in content.split("gemma-service:")[1].split("depends_on:")[0]
    }
    
    all_pass = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
        if not passed:
            all_pass = False
    
    return all_pass

def check_jwt_enforcement():
    """Verify JWT enforcement in service code"""
    print_section("Phase 3: JWT Enforcement Verification")
    
    base_dir = Path(__file__).parent.parent  # Go up from scripts/ to root
    services_dir = base_dir / "services"
    
    services = ["rag-service", "transcription-service", "gemma-service", "queue-service", "emotion-service"]
    
    all_enforced = True
    for service in services:
        main_py = services_dir / service / "src" / "main.py"
        if main_py.exists():
            content = main_py.read_text()
            has_middleware = "class ServiceAuthMiddleware" in content
            has_jwt_only = 'JWT_ONLY = os.getenv("JWT_ONLY"' in content
            has_replay = "get_replay_protector" in content
            has_aud_check = "expected_aud=" in content
            
            status = "✅" if all([has_middleware, has_jwt_only, has_replay, has_aud_check]) else "⚠️"
            print(f"  {status} {service:25s} middleware={has_middleware} jwt_only={has_jwt_only} replay={has_replay} aud={has_aud_check}")
            
            if not all([has_middleware, has_jwt_only, has_replay, has_aud_check]):
                all_enforced = False
        else:
            print(f"  ❌ {service:25s} main.py not found")
            all_enforced = False
    
    return all_enforced

def check_gateway_security():
    """Verify Gateway security features"""
    print_section("Phase 1 & 2: Gateway Security Features")
    
    base_dir = Path(__file__).parent.parent  # Go up from scripts/ to root
    gateway_main = base_dir / "services" / "api-gateway" / "src" / "main.py"
    
    if not gateway_main.exists():
        print("  ❌ Gateway main.py not found")
        return False
    
    content = gateway_main.read_text()
    
    checks = {
        "CORS middleware": "CORSMiddleware" in content,
        "CSRF middleware": "class CSRFMiddleware" in content,
        "Rate limiting": "class RateLimitMiddleware" in content,
        "JWT emission": "service_auth.create_token" in content,
        "Session cookies": "SESSION_COOKIE_SECURE" in content,
        "Comprehensive proxy logging": "[PROXY" in content and "request_id" in content,
    }
    
    all_pass = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
        if not passed:
            all_pass = False
    
    return all_pass

def check_logging():
    """Verify comprehensive logging implementation"""
    print_section("Comprehensive Logging Verification")
    
    base_dir = Path(__file__).parent.parent  # Go up from scripts/ to root
    
    files_to_check = [
        ("shared/security/service_auth.py", ["🔐 JWT CREATE", "✅ JWT VERIFIED", "🔴 JWT VERIFY FAILED"]),
        ("services/api-gateway/src/main.py", ["🔄 [PROXY", "✅ [PROXY", "❌ [PROXY"]),
        ("shared/security/secrets.py", ["🔍 SECRET GET", "✅ SECRET GET", "❌ SECRET GET"])
    ]
    
    all_pass = True
    for file_path, markers in files_to_check:
        full_path = base_dir / file_path
        if full_path.exists():
            content = full_path.read_text()
            missing = [m for m in markers if m not in content]
            if missing:
                print(f"  ⚠️  {file_path:45s} missing: {missing}")
                all_pass = False
            else:
                print(f"  ✅ {file_path:45s} all logging markers present")
        else:
            print(f"  ❌ {file_path:45s} FILE NOT FOUND")
            all_pass = False
    
    return all_pass

def main():
    """Run all verification checks"""
    print("\n" + "="*80)
    print("  🔒 SECURITY IMPLEMENTATION VERIFICATION")
    print("  Checking Phases 1-5 Implementation")
    print("="*80)
    
    results = {
        "Docker Secrets (Phase 5)": check_secrets(),
        "Compose Configuration (Phase 4 & 5)": check_compose_config(),
        "JWT Enforcement (Phase 3)": check_jwt_enforcement(),
        "Gateway Security (Phase 1 & 2)": check_gateway_security(),
        "Comprehensive Logging": check_logging()
    }
    
    print_section("VERIFICATION SUMMARY")
    
    all_passed = True
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status:10s} {check}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("  ✅ ALL SECURITY CHECKS PASSED!")
        print("     System is ready for testing.")
        return 0
    else:
        print("  ⚠️  SOME CHECKS FAILED")
        print("     Review the failures above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
