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
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, Header, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

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
    
    def __init__(self, service_id: str, service_secret: str):
        """
        Initialize service auth
        
        Args:
            service_id: Unique service identifier
            service_secret: Service secret key (from Docker secrets)
        """
        self.service_id = service_id
        self.service_secret = service_secret.encode('utf-8')
        
        logger.info(f"Service auth initialized for: {service_id}")
    
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
        
        logger.debug(f"🔐 JWT CREATE: service={self.service_id} aud={aud} jti={request_id[:12]}... expires_in={expires_in}s")
        
        # Encode payload
        payload_json = json.dumps(payload, separators=(',', ':'))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        
        # Create signature
        signature = hmac.new(
            self.service_secret,
            payload_b64.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        
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
            
            # Verify signature
            expected_signature = hmac.new(
                self.service_secret,
                payload_b64.encode(),
                hashlib.sha256
            ).digest()
            expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode().rstrip('=')
            
            if not hmac.compare_digest(signature_b64, expected_signature_b64):
                logger.error("🔴 JWT VERIFY FAILED: Signature mismatch")
                raise ValueError("Invalid signature")
            
            logger.debug("✅ JWT signature valid")
            
            # Decode payload
            # Add padding if needed
            padding = len(payload_b64) % 4
            if padding:
                payload_b64 += '=' * (4 - padding)
            
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload = json.loads(payload_json)
            
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
        service_secret: str,
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
        self.service_secret = service_secret.encode('utf-8')
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
            # Create temporary auth instance for verification
            temp_auth = ServiceAuth("", self.service_secret.decode())
            payload = temp_auth.verify_token(token)
            
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


def get_service_auth(service_id: str, service_secret: str) -> ServiceAuth:
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







