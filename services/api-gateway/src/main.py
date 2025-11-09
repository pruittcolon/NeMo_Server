"""
API Gateway Service
Handles authentication, routing, and frontend serving
"""
import base64
import os
import re
import secrets
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
import logging
import hashlib
import uuid
from datetime import datetime, timedelta
from threading import Lock
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response, Depends, Cookie, Header, File, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from starlette.responses import StreamingResponse as StarletteStreamingResponse
import time
import asyncio
from pydantic import BaseModel
import httpx

# Add parent directories to path
# Add root directory to path to access shared modules
# __file__ is /app/src/main.py, so parent.parent gives us /app
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import auth modules
try:
    from auth.auth_manager import AuthManager
    from auth.permissions import require_auth, Session
    print("[GATEWAY] Auth modules loaded")
except ImportError as e:
    print(f"[GATEWAY] WARNING: Auth import failed: {e}")
    AuthManager = None
    require_auth = None
    Session = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

from src.config import SecurityConfig as SecConf

# Configuration
GEMMA_URL = os.getenv("GEMMA_URL", "http://gemma-service:8001")
RAG_URL = os.getenv("RAG_URL", "http://rag-service:8004")
EMOTION_URL = os.getenv("EMOTION_URL", "http://emotion-service:8005")
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_URL", "http://transcription-service:8003")
INSIGHTS_URL = os.getenv("INSIGHTS_URL", "http://insights-service:8010")
# Security & CORS
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1,http://localhost").split(",") if o.strip()]
# Centralized cookie and CSRF names to prevent drift
SESSION_COOKIE_NAME = SecConf.SESSION_COOKIE_NAME
CSRF_COOKIE_NAME = SecConf.CSRF_COOKIE_NAME
CSRF_HEADER_NAME = SecConf.CSRF_HEADER_NAME
SESSION_COOKIE_SECURE = SecConf.SESSION_COOKIE_SECURE
SESSION_COOKIE_SAMESITE = getattr(SecConf, "SESSION_COOKIE_SAMESITE", "lax")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# Speaker identifier validation pattern (lowercase alphanumerics, hyphen, underscore)
SPEAKER_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
# Frontend is at /app/frontend in container
FRONTEND_DIR = Path("/app/frontend") if Path("/app/frontend").exists() else Path(__file__).parent.parent.parent.parent.parent / "frontend"
CANONICAL_HOST = os.getenv("CANONICAL_HOST", "localhost").strip()
CANONICAL_PORT = os.getenv("CANONICAL_PORT", "").strip()
ANALYSIS_FALLBACK_FILE = Path(os.getenv("ANALYSIS_FALLBACK_FILE", "/app/instance/analysis_fallback.json"))
_analysis_fallback_lock = Lock()

# Global auth manager and service auth
auth_manager = None
service_auth = None
# Login rate limiting parameters (tunable via env)
_LOGIN_WINDOW = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW", "60"))
_LOGIN_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT_LIMIT", "5"))
login_attempts: Dict[str, Dict[str, Any]] = {"window": _LOGIN_WINDOW, "limit": _LOGIN_LIMIT, "ips": {}}
personality_jobs: Dict[str, Dict[str, Any]] = {}
analysis_jobs: Dict[str, Dict[str, Any]] = {}


def _load_fallback_artifacts() -> List[Dict[str, Any]]:
    with _analysis_fallback_lock:
        if not ANALYSIS_FALLBACK_FILE.exists():
            return []
        try:
            return json.loads(ANALYSIS_FALLBACK_FILE.read_text())
        except Exception as exc:
            logger.warning("[ANALYSIS-FALLBACK] Failed to read %s: %s", ANALYSIS_FALLBACK_FILE, exc)
            return []


def _save_fallback_artifacts(items: List[Dict[str, Any]]) -> None:
    with _analysis_fallback_lock:
        ANALYSIS_FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANALYSIS_FALLBACK_FILE.write_text(json.dumps(items, indent=2))


def _persist_fallback_artifact(payload: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    artifact_id = payload.get("artifact_id") or f"fallback_{uuid.uuid4().hex}"
    metadata = dict(payload.get("metadata") or {})
    if session and metadata.get("user_id") is None:
        metadata["user_id"] = getattr(session, "user_id", None)
    artifact = {
        "artifact_id": artifact_id,
        "analysis_id": payload.get("analysis_id"),
        "title": payload.get("title") or "Analyzer Run",
        "body": payload.get("body", ""),
        "metadata": metadata,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    items = _load_fallback_artifacts()
    items = [item for item in items if item.get("artifact_id") != artifact_id]
    items.insert(0, artifact)
    _save_fallback_artifacts(items)
    return artifact


def _list_fallback_artifacts(limit: int, offset: int) -> Dict[str, Any]:
    items = _load_fallback_artifacts()
    subset = items[offset: offset + limit]
    return {
        "success": True,
        "items": subset,
        "count": len(subset),
        "total": len(items),
        "has_more": offset + limit < len(items),
        "source": "gateway_fallback",
    }


def _get_fallback_artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    items = _load_fallback_artifacts()
    for item in items:
        if item.get("artifact_id") == artifact_id:
            return item
    return None


def _decode_session_key(raw_value: Optional[str]) -> Optional[bytes]:
    """Decode a base64/urlsafe base64 encoded 32-byte key."""
    if not raw_value:
        return None
    raw_value = raw_value.strip()
    if not raw_value:
        return None
    padded = raw_value + "=" * (-len(raw_value) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(padded.encode("utf-8"))
            if len(decoded) == 32:
                return decoded
        except Exception:
            continue
    logger.error("Failed to decode session key; expected 32-byte base64 string")
    return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global auth_manager
    logger.info("Starting API Gateway...")
    
    session_key_bytes: Optional[bytes] = None
    secrets_source: Optional[str] = None

    if AuthManager:
        from shared.security.secrets import get_secret
        logger.info("🔍 Attempting to load session_key from secrets...")
        raw_secret = get_secret("session_key")
        logger.info(f"🔍 get_secret('session_key') returned: {raw_secret is not None} (length: {len(raw_secret) if raw_secret else 0})")
        session_key_bytes = _decode_session_key(raw_secret)
        logger.info(f"🔍 _decode_session_key returned: {session_key_bytes is not None} (length: {len(session_key_bytes) if session_key_bytes else 0})")
        if session_key_bytes:
            secrets_source = "docker"  # /run/secrets/session_key
        else:
            env_secret = os.getenv("SESSION_KEY_B64") or os.getenv("SESSION_KEY")
            session_key_bytes = _decode_session_key(env_secret)
            if session_key_bytes:
                secrets_source = "environment"

        if not session_key_bytes:
            logger.warning("Session key not found; generating ephemeral key (sessions reset on restart)")
            session_key_bytes = secrets.token_bytes(32)
            secrets_source = "ephemeral"
        else:
            logger.info("✅ Loaded session encryption key from %s", secrets_source)

        users_db_key = get_secret("users_db_key")
        if users_db_key:
            logger.info("Loaded users DB encryption key from secrets")
        else:
            logger.warning("Users DB encryption key not found; storing credentials database without encryption")

        # Import init_auth_manager to properly initialize the global singleton
        from auth.auth_manager import init_auth_manager
        auth_manager = init_auth_manager(
            secret_key=session_key_bytes,
            db_path="/app/instance/users.db",
            db_encryption_key=users_db_key,
        )
        logger.info("Auth manager initialized with global singleton")
    
    # Initialize service auth for inter-service JWTs
    logger.info("🔍 DEBUG: About to initialize JWT service auth")
    try:
        from shared.security.secrets import get_secret
        from shared.security.service_auth import get_service_auth
        jwt_secret = get_secret("jwt_secret", default="dev_jwt_secret")
        if jwt_secret:
            # service_id for gateway
            global service_auth
            service_auth = get_service_auth(service_id="gateway", service_secret=jwt_secret)
            logger.info("✅ JWT service auth initialized for gateway")
        else:
            logger.warning("jwt_secret not found; X-Service-Token will not be sent")
    except Exception as e:
        import traceback
        logger.error(f"⚠️ Failed to initialize ServiceAuth: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    yield
    
    logger.info("API Gateway shutdown complete")

app = FastAPI(title="API Gateway", version="1.0.0", lifespan=lifespan)


# Custom StaticFiles with no-cache headers to prevent VPN/browser caching issues
class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that adds Cache-Control headers to prevent caching issues"""
    
    async def get_response(self, path: str, scope) -> StarletteResponse:
        response = await super().get_response(path, scope)
        
        # Add no-cache headers for HTML, JS, and CSS files
        if path.endswith(('.html', '.js', '.css')):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        # Allow longer caching for assets like images, fonts
        else:
            response.headers['Cache-Control'] = 'public, max-age=3600'
        
        return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Rate limiting controls (can be disabled for dev/local)
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes"}
RATE_LIMIT_SKIP_PREFIXES = tuple(filter(None, os.getenv("RATE_LIMIT_SKIP_PREFIXES", "/ui/,/ui,/assets/,/static/,/docs/").split(",")))
RATE_LIMIT_SKIP_PATHS = set(filter(None, os.getenv("RATE_LIMIT_SKIP_PATHS", "/health,/").split(",")))

# Simple in-memory rate limiting middleware (fixed window)
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.default_window = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
        self.default_limit = int(os.getenv("RATE_LIMIT_DEFAULT", "120"))
        self.auth_limit = int(os.getenv("RATE_LIMIT_AUTH", "20"))
        # buckets: key -> {"count": int, "window_start": int}
        self.buckets: Dict[str, Dict[str, int]] = {}

    def _key(self, request: Request, scope: str) -> str:
        client_ip = request.client.host if request.client else "unknown"
        return f"{client_ip}:{scope}"

    async def dispatch(self, request: Request, call_next):
        if not RATE_LIMIT_ENABLED:
            return await call_next(request)
        # Determine scope and limit
        path = request.url.path or "/"

        # Skip static resources and health endpoints
        if path in RATE_LIMIT_SKIP_PATHS or any(path.startswith(prefix) for prefix in RATE_LIMIT_SKIP_PREFIXES):
            return await call_next(request)

        window = self.default_window
        limit = self.default_limit
        scope = "global"
        if path.startswith("/api/auth/login"):
            scope = "auth"
            limit = self.auth_limit

        now = int(time.time())
        key = self._key(request, scope)
        bucket = self.buckets.get(key, {"count": 0, "window_start": now})
        # Reset window if expired
        if now - bucket["window_start"] >= window:
            bucket = {"count": 0, "window_start": now}
        # Increment and check
        bucket["count"] += 1
        self.buckets[key] = bucket
        if bucket["count"] > limit:
            retry_after = window - (now - bucket["window_start"]) or 1
            logger.warning(f"Rate limit exceeded for {key}: {bucket['count']}/{limit}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "limit": limit,
                    "window_sec": window,
                    "retry_after_sec": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

# Enable rate limiting unless disabled
if RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)
else:
    logger.info("Rate limiting middleware disabled via RATE_LIMIT_ENABLED")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach common security headers to every response."""

    def __init__(self, app):
        super().__init__(app)
        force_hsts = os.getenv("FORCE_HSTS", "false").lower() in {"1", "true", "yes"}
        self.include_hsts = SESSION_COOKIE_SECURE or force_hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'"
        )
        if self.include_hsts:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CSRF enforcement middleware (double-submit cookie)
class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.exempt_paths = {"/health", "/api/auth/login", "/api/auth/logout", "/docs", "/openapi.json"}
        # Paths that allow Bearer token auth (mobile clients) without CSRF
        self.bearer_auth_paths = {"/transcribe"}
        self.logger = logging.getLogger(__name__)
        print("[CSRF MIDDLEWARE] ✅ CSRFMiddleware initialized!", flush=True)

    async def dispatch(self, request: Request, call_next):
        # Respect global CSRF toggle (e.g., TEST_MODE or local dev). When disabled,
        # forward the request untouched so local development isn't blocked.
        try:
            from src.config import SecurityConfig as SecConf
            if not SecConf.ENABLE_CSRF:
                return await call_next(request)
        except Exception:
            # If config import fails, keep middleware active by default
            pass
        try:
            # Skip all checks for exempt paths (like login, health, etc.)
            if request.url.path in self.exempt_paths:
                return await call_next(request)
            
            if request.method in {"POST", "PUT", "DELETE"}:
                print(f"[CSRF MIDDLEWARE] Processing {request.method} {request.url.path}", flush=True)
                # Validate session
                ws_session = request.cookies.get(SESSION_COOKIE_NAME)
                
                # Check for Bearer token (mobile clients like Flutter)
                if not ws_session:
                    auth_header = request.headers.get("Authorization", "")
                    print(f"[CSRF MIDDLEWARE] No cookie, checking auth header: {auth_header[:40] if auth_header else 'EMPTY'}", flush=True)
                    if auth_header.startswith("Bearer "):
                        ws_session = auth_header[7:]  # Remove "Bearer " prefix
                        print(f"[CSRF MIDDLEWARE] ✅ Found Bearer token: {ws_session[:20]}...", flush=True)
                
                if not auth_manager or not ws_session:
                    print(f"[CSRF MIDDLEWARE] ❌ NOT AUTHENTICATED: auth_manager={bool(auth_manager)}, ws_session={bool(ws_session)}", flush=True)
                    return Response(content='{"detail":"Not authenticated"}', media_type="application/json", status_code=401)
                session = auth_manager.validate_session(ws_session)
                if not session:
                    print(f"[CSRF MIDDLEWARE] ❌ Session validation failed", flush=True)
                    return Response(content='{"detail":"Invalid session"}', media_type="application/json", status_code=401)
                
                # Store session in request.state for later use by require_auth
                request.state.session = session
                
                # Skip CSRF check for Bearer auth paths (mobile clients don't have CSRF tokens)
                if request.url.path in self.bearer_auth_paths:
                    print(f"[CSRF MIDDLEWARE] ✅ Bearer auth path, allowing through", flush=True)
                    return await call_next(request)
                
                # Double-submit CSRF check for web clients
                header_token = request.headers.get(CSRF_HEADER_NAME)
                cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
                if not header_token or not cookie_token or header_token != cookie_token or header_token != session.csrf_token:
                    # Log token fingerprints (first 8 chars) to aid debugging without leaking secrets
                    ht = (header_token or "")[:8]
                    ct = (cookie_token or "")[:8]
                    st = (session.csrf_token or "")[:8]
                    self.logger.warning(
                        "[CSRF] invalid token path=%s header=%s cookie=%s session=%s",
                        request.url.path,
                        ht,
                        ct,
                        st,
                    )
                    return Response(content='{"detail":"CSRF token invalid"}', media_type="application/json", status_code=403)
        except Exception as e:
            print(f"[CSRF MIDDLEWARE] EXCEPTION: {e}", flush=True)
            import traceback
            traceback.print_exc()
        return await call_next(request)

app.add_middleware(CSRFMiddleware)


class CanonicalHostMiddleware(BaseHTTPMiddleware):
    """Redirect frontend traffic to a single canonical host."""

    def __init__(self, app):
        super().__init__(app)
        self.canonical_host = CANONICAL_HOST
        self.canonical_port = CANONICAL_PORT
        self.enabled = bool(self.canonical_host)

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        try:
            if request.method not in {"GET", "HEAD"}:
                return await call_next(request)

            path = request.url.path
            if not (path == "/" or path.startswith("/ui")):
                return await call_next(request)

            host_header = request.headers.get("host")
            if not host_header:
                return await call_next(request)

            hostname, _, port = host_header.partition(":")
            request_port = port or (str(request.url.port) if request.url.port else "")
            request_port = request_port if request_port not in {"80", "443"} else ""

            target_port = self.canonical_port or request_port
            target_port = target_port if target_port and target_port not in {"80", "443"} else ""

            if hostname == self.canonical_host and (not target_port or target_port == request_port):
                return await call_next(request)

            netloc = self.canonical_host
            if target_port:
                netloc = f"{self.canonical_host}:{target_port}"

            redirect_url = request.url.replace(netloc=netloc)
            return RedirectResponse(str(redirect_url), status_code=307)
        except Exception as exc:
            logger.warning(f"[CANONICAL] Redirect handling failed: {exc}")
            return await call_next(request)


app.add_middleware(CanonicalHostMiddleware)

# ============================================================================
# Authentication Models
# ============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str

# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "healthy", "service": "api-gateway"}

@app.get("/api/health")
def api_health() -> Dict[str, Any]:
    """Alias for legacy frontend that prefixes requests with /api."""
    return health()

# ============================================================================
# Authentication Endpoints
# ============================================================================

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response, raw_request: Request):
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Auth not available")
    # Rate limiting (simple per-IP window)
    try:
        ip = _client_ip(raw_request)
        now = time.time()
        window = login_attempts["window"]
        lim = login_attempts["limit"]
        ip_state = login_attempts["ips"].get(ip, {"count": 0, "start": now})
        if now - ip_state["start"] > window:
            ip_state = {"count": 0, "start": now}
        ip_state["count"] += 1
        login_attempts["ips"][ip] = ip_state
        if ip_state["count"] > lim:
            raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")
    except HTTPException:
        raise
    except Exception:
        pass
    
    # authenticate returns session_token directly
    session_token = auth_manager.authenticate(request.username, request.password)
    if not session_token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Get user info from session
    session = auth_manager.validate_session(session_token)
    if not session:
        raise HTTPException(status_code=500, detail="Session creation failed")
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=86400,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE
    )
    # CSRF cookie (readable)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=session.csrf_token or "",
        httponly=False,
        max_age=86400,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE
    )
    
    return {
        "success": True,
        "session_token": session_token,
        "user": {
            "user_id": session.user_id,
            "role": session.role.value
        }
    }

@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    # Delete both session and CSRF cookies
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)
    return {"success": True}

@app.get("/api/auth/session")
async def check_session(request: Request):
    ws_session = request.cookies.get(SESSION_COOKIE_NAME)
    if not auth_manager or not ws_session:
        return {"valid": False}
    
    session = auth_manager.validate_session(ws_session)
    if not session:
        return {"valid": False}
    
    return {
        "valid": True,
        "user": {
            "user_id": session.user_id,
            "role": session.role.value
        }
    }

@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check if user is authenticated - used by frontend auth.js"""
    ws_session = request.cookies.get(SESSION_COOKIE_NAME)
    if not auth_manager or not ws_session:
        return {"valid": False}
    
    session = auth_manager.validate_session(ws_session)
    if not session:
        return {"valid": False}
    
    return {
        "valid": True,
        "user": {
            "user_id": session.user_id,
            "role": session.role.value
        }
    }

# ============================================================================
# Proxy Helper
# ============================================================================

async def proxy_request(
    url: str,
    method: str = "POST",
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
):
    """Proxy request to backend service with comprehensive logging (no payloads)"""
    start_ts = time.time()
    request_id = str(uuid.uuid4())[:12]
    
    logger.info(f"🔄 [PROXY {request_id}] START: {method} {url}")
    
    # Build headers with service authentication
    headers: Dict[str, str] = {}
    jwt_emitted = False
    jwt_short = ""
    
    # Add short‑TTL JWT header if available
    try:
        if service_auth:
            token = service_auth.create_token(expires_in=60, aud="internal")
            headers["X-Service-Token"] = token
            # Extract jti for logging (don't log full token)
            try:
                import base64, json as _json
                payload_b64 = token.split('.')[0]
                padding = len(payload_b64) % 4
                if padding:
                    payload_b64 += '=' * (4 - padding)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                jwt_short = payload.get('jti', payload.get('request_id', ''))[:12]
                jwt_emitted = True
                logger.debug(f"🔐 [PROXY {request_id}] JWT emitted: jti={jwt_short}... aud=internal ttl=60s")
            except:
                jwt_short = "unknown"
                jwt_emitted = True
    except Exception as e:
        logger.warning(f"⚠️ [PROXY {request_id}] JWT emission failed: {e}")
    
    if jwt_emitted:
        logger.info(f"🔐 [PROXY {request_id}] Auth: JWT (jti={jwt_short}...)")
    else:
        logger.error(f"❌ [PROXY {request_id}] JWT unavailable; aborting request to {url}")
        raise HTTPException(status_code=503, detail="Service authentication unavailable")
    
    if extra_headers:
        headers.update(extra_headers)

    def _extract_error_payload(response: httpx.Response) -> Dict[str, Any]:  # type: ignore[name-defined]
        safe_message: Any = None
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            safe_message = payload.get("detail") or payload
        elif isinstance(payload, list):
            safe_message = payload
        else:
            try:
                safe_message = response.text[:256]
            except Exception:
                safe_message = None
        if isinstance(safe_message, (dict, list)):
            try:
                safe_message = json.dumps(safe_message)  # type: ignore[arg-type]
            except Exception:
                safe_message = str(safe_message)
        if not safe_message:
            safe_message = response.reason_phrase or "Upstream service error"
        request_url = None
        try:
            request_url = str(response.request.url)  # type: ignore[attr-defined]
        except Exception:
            request_url = url
        return {
            "service": request_url,
            "status": response.status_code,
            "request_id": request_id,
            "message": safe_message,
        }

    try:
        logger.debug(f"📤 [PROXY {request_id}] Sending request to backend...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                if files:
                    logger.debug(f"📤 [PROXY {request_id}] Uploading files (no payload logged)")
                    response = await client.post(url, headers=headers, files=files, data=json or {})
                else:
                    logger.debug(f"📤 [PROXY {request_id}] Sending JSON (no payload logged)")
                    response = await client.post(url, headers=headers, json=json)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            duration_ms = int((time.time() - start_ts) * 1000)
            logger.info(f"📥 [PROXY {request_id}] Response: status={response.status_code} duration={duration_ms}ms")
            
            if response.status_code != 200:
                err_payload = _extract_error_payload(response)
                body_size = len(response.content or b"")
                logger.error(
                    "❌ [PROXY %s] Non-200 status=%s body_size=%s bytes detail=%s",
                    request_id,
                    response.status_code,
                    body_size,
                    err_payload.get("message"),
                )
            
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ [PROXY {request_id}] SUCCESS: {method} {url} in {duration_ms}ms")
            return data
            
    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_ts) * 1000)
        logger.error(f"⏱️ [PROXY {request_id}] TIMEOUT after {duration_ms}ms (limit 120s): {e}")
        raise HTTPException(status_code=504, detail=f"Service timeout: {url}")
    except httpx.HTTPStatusError as e:
        duration_ms = int((time.time() - start_ts) * 1000)
        err_payload = _extract_error_payload(e.response)
        body_size = len(e.response.content or b"")
        logger.error(
            "❌ [PROXY %s] HTTP ERROR: status=%s duration=%sms body_size=%s bytes detail=%s",
            request_id,
            e.response.status_code,
            duration_ms,
            body_size,
            err_payload.get("message"),
        )
        raise HTTPException(status_code=e.response.status_code, detail=err_payload)
    except Exception as e:
        duration_ms = int((time.time() - start_ts) * 1000)
        logger.error(f"💥 [PROXY {request_id}] EXCEPTION after {duration_ms}ms: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"💥 [PROXY {request_id}] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")


def format_sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

# ============================================================================
# Gemma Endpoints
# ============================================================================

@app.post("/api/gemma/warmup")
async def gemma_warmup(session: Session = Depends(require_auth)):
    """Warmup Gemma - moves model to GPU and waits until ready"""
    result = await proxy_request(f"{GEMMA_URL}/warmup", "POST", json={})
    return result

@app.post("/api/gemma/generate")
async def gemma_generate(request: Dict[str, Any], session: Session = Depends(require_auth)):
    result = await proxy_request(f"{GEMMA_URL}/generate", "POST", json=request)
    return result

@app.post("/api/gemma/chat")
async def gemma_chat(request: Dict[str, Any], session: Session = Depends(require_auth)):
    result = await proxy_request(f"{GEMMA_URL}/chat", "POST", json=request)
    return result

@app.get("/api/gemma/stats")
async def gemma_stats(session: Session = Depends(require_auth)):
    result = await proxy_request(f"{GEMMA_URL}/stats", "GET")
    return result

@app.post("/api/gemma/chat-rag")
async def gemma_chat_rag(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """RAG-enhanced chat via Gemma service"""
    result = await proxy_request(f"{GEMMA_URL}/chat/rag", "POST", json=request)
    return result

@app.post("/api/gemma/analyze")
async def gemma_analyze(request: Dict[str, Any], http_request: Request, session: Session = Depends(require_auth)):
    """Proxy legacy Gemma analyzer call (batch)."""
    analysis_id = http_request.headers.get("X-Analysis-Id") or f"analysis_{uuid.uuid4().hex[:10]}"
    headers = {"X-Analysis-Id": analysis_id} if analysis_id else None
    result = await proxy_request(
        f"{GEMMA_URL}/analyze",
        "POST",
        json=request,
        extra_headers=headers,
    )
    if isinstance(result, dict):
        result.setdefault("analysis_id", analysis_id)
    return result

@app.post("/api/gemma/analyze/stream")
async def gemma_analyze_stream_create(
    payload: Dict[str, Any],
    http_request: Request,
    session: Session = Depends(require_auth)
):
    """Create a streaming Gemma analysis job."""
    job_id = f"gemma-stream-{uuid.uuid4().hex[:10]}"
    analysis_id = payload.get("analysis_id") or http_request.headers.get("X-Analysis-Id")
    if not analysis_id:
        analysis_id = f"analysis_{uuid.uuid4().hex[:10]}"
    analysis_jobs[job_id] = {
        "payload": payload,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "analysis_id": analysis_id,
        "user_id": getattr(session, "user_id", None),
    }
    logger.info(
        "[ANALYZE-STREAM] Created job %s analysis_id=%s user=%s",
        job_id,
        analysis_id,
        getattr(session, "user_id", None),
    )
    return {"success": True, "job_id": job_id}


@app.get("/api/gemma/analyze/stream/{job_id}")
async def gemma_analyze_stream(job_id: str, http_request: Request, session: Session = Depends(require_auth)):
    """Stream analyzer progress via Server-Sent Events."""
    job = analysis_jobs.pop(job_id, None)
    if not job:
        logger.warning("[ANALYZE-STREAM] Unknown job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Analysis job not found or already started")

    payload = job.get("payload") or {}
    filters = payload.get("filters") or {}
    prompt_template = payload.get("custom_prompt") or ""
    max_tokens = int(payload.get("max_tokens", 512) or 512)
    temperature = float(payload.get("temperature", 0.4) or 0.4)
    analysis_id = http_request.query_params.get("analysis_id") or job.get("analysis_id")
    analysis_headers = {"X-Analysis-Id": analysis_id} if analysis_id else None

    def _normalize_filter_list(value: Optional[Any]) -> List[str]:
        if not value:
            return []
        if isinstance(value, (str, bytes)):
            return [str(value)]
        normalized: List[str] = []
        iterable = value if isinstance(value, (list, tuple, set)) else [value]
        for item in iterable:
            if isinstance(item, dict):
                for key in ("value", "name", "id", "speaker", "emotion"):
                    if item.get(key):
                        normalized.append(str(item[key]))
                        break
                else:
                    normalized.append(str(item))
            else:
                normalized.append(str(item))
        return normalized

    async def _fetch_fallback_items() -> List[Dict[str, Any]]:
        limit = max(1, min(int(filters.get("limit", 20) or 20), 200))
        context_lines = max(0, min(int(filters.get("context_lines", 3) or 0), 10))
        speakers_filter = {s.lower() for s in _normalize_filter_list(filters.get("speakers"))}
        emotions_filter = {e.lower() for e in _normalize_filter_list(filters.get("emotions"))}
        raw_keywords = str(filters.get("keywords", "") or "")
        keywords = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]
        match_all = filters.get("match", "any") == "all"
        start_date_str = filters.get("start_date")
        end_date_str = filters.get("end_date")

        def parse_date(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
            if not value:
                return None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
            if end_of_day and dt.tzinfo is None:
                return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            if end_of_day:
                return dt + timedelta(hours=23, minutes=59, seconds=59, microseconds=999999)
            return dt

        start_dt = parse_date(start_date_str) if start_date_str else None
        end_dt = parse_date(end_date_str, end_of_day=True) if end_date_str else None

        recent_limit = max(limit * 5, 200)
        recent_response = await proxy_request(
            f"{RAG_URL}/transcripts/recent?limit={recent_limit}",
            "GET",
            params=None,
            extra_headers=analysis_headers,
        )
        transcripts = recent_response.get("transcripts") or []

        items: List[Dict[str, Any]] = []
        for transcript in transcripts:
            created_value = transcript.get("created_at") or transcript.get("timestamp")
            transcript_dt = parse_date(created_value)
            if start_dt and transcript_dt and transcript_dt < start_dt:
                continue
            if end_dt and transcript_dt and transcript_dt > end_dt:
                continue

            segments = transcript.get("segments") or []
            for idx, segment in enumerate(segments):
                speaker_value = (segment.get("speaker") or "").strip()
                if speakers_filter and speaker_value.lower() not in speakers_filter:
                    continue

                emotion_value = (
                    (segment.get("emotion") or segment.get("dominant_emotion") or "").strip().lower()
                )
                if emotions_filter and emotion_value not in emotions_filter:
                    continue

                text_value = segment.get("text") or ""
                if keywords:
                    text_lower = text_value.lower()
                    matches = [kw for kw in keywords if kw in text_lower]
                    if match_all and len(matches) != len(keywords):
                        continue
                    if not match_all and not matches:
                        continue

                context: List[Dict[str, Any]] = []
                if context_lines:
                    start_idx = max(0, idx - context_lines)
                    for ctx_segment in segments[start_idx:idx]:
                        context.append({
                            "speaker": ctx_segment.get("speaker"),
                            "text": ctx_segment.get("text"),
                            "emotion": ctx_segment.get("emotion") or ctx_segment.get("dominant_emotion"),
                        })

                items.append({
                    "segment_id": segment.get("id"),
                    "transcript_id": transcript.get("id"),
                    "job_id": transcript.get("job_id"),
                    "speaker": segment.get("speaker"),
                    "emotion": segment.get("emotion") or segment.get("dominant_emotion"),
                    "text": text_value,
                    "created_at": created_value,
                    "start_time": segment.get("start_time"),
                    "end_time": segment.get("end_time"),
                    "context_before": context,
                })

                if len(items) >= limit:
                    return items

        return items

    logger.info(
        "[ANALYZE-STREAM] job=%s analysis_id=%s filters=%s user=%s",
        job_id,
        analysis_id,
        {k: filters.get(k) for k in ("limit", "speakers", "emotions", "start_date", "end_date", "search_type")},
        getattr(session, "user_id", None),
    )


    # Enable fallback by default to avoid breaking UX if RAG /transcripts/query is unavailable
    ANALYZE_FALLBACK_ENABLED = os.getenv("ANALYZE_FALLBACK_ENABLED", "true").lower() in {"1", "true", "yes"}

    async def event_generator():
        last_model = None
        started_at = datetime.utcnow().isoformat() + "Z"
        MAX_PROMPT_CHARS = 6000
        combined_sections: List[str] = []
        artifact_id: Optional[str] = None

        try:
            # Warmup GPU (best effort)
            try:
                await proxy_request(
                    f"{GEMMA_URL}/warmup",
                    "POST",
                    json={},
                    extra_headers=analysis_headers,
                )
                logger.info(
                    "[ANALYZE-STREAM] Warmup complete job=%s analysis_id=%s",
                    job_id,
                    analysis_id,
                )
                yield format_sse("meta", {"job_id": job_id, "message": "GPU warmup complete"})
            except Exception as warmup_error:
                logger.warning(
                    "[ANALYZE-STREAM] Warmup failed job=%s analysis_id=%s error=%s",
                    job_id,
                    analysis_id,
                    warmup_error,
                )
                yield format_sse("meta", {"job_id": job_id, "message": "GPU warmup failed; continuing"})

            rag_payload = dict(filters)
            rag_payload.setdefault("limit", max(1, min(int(filters.get("limit", 20) or 20), 200)))
            rag_payload.setdefault("context_lines", max(0, min(int(filters.get("context_lines", 3) or 0), 10)))

            fallback_used = False
            rag_query_status: Optional[int] = None
            try:
                rag_result = await proxy_request(
                    f"{RAG_URL}/transcripts/query",
                    "POST",
                    json=rag_payload,
                    extra_headers=analysis_headers,
                )
                rag_query_status = 200
                items = rag_result.get("items") or []
            except HTTPException as exc:
                if exc.status_code == 404:
                    logger.error(
                        "[ANALYZE-STREAM] RAG query endpoint 404 job=%s analysis_id=%s (fallback=%s)",
                        job_id,
                        analysis_id,
                        ANALYZE_FALLBACK_ENABLED,
                    )
                    rag_query_status = 404
                    if ANALYZE_FALLBACK_ENABLED:
                        fallback_used = True
                        items = await _fetch_fallback_items()
                    else:
                        yield format_sse("server_error", {"job_id": job_id, "detail": "RAG query unavailable"})
                        return
                else:
                    rag_query_status = exc.status_code
                    raise

            # Prefer backend-reported total if available to avoid UI jumps to the page limit
            rag_total = None
            try:
                if isinstance(rag_result, dict):
                    rag_total = rag_result.get("total") or rag_result.get("count")
            except Exception:
                rag_total = None
            total = rag_total if isinstance(rag_total, int) else len(items)
            if fallback_used:
                logger.info(
                    "[ANALYZE-STREAM] job=%s analysis_id=%s fallback produced %s candidate statements",
                    job_id,
                    analysis_id,
                    total,
                )
            else:
                logger.info(
                    "[ANALYZE-STREAM] job=%s analysis_id=%s fetched %s candidate statements",
                    job_id,
                    analysis_id,
                    total,
                )

            meta_payload = {"job_id": job_id, "total": total, "started_at": started_at}
            if fallback_used:
                meta_payload["fallback"] = "transcripts/recent"
                meta_payload["fallback_reason"] = "rag_query_404"
            if rag_query_status is not None:
                meta_payload["rag_query_status"] = rag_query_status
            yield format_sse("meta", meta_payload)
            if fallback_used:
                yield format_sse(
                    "meta",
                    {"job_id": job_id, "message": "Using fallback query (transcripts/recent filter)"},
                )

            if total == 0:
                yield format_sse(
                    "done",
                    {"job_id": job_id, "completed_at": datetime.utcnow().isoformat() + "Z", "model": None},
                )
                logger.info(
                    "[ANALYZE-STREAM] job=%s analysis_id=%s completed with no matches",
                    job_id,
                    analysis_id,
                )
                return

            for index, item in enumerate(items, start=1):
                if await http_request.is_disconnected():
                    logger.warning(
                        "[ANALYZE-STREAM] Client disconnected job=%s analysis_id=%s",
                        job_id,
                        analysis_id,
                    )
                    break

                snippet_lines: List[str] = []
                for ctx in item.get("context_before") or []:
                    snippet_lines.append(f"[Context] {ctx.get('speaker') or 'Speaker'}: {ctx.get('text')}")
                snippet_lines.append(f"[Statement] {item.get('speaker') or 'Speaker'}: {item.get('text')}")
                transcript_block = "\n".join(snippet_lines)

                if prompt_template and "{transcripts}" in prompt_template:
                    final_prompt = prompt_template.replace("{transcripts}", transcript_block)
                else:
                    base_prompt = prompt_template or "Gemma, analyze the following statement."
                    final_prompt = base_prompt.strip() + "\n\nTranscripts:\n" + transcript_block

                prompt_trimmed = False
                if len(final_prompt) > MAX_PROMPT_CHARS:
                    head = final_prompt[:2000]
                    tail = final_prompt[-(MAX_PROMPT_CHARS - 2000):]
                    final_prompt = head + "\n[TRUNCATED FOR LENGTH]\n" + tail
                    prompt_trimmed = True

                prompt_len = len(final_prompt)
                approx_prompt_tokens = max(1, prompt_len // 4)
                prompt_hash = hashlib.sha256(final_prompt.encode("utf-8")).hexdigest()[:12]
                logger.info(
                    "[ANALYZE-STREAM] job=%s analysis_id=%s statement=%s/%s prompt_hash=%s chars=%s approx_tokens=%s trimmed=%s",
                    job_id,
                    analysis_id,
                    index,
                    total,
                    prompt_hash,
                    prompt_len,
                    approx_prompt_tokens,
                    prompt_trimmed,
                )

                yield format_sse(
                    "step",
                    {
                        "job_id": job_id,
                        "i": index,
                        "total": total,
                        "status": "sending",
                        "prompt_fragment": final_prompt[:160],
                    },
                )

                gemma_request = {
                    "prompt": final_prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": 0.9,
                }

                yield format_sse(
                    "step",
                    {
                        "job_id": job_id,
                        "i": index,
                        "total": total,
                        "status": "waiting",
                    },
                )

                try:
                    response = await proxy_request(
                        f"{GEMMA_URL}/generate",
                        "POST",
                        json=gemma_request,
                        extra_headers=analysis_headers,
                    )
                except HTTPException as exc:
                    logger.error("[ANALYZE-STREAM] Gemma error job=%s: %s", job_id, exc.detail)
                    yield format_sse("error", {"job_id": job_id, "i": index, "detail": exc.detail})
                    break

                response_text = response.get("text") or response.get("response") or ""
                last_model = response.get("model") or last_model
                combined_sections.append(
                    "\n".join(
                        [
                            f"Statement {index}/{total}",
                            "Context:",
                            transcript_block,
                            "",
                            "Gemma Response:",
                            response_text,
                            "",
                        ]
                    )
                )

                yield format_sse(
                    "result",
                    {
                        "job_id": job_id,
                        "i": index,
                        "total": total,
                        "response": response_text,
                        "item": item,
                    },
                )

                logger.info(
                    "[ANALYZE-STREAM] job=%s analysis_id=%s statement=%s/%s completed tokens=%s mode=%s",
                    job_id,
                    analysis_id,
                    index,
                    total,
                    response.get("tokens_generated") if isinstance(response, dict) else "?",
                    response.get("mode") if isinstance(response, dict) else "?",
                )

            # Archive combined artifact (best effort)
            if analysis_id and combined_sections:
                archive_payload = {
                    "analysis_id": analysis_id,
                    "title": payload.get("title") or f"Streaming Analysis - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
                    "body": "\n".join(combined_sections),
                    "metadata": {
                        "filters": filters,
                        "total_statements": total,
                        "fallback_used": fallback_used,
                        "job_id": job_id,
                        "model": last_model,
                        "started_at": started_at,
                        "completed_at": datetime.utcnow().isoformat() + "Z",
                        "user_id": job.get("user_id"),
                    },
                }
                try:
                    archive_result = await proxy_request(
                        f"{RAG_URL}/analysis/archive",
                        "POST",
                        json=archive_payload,
                        extra_headers=analysis_headers,
                    )
                    artifact_id = archive_result.get("artifact_id") if isinstance(archive_result, dict) else None
                    if artifact_id:
                        logger.info(
                            "[ANALYZE-STREAM] job=%s analysis_id=%s archived artifact_id=%s",
                            job_id,
                            analysis_id,
                            artifact_id,
                        )
                except Exception as exc:
                    logger.error(
                        "[ANALYZE-STREAM] job=%s analysis_id=%s archive failed: %s",
                        job_id,
                        analysis_id,
                        exc,
                    )

            # Produce a concise executive summary of the combined sections (best effort)
            summary_text = ""
            try:
                if combined_sections:
                    summary_context = "\n\n".join(combined_sections)
                    # limit context length defensively
                    summary_context = summary_context[-12000:]
                    summary_prompt = (
                        "You are an expert conversation analyst. Based on the following analysis sections (each contains Context and Gemma Response), "
                        "write a concise executive summary with 5-8 bullet points and a 2-3 sentence conclusion. Be precise and avoid repetition.\n\n"
                        f"{summary_context}\n\n"
                        "Now provide the executive summary:"
                    )
                    gen_req = {
                        "prompt": summary_prompt,
                        "max_tokens": 384,
                        "temperature": 0.3,
                    }
                    gen_resp = await proxy_request(
                        f"{GEMMA_URL}/generate",
                        "POST",
                        json=gen_req,
                        extra_headers=analysis_headers,
                    )
                    if isinstance(gen_resp, dict):
                        summary_text = (gen_resp.get("text") or gen_resp.get("response") or "").strip()
            except Exception as exc:
                logger.warning("[ANALYZE-STREAM] summary generation failed job=%s analysis_id=%s: %s", job_id, analysis_id, exc)

            yield format_sse(
                "done",
                {
                    "job_id": job_id,
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                    "model": last_model,
                    "analysis_id": analysis_id,
                    "artifact_id": artifact_id,
                    **({"summary": summary_text} if summary_text else {}),
                },
            )
            logger.info(
                "[ANALYZE-STREAM] job=%s analysis_id=%s finished model=%s",
                job_id,
                analysis_id,
                last_model,
            )
        except asyncio.CancelledError:
            logger.warning("[ANALYZE-STREAM] Stream cancelled job=%s", job_id)
            raise
        except Exception as exc:
            logger.error(
                "[ANALYZE-STREAM] Unexpected error job=%s analysis_id=%s: %s",
                job_id,
                analysis_id,
                exc,
            )
            yield format_sse("error", {"job_id": job_id, "detail": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@app.post("/api/analyze/gemma_summary")
async def analyze_gemma_summary(
    request: Dict[str, Any],
    session: Session = Depends(require_auth)
):
    """
    Generate a conversational summary using Gemma based on provided context.
    """
    context_raw = str(request.get("context", "") or "").strip()
    if not context_raw:
        raise HTTPException(status_code=400, detail="context is required")

    # Avoid extremely large prompts (helps keep inference fast)
    context = context_raw[:8000]
    emotion_focus = (request.get("emotion") or "neutral").strip().lower()
    max_tokens = int(request.get("max_tokens") or 320)
    temperature = float(request.get("temperature") or 0.4)

    prompt = (
        "You are an expert conversation analyst. Review the transcript excerpts "
        "and produce a concise summary for an executive audience. Highlight the most "
        "important events, decisions, risks, and opportunities. If an emotion focus is provided, "
        "weave in how that emotion manifests.\n\n"
        f"Emotion focus: {emotion_focus or 'neutral'}\n\n"
        "Transcript context:\n"
        f"{context}\n\n"
        "Write the summary as bullet points followed by a short paragraph of key insights."
    )

    generation_payload = {
        "prompt": prompt,
        "max_tokens": max(120, min(max_tokens, 512)),
        "temperature": max(0.1, min(temperature, 1.0))
    }

    gemma_response = await proxy_request(
        f"{GEMMA_URL}/generate",
        "POST",
        json=generation_payload
    )

    summary_text = ""
    if isinstance(gemma_response, dict):
        summary_text = gemma_response.get("text") or gemma_response.get("response") or ""

    return {
        "success": True,
        "summary": summary_text.strip(),
        "emotion": emotion_focus,
        "model": gemma_response.get("model") if isinstance(gemma_response, dict) else None,
        "raw": gemma_response
    }


@app.post("/api/analyze/prepare_emotion_analysis")
async def analyze_prepare_emotion_analysis(
    request: Dict[str, Any],
    session: Session = Depends(require_auth)
):
    """
    Fetch emotion statistics from RAG service and tailor them for the UI.
    """
    start_date = request.get("start_date")
    end_date = request.get("end_date")

    params: Dict[str, Any] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    rag_stats = await proxy_request(
        f"{RAG_URL}/memory/emotions/stats",
        "GET",
        params=params or None
    )

    emotions_requested = request.get("emotions")
    emotion_counts: Dict[str, Any] = {}

    if isinstance(emotions_requested, list) and rag_stats:
        for emotion_name in emotions_requested:
            if isinstance(emotion_name, str):
                emotion_counts[emotion_name] = rag_stats.get(emotion_name, 0)
    else:
        # Fallback: include any numeric keys returned by backend
        for key, value in (rag_stats or {}).items():
            if isinstance(value, (int, float)):
                emotion_counts[key] = value

    return {
        "success": True,
        "start_date": start_date,
        "end_date": end_date,
        "emotions": emotion_counts,
        "raw": rag_stats
    }


@app.post("/api/analyze/personality")
async def analyze_personality(
    request: Dict[str, Any],
    session: Session = Depends(require_auth)
):
    """
    Run a quick personality analysis by collecting recent transcripts and
    prompting Gemma for a traits breakdown.
    """
    last_n = request.get("last_n_transcripts") or request.get("limit") or 15
    try:
        last_n_int = max(5, min(int(last_n), 40))
    except (TypeError, ValueError):
        last_n_int = 15

    transcripts_payload = await proxy_request(
        f"{RAG_URL}/transcripts/recent",
        "GET",
        params={"limit": last_n_int}
    )

    transcript_items = []
    if isinstance(transcripts_payload, dict):
        transcript_items = transcripts_payload.get("transcripts") or transcripts_payload.get("items") or []
    elif isinstance(transcripts_payload, list):
        transcript_items = transcripts_payload

    snippets = []
    max_snippets = 200
    for item in transcript_items[:last_n_int]:
        if not isinstance(item, dict):
            continue
        speaker = item.get("speaker") or item.get("primary_speaker") or "Speaker"
        text = item.get("snippet") or item.get("text") or item.get("full_text") or ""
        if text:
            snippets.append(f"{speaker}: {text}")
        if len(snippets) >= max_snippets:
            break
        segments = item.get("segments") or []
        if isinstance(segments, list):
            for seg in segments[:5]:
                if isinstance(seg, dict):
                    seg_speaker = seg.get("speaker") or speaker
                    seg_text = seg.get("text") or ""
                    if seg_text:
                        snippets.append(f"{seg_speaker}: {seg_text}")
                    if len(snippets) >= max_snippets:
                        break
            if len(snippets) >= max_snippets:
                break

    conversation_sample = "\n".join(snippets)[:6000] or "No transcript data available."

    prompt = (
        "You are a professional psychologist analyzing the conversation below. "
        "Provide a personality profile using Big Five traits, communication style, strengths, "
        "risks, and actionable coaching suggestions. Be balanced and evidence-driven.\n\n"
        "Conversation sample:\n"
        f"{conversation_sample}\n\n"
        "Respond with structured sections titled: 'Overview', 'Trait Breakdown', "
        "'Communication Style', 'Strengths', 'Risks', and 'Coaching Tips'."
    )

    gemma_response = await proxy_request(
        f"{GEMMA_URL}/generate",
        "POST",
        json={
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.5
        }
    )

    analysis_text = ""
    if isinstance(gemma_response, dict):
        analysis_text = gemma_response.get("text") or gemma_response.get("response") or ""

    job_id = f"persona_{uuid.uuid4().hex[:12]}"
    result_payload = {
        "job_id": job_id,
        "status": "complete",
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "result": {
            "analysis": analysis_text.strip(),
            "model": gemma_response.get("model") if isinstance(gemma_response, dict) else None,
            "raw": gemma_response
        }
    }

    # Cache for follow-up GET requests (best effort).
    personality_jobs[job_id] = result_payload

    return result_payload


@app.get("/api/analyze/personality/{job_id}")
async def get_personality_result(
    job_id: str,
    session: Session = Depends(require_auth)
):
    """
    Return previously computed personality analysis.
    """
    job = personality_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Personality analysis not found")
    return job

# ============================================================================
# RAG Endpoints
# ============================================================================

@app.post("/api/rag/query")
async def rag_query(request: Dict[str, Any], session: Session = Depends(require_auth)):
    result = await proxy_request(f"{RAG_URL}/query", "POST", json=request)
    return result

@app.post("/api/search/semantic")
async def search_semantic(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """Proxy unified semantic search to RAG service"""
    result = await proxy_request(f"{RAG_URL}/search/semantic", "POST", json=request)
    return result

@app.post("/api/rag/memory/search")
async def rag_search(request: Dict[str, Any], session: Session = Depends(require_auth)):
    result = await proxy_request(f"{RAG_URL}/memory/search", "POST", json=request)
    return result

# ============================================================================
# Memory Endpoints (Proxy to RAG service)
# ============================================================================

@app.get("/api/memory/list")
async def memory_list(
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(require_auth)
):
    """List all memories with pagination"""
    result = await proxy_request(f"{RAG_URL}/memory/list?limit={limit}&offset={offset}", "GET")
    return result

@app.post("/api/memory/search")
async def memory_search(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """Search memories"""
    result = await proxy_request(f"{RAG_URL}/memory/search", "POST", json=request)
    return result

@app.post("/api/memory/add")
async def memory_add(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """Add a memory (proxy to RAG service)"""
    result = await proxy_request(f"{RAG_URL}/memory/add", "POST", json=request)
    return result


@app.post("/api/memory/create")
async def memory_create(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """
    Alias for memory creation expected by the frontend SDK.
    Requires at minimum a title and body.
    """
    title = (request.get("title") or "").strip()
    body = (request.get("body") or "").strip()
    if not title or not body:
        raise HTTPException(status_code=400, detail="title and body are required")

    payload = {
        "title": title,
        "body": body,
        "metadata": request.get("metadata") or {}
    }
    return await memory_add(payload, session=session)

@app.get("/api/memory/stats")
async def memory_stats(session: Session = Depends(require_auth)):
    """Get memory statistics"""
    result = await proxy_request(f"{RAG_URL}/memory/stats", "GET")
    return result

@app.get("/api/memory/emotions/stats")
async def memory_emotions_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Session = Depends(require_auth)
):
    """Get emotion statistics with optional date filtering"""
    params = []
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")
    query_string = f"?{'&'.join(params)}" if params else ""
    result = await proxy_request(f"{RAG_URL}/memory/emotions/stats{query_string}", "GET")
    return result


@app.get("/api/analytics/signals")
async def analytics_signals(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    speakers: Optional[str] = None,
    emotions: Optional[str] = None,
    metrics: Optional[str] = None,
    session: Session = Depends(require_auth)
):
    """Proxy analytics overlays to the insights service."""
    query_params = {}
    if start_date:
        query_params["start_date"] = start_date
    if end_date:
        query_params["end_date"] = end_date
    if speakers:
        query_params["speakers"] = speakers
    if emotions:
        query_params["emotions"] = emotions
    if metrics:
        query_params["metrics"] = metrics
    query_string = f"?{urlencode(query_params)}" if query_params else ""
    result = await proxy_request(f"{INSIGHTS_URL}/analytics/signals{query_string}", "GET")
    return result

@app.get("/api/transcripts/speakers")
async def transcripts_speakers(session: Session = Depends(require_auth)):
    result = await proxy_request(f"{RAG_URL}/transcripts/speakers", "GET")
    return result


@app.post("/api/transcripts/count")
async def transcripts_count(
    payload: Dict[str, Any],
    http_request: Request,
    session: Session = Depends(require_auth)
):
    analysis_id = http_request.headers.get("X-Analysis-Id")
    headers = {"X-Analysis-Id": analysis_id} if analysis_id else None
    try:
        result = await proxy_request(
            f"{RAG_URL}/transcripts/count",
            "POST",
            json=payload,
            extra_headers=headers,
        )
        return result
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        logger.warning("[COUNT-FALLBACK] /transcripts/count 404 – deriving count from /transcripts/recent window")
        # Derive a best-effort count from the same recent window used in query fallback
        qp = dict(payload or {})
        qp.setdefault("limit", 500)
        browse = await transcripts_query(qp, http_request)
        return {"success": True, "count": int(browse.get("total", 0))}


@app.post("/api/transcripts/query")
async def transcripts_query(
    payload: Dict[str, Any],
    http_request: Request,
    session: Session = Depends(require_auth)
):
    analysis_id = http_request.headers.get("X-Analysis-Id")
    headers = {"X-Analysis-Id": analysis_id} if analysis_id else None
    try:
        result = await proxy_request(
            f"{RAG_URL}/transcripts/query",
            "POST",
            json=payload,
            extra_headers=headers,
        )
        return result
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        # Compatibility fallback for older RAG builds without /transcripts/query
        logger.warning("[QUERY-FALLBACK] /transcripts/query 404 – using /transcripts/recent filter path")

        def _norm_list(value):
            if not value:
                return []
            if isinstance(value, (list, tuple, set)):
                return [str(v) for v in value]
            return [str(value)]

        limit = max(1, min(int(payload.get("limit", 50) or 50), 500))
        offset = max(0, int(payload.get("offset", 0) or 0))
        speakers = {s.lower() for s in _norm_list(payload.get("speakers"))}
        emotions = {e.lower() for e in _norm_list(payload.get("emotions"))}
        raw_keywords = str(payload.get("keywords", "") or "")
        keywords = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]
        require_all = (payload.get("match") or "any").lower() == "all"
        sort_by = (payload.get("sort_by") or "created_at").lower()
        allowed_sorts = {"created_at", "speaker", "emotion", "job_id", "start_time"}
        if sort_by not in allowed_sorts:
            sort_by = "created_at"
        order = (payload.get("order") or "desc").lower()
        if order not in {"asc", "desc"}:
            order = "desc"
        reverse_sort = (order == "desc")
        target_count = max(limit + offset, limit)

        recent_limit = max(target_count * 4, 500)
        recent = await proxy_request(
            f"{RAG_URL}/transcripts/recent?limit={recent_limit}",
            "GET",
            params=None,
            extra_headers=headers,
        )
        transcripts = recent.get("transcripts") or []

        def _timestamp_value(value: Optional[Any]) -> float:
            if value in (None, ""):
                return 0.0
            if isinstance(value, datetime):
                return value.timestamp()
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value)
            try:
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                return datetime.fromisoformat(text).timestamp()
            except Exception:
                return 0.0

        def _sort_key(item: Dict[str, Any]) -> Any:
            if sort_by == "speaker":
                return (item.get("speaker") or "").lower()
            if sort_by == "emotion":
                return (item.get("emotion") or "").lower()
            if sort_by == "job_id":
                return item.get("job_id") or ""
            if sort_by == "start_time":
                return _timestamp_value(item.get("start_time"))
            return _timestamp_value(item.get("created_at"))

        items = []
        for tr in transcripts:
            segments = tr.get("segments") or []
            for idx, seg in enumerate(segments):
                if speakers:
                    sv = (seg.get("speaker") or "").lower().strip()
                    if sv not in speakers:
                        continue
                if emotions:
                    ev = (seg.get("emotion") or tr.get("dominant_emotion") or "").lower()
                    if ev not in emotions:
                        continue
                if keywords:
                    text = (seg.get("text") or "").lower()
                    if not text:
                        continue
                    hits = [kw for kw in keywords if kw in text]
                    if require_all and len(hits) != len(keywords):
                        continue
                    if not require_all and len(hits) == 0:
                        continue
                items.append({
                    "segment_id": f"fallback-{tr.get('job_id', 'job')}-{idx}",
                    "transcript_id": tr.get("transcript_id"),
                    "job_id": tr.get("job_id"),
                    "speaker": seg.get("speaker"),
                    "emotion": seg.get("emotion") or tr.get("dominant_emotion"),
                    "emotion_confidence": seg.get("emotion_confidence"),
                    "text": seg.get("text"),
                    "created_at": tr.get("created_at"),
                    "start_time": seg.get("start_time"),
                    "end_time": seg.get("end_time"),
                    "context_before": [],
                    "context_after": [],
                })
                if len(items) >= target_count:
                    break
            if len(items) >= target_count:
                break

        items.sort(key=_sort_key, reverse=reverse_sort)
        total = len(items)
        page = items[offset:offset + limit]
        count = len(page)
        has_more = (offset + count) < total
        next_offset = offset + count

        return {
            "success": True,
            "items": page,
            "count": count,
            "total": total,
            "has_more": has_more,
            "next_offset": next_offset,
            "sort_by": sort_by,
            "order": order,
            "fallback": "transcripts/recent",
        }


@app.get("/api/transcripts/recent")
async def transcripts_recent(
    limit: int = 10,
    session: Session = Depends(require_auth)
):
    """Get recent transcripts"""
    result = await proxy_request(f"{RAG_URL}/transcripts/recent?limit={limit}", "GET")
    return result

@app.get("/api/transcript/{job_id}")
async def transcript_get(
    job_id: str,
    session: Session = Depends(require_auth)
):
    """Get transcript by job_id"""
    result = await proxy_request(f"{RAG_URL}/transcript/{job_id}", "GET")
    return result


# ============================================================================
# Analysis Artifacts API
# ============================================================================


@app.post("/api/analysis/archive")
async def analysis_archive(
    payload: Dict[str, Any],
    http_request: Request,
    session: Session = Depends(require_auth)
):
    analysis_id = http_request.headers.get("X-Analysis-Id")
    if analysis_id:
        payload.setdefault("analysis_id", analysis_id)
    headers = {"X-Analysis-Id": analysis_id} if analysis_id else None
    try:
        result = await proxy_request(
            f"{RAG_URL}/analysis/archive",
            "POST",
            json=payload,
            extra_headers=headers,
        )
        return result
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        logger.warning("[ANALYSIS-ARCHIVE] RAG 404 – storing artifact locally")
        artifact = _persist_fallback_artifact(payload, session)
        return {"success": True, "artifact_id": artifact["artifact_id"], "fallback": True}


@app.get("/api/analysis/list")
async def analysis_list(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(require_auth)
):
    params = []
    if limit:
        params.append(f"limit={limit}")
    if offset:
        params.append(f"offset={offset}")
    query = "&".join(params)
    logger.info(
        "[ANALYSIS-LIST] user=%s limit=%s offset=%s",
        getattr(session, "user_id", None),
        limit,
        offset,
    )
    try:
        result = await proxy_request(
            f"{RAG_URL}/analysis/list{'?' + query if query else ''}",
            "GET",
        )
        logger.info(
            "[ANALYSIS-LIST] success user=%s count=%s has_more=%s",
            getattr(session, "user_id", None),
            (result or {}).get("count"),
            (result or {}).get("has_more"),
        )
        return result
    except HTTPException as exc:
        if exc.status_code != 404:
            logger.error(
                "[ANALYSIS-LIST] error user=%s status=%s",
                getattr(session, "user_id", None),
                exc.status_code,
            )
            raise
        logger.warning("[ANALYSIS-LIST] RAG 404 – using fallback store")
        return _list_fallback_artifacts(limit, offset)


@app.get("/api/analysis/{artifact_id}")
async def analysis_get(
    artifact_id: str,
    session: Session = Depends(require_auth)
):
    logger.info(
        "[ANALYSIS-GET] user=%s artifact_id=%s",
        getattr(session, "user_id", None),
        artifact_id,
    )
    try:
        result = await proxy_request(
            f"{RAG_URL}/analysis/{artifact_id}",
            "GET",
        )
        logger.info(
            "[ANALYSIS-GET] success user=%s artifact_id=%s",
            getattr(session, "user_id", None),
            artifact_id,
        )
        return result
    except HTTPException as exc:
        if exc.status_code != 404:
            logger.error(
                "[ANALYSIS-GET] error user=%s artifact_id=%s status=%s",
                getattr(session, "user_id", None),
                artifact_id,
                exc.status_code,
            )
            raise
        fallback = _get_fallback_artifact(artifact_id)
        if fallback:
            return {"success": True, "artifact": fallback, "source": "gateway_fallback"}
        logger.error(
            "[ANALYSIS-GET] artifact_id=%s not found in fallback store",
            artifact_id,
        )
        raise


@app.post("/api/analysis/search")
async def analysis_search(
    payload: Dict[str, Any],
    session: Session = Depends(require_auth)
):
    logger.info(
        "[ANALYSIS-SEARCH] user=%s query=%s limit=%s",
        getattr(session, "user_id", None),
        (payload or {}).get("query"),
        (payload or {}).get("limit"),
    )
    try:
        result = await proxy_request(
            f"{RAG_URL}/analysis/search",
            "POST",
            json=payload,
        )
        logger.info(
            "[ANALYSIS-SEARCH] success user=%s count=%s",
            getattr(session, "user_id", None),
            len(result.get("items") or []) if isinstance(result, dict) else "?",
        )
        return result
    except HTTPException as exc:
        logger.error(
            "[ANALYSIS-SEARCH] error user=%s status=%s",
            getattr(session, "user_id", None),
            exc.status_code,
        )
        raise


# ============================================================================
# Meta-Analysis and Chat-on-Artifact (Gemma)
# ============================================================================


@app.post("/api/analysis/meta")
async def analysis_meta(
    payload: Dict[str, Any],
    http_request: Request,
    session: Session = Depends(require_auth),
):
    analysis_id = http_request.headers.get("X-Analysis-Id") or f"meta_{uuid.uuid4().hex[:10]}"
    headers = {"X-Analysis-Id": analysis_id}

    async def streamer():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{GEMMA_URL}/analyze/meta",
                    json=payload,
                    headers=headers,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StarletteStreamingResponse(streamer(), media_type="text/event-stream")


@app.post("/api/gemma/chat-on-artifact")
async def chat_on_artifact_api(
    payload: Dict[str, Any],
    session: Session = Depends(require_auth),
):
    result = await proxy_request(
        f"{GEMMA_URL}/chat-on-artifact",
        "POST",
        json=payload,
    )
    return result


@app.post("/api/gemma/chat-on-artifact/v2")
async def chat_on_artifact_v2_api(
    payload: Dict[str, Any],
    session: Session = Depends(require_auth),
):
    result = await proxy_request(
        f"{GEMMA_URL}/chat-on-artifact/v2",
        "POST",
        json=payload,
    )
    return result


@app.get("/api/result/{job_id}")
async def api_result_get(
    job_id: str,
    session: Session = Depends(require_auth)
):
    """Alias for /api/transcript/{job_id} used by older frontend components."""
    return await transcript_get(job_id=job_id, session=session)


@app.get("/api/latest_result")
async def latest_result(session: Session = Depends(require_auth)):
    """
    Return the most recent transcript entry for quick UI previews.
    """
    data = await proxy_request(f"{RAG_URL}/transcripts/recent?limit=1", "GET")
    latest = None

    if isinstance(data, dict):
        candidates = data.get("transcripts") or data.get("items") or []
        if isinstance(candidates, list) and candidates:
            latest = candidates[0]
    elif isinstance(data, list) and data:
        latest = data[0]

    return {
        "success": True,
        "result": latest,
        "raw": data
    }

# ============================================================================
# Emotion Endpoints
# ============================================================================

@app.post("/api/emotion/analyze")
async def emotion_analyze(request: Dict[str, Any], session: Session = Depends(require_auth)):
    result = await proxy_request(f"{EMOTION_URL}/analyze", "POST", json=request)
    return result

# ============================================================================
# Transcription Endpoints
# ============================================================================

@app.post("/api/transcription/transcribe")
async def transcription_transcribe(
    file: UploadFile = File(...),
    session: Session = Depends(require_auth)
):
    """Transcribe audio file"""
    if not service_auth:
        logger.error("[TRANSCRIBE-API] ❌ service_auth unavailable")
        raise HTTPException(status_code=503, detail="Service authentication unavailable")

    headers: Dict[str, str] = {}
    try:
        token = service_auth.create_token(expires_in=60)
        headers["X-Service-Token"] = token
        logger.debug("[TRANSCRIBE-API] JWT attached for transcription request")
    except Exception as e:
        logger.error(f"[TRANSCRIBE-API] ❌ Failed to create JWT token: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service authentication unavailable")
    
    # Read file content
    file_content = await file.read()
    # Content-type and size validation
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid content type; expected audio/*")
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_MB}MB)")
    
    logger.info("[TRANSCRIBE-API] Forwarding audio chunk (%s bytes)", len(file_content))
    files = {"audio": (file.filename or "audio.wav", file_content, file.content_type or "audio/wav")}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        logger.info(f"[TRANSCRIBE-API] Forwarding to {TRANSCRIPTION_URL}/transcribe")
        response = await client.post(
            f"{TRANSCRIPTION_URL}/transcribe",
            headers=headers,
            files=files
        )
        response.raise_for_status()
        return response.json()

@app.post("/api/transcription/stream")
async def transcription_stream(request: Dict[str, Any], session: Session = Depends(require_auth)):
    """Start streaming transcription session"""
    result = await proxy_request(f"{TRANSCRIPTION_URL}/stream", "POST", json=request)
    return result

# Direct transcribe endpoint (for Flutter app compatibility)
@app.post("/transcribe")
async def transcribe_direct(request: Request, session: Session = Depends(require_auth)):
    """Direct transcribe endpoint - forwards to transcription service (flexible input)"""
    if not service_auth:
        logger.error("[TRANSCRIBE] ❌ service_auth unavailable")
        raise HTTPException(status_code=503, detail="Service authentication unavailable")

    headers: Dict[str, str] = {}
    try:
        token = service_auth.create_token(expires_in=60)
        headers["X-Service-Token"] = token
        logger.debug("[TRANSCRIBE] JWT attached for direct request")
    except Exception as e:
        logger.error(f"[TRANSCRIBE] ❌ Failed to create JWT token: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service authentication unavailable")
    
    try:
        content_type = request.headers.get("content-type", "")
        logger.info(f"[TRANSCRIBE] Received request with content-type: {content_type}")
        
        # Handle multipart form data
        if "multipart/form-data" in content_type:
            form = await request.form()
            logger.info(f"[TRANSCRIBE] Form fields: {list(form.keys())}")
            
            # Look for file in common field names
            file = None
            for field_name in ["file", "audio", "recording", "data"]:
                if field_name in form:
                    file = form[field_name]
                    logger.info(f"[TRANSCRIBE] Found file in field '{field_name}'")
                    break
            
            if file:
                # Read file content
                if hasattr(file, 'read'):
                    file_content = await file.read()
                else:
                    file_content = file
                    
                logger.info(f"[TRANSCRIBE] File size: {len(file_content)} bytes")
                if len(file_content) > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_MB}MB)")
                
                # Extract other form fields (seq, stream_id, format, sample_rate)
                form_data = {}
                for key in form.keys():
                    if key not in ["file", "audio", "recording", "data"]:
                        form_data[key] = form[key]
                
                logger.info(f"[TRANSCRIBE] Additional form data: {form_data}")
                
                # Transcription service expects field name "audio"
                files = {"audio": ("audio.wav", file_content, "audio/wav")}
            else:
                logger.error(f"[TRANSCRIBE] No file found. Available fields: {list(form.keys())}")
                raise HTTPException(status_code=400, detail=f"No file in multipart data. Fields: {list(form.keys())}")
        else:
            # Handle raw body
            body = await request.body()
            logger.info(f"[TRANSCRIBE] Received raw body: {len(body)} bytes")
            
            if len(body) == 0:
                raise HTTPException(status_code=400, detail="No audio data provided")
            if len(body) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_MB}MB)")
                
            files = {"file": ("audio.wav", body, "audio/wav")}
        
        # Forward to transcription service
        async with httpx.AsyncClient(timeout=120.0) as client:
            logger.info(f"[TRANSCRIBE] Forwarding to {TRANSCRIPTION_URL}/transcribe")
            logger.info(f"[TRANSCRIBE] 📤 Headers being sent: {list(headers.keys())}")  # Log header names only
            
            # Build multipart data including form fields if present
            multipart_data = []
            
            # Add audio file
            for field_name, file_info in files.items():
                filename, content, content_type = file_info
                multipart_data.append((field_name, (filename, content, content_type)))
            
            # Add other form fields
            if 'form_data' in locals():
                for key, value in form_data.items():
                    multipart_data.append((key, (None, str(value))))
            
            logger.info(f"[TRANSCRIBE] 📋 Multipart fields: {[k for k,v in multipart_data]}")
            
            response = await client.post(
                f"{TRANSCRIPTION_URL}/transcribe",
                headers=headers,
                files=multipart_data if multipart_data else files
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"[TRANSCRIBE] Success: {result}")
            return result
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TRANSCRIBE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transcribe")
async def api_transcribe(request: Request, session: Session = Depends(require_auth)):
    """Alias route for frontend clients that prefix endpoints with /api."""
    return await transcribe_direct(request=request, session=session)

# ============================================================================

# ============================================================================
# Speaker Enrollment Routes
# ============================================================================

@app.post("/enroll/upload")
async def enroll_upload(
    audio: UploadFile = File(...),
    speaker: str = Form(...),
    session: Session = Depends(require_auth)
):
    """
    Upload enrollment audio for speaker voice profile
    
    Creates a speaker embedding from 90-120 seconds of voice audio
    Saves to instance/enrollment/{speaker_name}/
    """
    import os
    import tempfile
    import numpy as np
    import soundfile as sf
    from pathlib import Path
    
    try:
        # Validate speaker name
        speaker_clean = speaker.strip().lower()
        if not speaker_clean:
            raise HTTPException(status_code=400, detail="Speaker name required")
        if not SPEAKER_ID_PATTERN.fullmatch(speaker_clean):
            raise HTTPException(
                status_code=400,
                detail="Speaker name must be 1-64 characters of lowercase letters, digits, '_' or '-'",
            )
        
        # Read audio data
        audio_data = await audio.read()
        # Size and type checks
        if audio.content_type and not audio.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="Invalid content type; expected audio/*")
        if len(audio_data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_MB}MB)")
        logger.info(f"[ENROLL] Processing enrollment for '{speaker_clean}' ({len(audio_data)} bytes)")
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            # Load and validate audio
            audio_array, sample_rate = sf.read(tmp_path)
            duration = len(audio_array) / sample_rate
            
            if duration < 90:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Audio too short ({duration:.1f}s). Need at least 90 seconds."
                )
            
            logger.info(f"[ENROLL] Audio: {duration:.1f}s at {sample_rate}Hz")
            
            # Resample to 16kHz if needed
            if sample_rate != 16000:
                import librosa
                audio_array = librosa.resample(audio_array, orig_sr=sample_rate, target_sr=16000)
                sample_rate = 16000
                
                # Save resampled audio
                resampled_path = tmp_path.replace(".wav", "_16k.wav")
                sf.write(resampled_path, audio_array, sample_rate)
                os.remove(tmp_path)
                tmp_path = resampled_path
            
            # Create enrollment directory
            enrollment_dir = Path("instance/enrollment") / speaker_clean
            enrollment_dir.mkdir(parents=True, exist_ok=True)
            
            # Save the enrollment audio
            enrollment_audio_path = enrollment_dir / "enrollment.wav"
            sf.write(str(enrollment_audio_path), audio_array, sample_rate)
            logger.info(f"[ENROLL] Saved audio to {enrollment_audio_path}")
            
            # Generate speaker embedding using TitaNet (if available)
            try:
                # Try to use transcription service's speaker model
                embedding_response = await httpx.AsyncClient(timeout=60.0).post(
                    f"{TRANSCRIPTION_URL}/generate_embedding",
                    files={"audio": (audio.filename, open(tmp_path, "rb"), "audio/wav")}
                )
                
                if embedding_response.status_code == 200:
                    embedding_data = embedding_response.json()
                    embedding = np.array(embedding_data["embedding"])
                    
                    # Save embedding
                    embedding_path = enrollment_dir.parent / f"{speaker_clean}_embedding.npy"
                    np.save(str(embedding_path), embedding)
                    logger.info(f"[ENROLL] Saved embedding to {embedding_path}")
                    
                    return {
                        "status": "success",
                        "message": f"Enrollment successful for '{speaker_clean}'",
                        "speaker": speaker_clean,
                        "duration": duration,
                        "audio_path": str(enrollment_audio_path),
                        "embedding_path": str(embedding_path),
                        "auto_processed": True
                    }
                else:
                    logger.warning(f"[ENROLL] Could not generate embedding: {embedding_response.status_code}")
                    
            except Exception as emb_error:
                logger.warning(f"[ENROLL] Embedding generation failed: {emb_error}")
            
            # Return success even without embedding (can be processed later)
            return {
                "status": "success",
                "message": f"Enrollment audio saved for '{speaker_clean}'. Run embedding generation script.",
                "speaker": speaker_clean,
                "duration": duration,
                "audio_path": str(enrollment_audio_path),
                "embedding_path": None,
                "auto_processed": False
            }
            
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENROLL] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {str(e)}")


@app.get("/enroll/speakers")
async def list_enrolled_speakers(session = Depends(require_auth)):
    """List all enrolled speakers"""
    import os
    from pathlib import Path
    
    try:
        enrollment_dir = Path("instance/enrollment")
        
        if not enrollment_dir.exists():
            return {"speakers": [], "count": 0}
        
        # Find all speaker directories
        speakers = []
        for item in enrollment_dir.iterdir():
            if item.is_dir():
                speakers.append(item.name)
            elif item.name.endswith("_embedding.npy"):
                # Also list speakers with just embeddings
                speaker_name = item.name.replace("_embedding.npy", "")
                if speaker_name not in speakers:
                    speakers.append(speaker_name)
        
        speakers.sort()
        
        return {
            "speakers": speakers,
            "count": len(speakers)
        }
        
    except Exception as e:
        logger.error(f"[ENROLL] Error listing speakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/enroll/upload")
async def api_enroll_upload(
    audio: UploadFile = File(...),
    speaker: str = Form(...),
    session: Session = Depends(require_auth)
):
    """Alias for /enroll/upload to support /api prefix."""
    return await enroll_upload(audio=audio, speaker=speaker, session=session)


@app.get("/api/enroll/speakers")
async def api_list_enrolled_speakers(session: Session = Depends(require_auth)):
    """Alias for /enroll/speakers to support /api prefix."""
    return await list_enrolled_speakers(session=session)

# Root & Frontend
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/ui/login.html")

# Mount static frontend with no-cache headers to prevent VPN/browser caching issues
if FRONTEND_DIR.exists():
    app.mount("/ui", NoCacheStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info(f"Frontend mounted at /ui from {FRONTEND_DIR} (with no-cache headers)")
else:
    logger.warning(f"Frontend not found at {FRONTEND_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
