"""
Service-to-Service Authentication with JWT
Provides secure inter-service communication
"""

import time
import os
import uuid
import hmac
import hashlib
import json
import base64
import logging
import secrets
from typing import Optional, Dict, Any, Tuple, List, Sequence
from fastapi import HTTPException, Header, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _is_test_mode() -> bool:
    return os.getenv("TEST_MODE", "false").strip().lower() in {"1", "true", "yes"}


def _add_base64_padding(value: str) -> str:
    return value + ("=" * (-len(value) % 4))


def _normalize_secret_value(raw: str, allow_short: bool = False) -> bytes:
    candidate = (raw or "").strip()
    if not candidate:
        raise ValueError("JWT secret is empty")
    # Try base64/urlsafe base64 first
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(_add_base64_padding(candidate))
            if decoded and (len(decoded) >= 32 or allow_short):
                return decoded
        except Exception:
            continue
    # Fallback to UTF-8 bytes
    data = candidate.encode("utf-8")
    if len(data) < 32 and not allow_short:
        raise ValueError("JWT secret must be at least 32 bytes")
    return data


def _looks_like_default_secret(raw: str) -> bool:
    return raw.strip() == "dev_jwt_secret"


def load_service_jwt_keys(service_name: str) -> List[Tuple[str, bytes]]:
    """
    Load primary/previous JWT secrets for the given service.

    Returns:
        List of (kid, key_bytes) tuples, primary first.
    """
    from shared.security.secrets import get_secret

    test_mode = _is_test_mode()
    raw_entries: List[Tuple[str, str]] = []
    for kid, secret_name in (("k1", "jwt_secret_primary"), ("k0", "jwt_secret_previous")):
        value = get_secret(secret_name)
        if value:
            raw_entries.append((kid, value))
    if not raw_entries:
        fallback = get_secret("jwt_secret")
        if fallback:
            raw_entries.append(("legacy", fallback))

    keys: List[Tuple[str, bytes]] = []
    for idx, (kid, value) in enumerate(raw_entries):
        try:
            key_bytes = _normalize_secret_value(value, allow_short=test_mode)
        except ValueError as exc:
            raise RuntimeError(f"Invalid JWT secret '{kid}' for {service_name}: {exc}") from exc
        kid_label = kid or f"k{idx+1}"
        keys.append((kid_label, key_bytes))

    if not keys:
        if test_mode:
            temp = secrets.token_bytes(32)
            keys.append(("ephemeral", temp))
            logger.warning(
                "[SERVICE-AUTH] %s starting without jwt_secret; generated ephemeral test key",
                service_name,
            )
        else:
            raise RuntimeError(f"[SERVICE-AUTH] {service_name} missing jwt_secret and TEST_MODE disabled")

    if not test_mode:
        for kid, raw_value in raw_entries:
            if _looks_like_default_secret(raw_value):
                raise RuntimeError(
                    f"[SERVICE-AUTH] {service_name} configured with insecure default jwt_secret; "
                    "provide a strong secret via docker secrets or env"
                )

    logger.info(
        "[SERVICE-AUTH] Loaded %s JWT key(s) for %s",
        len(keys),
        service_name,
    )
    return keys

# Optional Redis import (fallback to in-memory if unavailable)
try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - import fallback
    redis = None


class _InMemoryReplayStore:
    """Process-local replay cache fallback with TTL support."""
    def __init__(self):
        self._store: Dict[str, int] = {}

    def add_if_absent(self, key: str, ttl_seconds: int) -> bool:
        now = int(time.time())
        # Cleanup expired entries lazily
        expired = [k for k, exp in self._store.items() if exp <= now]
        for k in expired:
            self._store.pop(k, None)
        if key in self._store:
            return False
        self._store[key] = now + ttl_seconds
        return True


class ReplayProtector:
    """Replay protection using Redis with in-memory fallback.

    Usage:
      ok, reason = protector.check_and_store(request_id, ttl)
      if not ok: raise ValueError(reason)
    """
    def __init__(self, url: Optional[str] = None):
        url = url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._client = None
        if redis is not None:
            try:
                self._client = redis.Redis.from_url(url, decode_responses=True)
                # Simple ping to verify connectivity
                self._client.ping()
                logger.info("ReplayProtector: using Redis backend (%s)", url)
            except Exception as e:
                logger.warning("ReplayProtector: Redis unavailable (%s), falling back to in-memory: %s", url, e)
                self._client = None
        else:
            logger.warning("ReplayProtector: redis package not installed, using in-memory fallback")
        self._fallback = _InMemoryReplayStore()

    def check_and_store(self, request_id: str, ttl_seconds: int) -> Tuple[bool, str]:
        if not request_id:
            return False, "missing request_id"
        key = f"s2s:rid:{request_id}"
        try:
            if self._client is not None:
                # SETNX + EXPIRE in one go via set(name, value, nx=True, ex=ttl)
                created = self._client.set(key, "1", nx=True, ex=ttl_seconds)
                if not created:
                    return False, "replay detected"
                return True, "ok"
        except Exception as e:
            logger.warning("ReplayProtector: Redis error, using fallback: %s", e)
            self._client = None
        # Fallback path
        added = self._fallback.add_if_absent(key, ttl_seconds)
        if not added:
            return False, "replay detected (fallback)"
        return True, "ok"


class ServiceAuth:
    """
    JWT-based service authentication
    
    Each service has a unique service ID and secret
    JWTs are signed with HMAC-SHA256
    """
    
    def __init__(self, service_id: str, service_secret):
        """
        Initialize service auth
        
        Args:
            service_id: Unique service identifier
            service_secret: Service secret material (string/bytes or list of (kid, key))
        """
        self.service_id = service_id
        self._keys = self._normalize_keys(service_secret)
        self._primary = self._keys[0]
        logger.info(f"Service auth initialized for: {service_id}")

    @staticmethod
    def _normalize_keys(service_secret) -> List[Tuple[str, bytes]]:
        def ensure_bytes(value) -> bytes:
            if isinstance(value, bytes):
                return value
            if isinstance(value, str):
                return value.encode("utf-8")
            raise TypeError("JWT key must be bytes or str")

        if isinstance(service_secret, Sequence) and not isinstance(service_secret, (str, bytes, bytearray)):
            normalized: List[Tuple[str, bytes]] = []
            for idx, entry in enumerate(service_secret):
                if isinstance(entry, tuple):
                    kid, key = entry
                elif isinstance(entry, dict):
                    kid = entry.get("kid")
                    key = entry.get("key")
                else:
                    raise TypeError("JWT key entries must be tuple or dict")
                if key is None:
                    raise TypeError("JWT key entry missing 'key'")
                key_bytes = ensure_bytes(key)
                kid_label = (kid or f"k{idx+1}")
                normalized.append((kid_label, key_bytes))
            if not normalized:
                raise ValueError("No JWT keys provided")
            return normalized

        # Backward compatibility: single secret string
        key_bytes = ensure_bytes(service_secret)
        return [("legacy", key_bytes)]

    @staticmethod
    def _sign(payload_b64: str, key: bytes) -> str:
        signature = hmac.new(
            key,
            payload_b64.encode(),
            hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    def create_token(self, expires_in: int = 300, aud: str = "internal") -> str:
        """
        Create JWT token for outgoing requests
        
        Args:
            expires_in: Token expiry in seconds (default: 5 minutes)
            aud: Token audience (default: "internal")
            
        Returns:
            JWT token
        """
        now = int(time.time())
        
        # Generate unique request_id (used as jti for replay protection)
        request_id = str(uuid.uuid4())
        
        # Create payload
        payload = {
            "service_id": self.service_id,
            "request_id": request_id,
            "jti": request_id,  # JWT ID for replay protection
            "issued_at": now,
            "expires_at": now + expires_in,
            "aud": aud,
        }
        if self._primary[0]:
            payload["kid"] = self._primary[0]
        
        logger.debug(f"🔐 JWT CREATE: service={self.service_id} aud={aud} jti={request_id[:12]}... expires_in={expires_in}s")
        
        # Encode payload
        payload_json = json.dumps(payload, separators=(',', ':'))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        
        # Create signature
        signature_b64 = self._sign(payload_b64, self._primary[1])
        
        # Combine into JWT
        token = f"{payload_b64}.{signature_b64}"
        
        logger.debug(f"✅ JWT CREATED: service={self.service_id} jti={request_id[:12]}... token_len={len(token)}")
        
        return token
    
    def verify_token(self, token: str, allowed_services: Optional[list] = None, expected_aud: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify JWT token from incoming request
        
        Args:
            token: JWT token to verify
            allowed_services: Optional list of allowed service IDs
            expected_aud: Expected audience value (e.g., "internal")
            
        Returns:
            Token payload if valid
            
        Raises:
            ValueError: If token is invalid
        """
        if not token:
            logger.error("🔴 JWT VERIFY FAILED: Token is empty")
            raise ValueError("Token is empty")
        
        try:
            logger.debug(f"🔍 JWT VERIFY START: token_len={len(token)} expected_aud={expected_aud} allowed_services={allowed_services}")
            
            # Split token
            parts = token.split('.')
            if len(parts) != 2:
                logger.error(f"🔴 JWT VERIFY FAILED: Invalid format, expected 2 parts got {len(parts)}")
                raise ValueError("Invalid token format")
            
            payload_b64, signature_b64 = parts
            
            # Decode payload (needed to inspect kid for key selection)
            payload_b64_original = payload_b64
            padding = len(payload_b64) % 4
            if padding:
                payload_b64 += '=' * (4 - padding)
            
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload = json.loads(payload_json)
            kid = payload.get("kid")

            # Verify signature across candidate keys
            candidate_keys = self._keys
            if kid:
                matches = [entry for entry in self._keys if entry[0] == kid]
                if matches:
                    candidate_keys = matches

            matched_key = None
            for candidate in candidate_keys:
                expected_signature_b64 = self._sign(payload_b64_original, candidate[1])
                if hmac.compare_digest(signature_b64, expected_signature_b64):
                    matched_key = candidate
                    break

            if not matched_key:
                logger.error("🔴 JWT VERIFY FAILED: Signature mismatch")
                raise ValueError("Invalid signature")

            logger.debug("✅ JWT signature valid (kid=%s)", kid or matched_key[0])
            
            jti_short = str(payload.get('request_id', payload.get('jti', '')))[:12]
            logger.debug(f"✅ JWT payload decoded: service={payload.get('service_id')} jti={jti_short}... aud={payload.get('aud')}")
            
            # Verify expiry
            now = int(time.time())
            expires_at = payload.get('expires_at', 0)
            if expires_at < now:
                logger.error(f"🔴 JWT VERIFY FAILED: Token expired (expired_at={expires_at} now={now} diff={now-expires_at}s ago)")
                raise ValueError("Token expired")
            
            logger.debug(f"✅ JWT not expired (expires in {expires_at - now}s)")
            
            # Verify allowed services
            caller_service = payload.get('service_id')
            if allowed_services and caller_service not in allowed_services:
                logger.error(f"🔴 JWT VERIFY FAILED: Service '{caller_service}' not in allowed list {allowed_services}")
                raise ValueError(f"Service {caller_service} not allowed")
            
            if allowed_services:
                logger.debug(f"✅ JWT service '{caller_service}' is allowed")

            # Verify audience
            if expected_aud is not None:
                aud = payload.get('aud')
                if aud != expected_aud:
                    logger.error(f"🔴 JWT VERIFY FAILED: Audience mismatch, expected '{expected_aud}' got '{aud}'")
                    raise ValueError(f"Invalid audience: {aud}")
                logger.debug(f"✅ JWT audience '{aud}' matches expected")
            
            logger.info(f"✅ JWT VERIFIED: service={caller_service} jti={jti_short}... aud={payload.get('aud')}")
            
            return payload
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"🔴 JWT VERIFY FAILED: Unexpected error: {e}")
            raise ValueError(f"Token verification failed: {e}")
    
    def get_auth_header(self) -> Dict[str, str]:
        """
        Get authorization header for outgoing requests
        
        Returns:
            Dict with X-Service-Token header
        """
        token = self.create_token()
        return {"X-Service-Token": token}


# Singleton-style helper for replay protection
_replay_protector: Optional[ReplayProtector] = None


def get_replay_protector() -> ReplayProtector:
    global _replay_protector
    if _replay_protector is None:
        _replay_protector = ReplayProtector()
    return _replay_protector



class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for service authentication
    
    Verifies JWT tokens on incoming requests
    """
    
    def __init__(
        self,
        app,
        service_secret,
        exempt_paths: list = None,
        enabled: bool = True
    ):
        """
        Initialize middleware
        
        Args:
            app: FastAPI app
            service_secret: Service secret for verification
            exempt_paths: Paths that don't require auth (e.g., /health)
            enabled: Whether auth is enabled (disable for TEST_MODE)
        """
        super().__init__(app)
        self._verifier = ServiceAuth("__middleware__", service_secret)
        self.exempt_paths = exempt_paths or ["/health", "/docs", "/openapi.json"]
        self.enabled = enabled
        
        if not enabled:
            logger.warning("Service authentication DISABLED (TEST_MODE)")
        else:
            logger.info(f"Service authentication enabled (exempt: {self.exempt_paths})")
    
    async def dispatch(self, request: Request, call_next):
        """Process request"""
        
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)
        
        # Skip exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        
        # Get token from header
        token = request.headers.get("X-Service-Token")
        
        if not token:
            logger.warning(f"Missing service token: {request.url.path}")
            return JSONResponse(
                {"error": "Missing service token"},
                status_code=401
            )
        
        # Verify token
        try:
            payload = self._verifier.verify_token(token)
            
            # Store service_id in request state
            request.state.service_id = payload['service_id']
            request.state.request_id = payload['request_id']
            
            return await call_next(request)
            
        except ValueError as e:
            logger.warning(f"Invalid service token: {e}")
            return JSONResponse(
                {"error": f"Invalid service token: {e}"},
                status_code=401
            )


# Service instances cache
_service_auths: Dict[str, ServiceAuth] = {}


def get_service_auth(service_id: str, service_secret) -> ServiceAuth:
    """
    Get or create service auth instance
    
    Args:
        service_id: Service identifier
        service_secret: Service secret
        
    Returns:
        ServiceAuth instance
    """
    if service_id not in _service_auths:
        _service_auths[service_id] = ServiceAuth(service_id, service_secret)
    return _service_auths[service_id]

