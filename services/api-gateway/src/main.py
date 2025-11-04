"""
API Gateway Service
Handles authentication, routing, and frontend serving
"""
import base64
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, Depends, Cookie, Header, File, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
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

# Configuration
GEMMA_URL = os.getenv("GEMMA_URL", "http://gemma-service:8001")
RAG_URL = os.getenv("RAG_URL", "http://rag-service:8004")
EMOTION_URL = os.getenv("EMOTION_URL", "http://emotion-service:8005")
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_URL", "http://transcription-service:8003")
# Security & CORS
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1,http://localhost").split(",") if o.strip()]
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1","true","yes"}
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "strict").lower()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# Speaker identifier validation pattern (lowercase alphanumerics, hyphen, underscore)
SPEAKER_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
# Frontend is at /app/frontend in container
FRONTEND_DIR = Path("/app/frontend") if Path("/app/frontend").exists() else Path(__file__).parent.parent.parent.parent.parent / "frontend"

# Global auth manager and service auth
auth_manager = None
service_auth = None
login_attempts: Dict[str, Dict[str, Any]] = {"window": 60, "limit": 5, "ips": {}}


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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

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
        # Determine scope and limit
        path = request.url.path
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

# Enable rate limiting
app.add_middleware(RateLimitMiddleware)


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
            "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'"
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
        try:
            if request.method in {"POST", "PUT", "DELETE"} and request.url.path not in self.exempt_paths:
                print(f"[CSRF MIDDLEWARE] Processing {request.method} {request.url.path}", flush=True)
                # Validate session
                ws_session = request.cookies.get("ws_session")
                
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
                header_token = request.headers.get("X-CSRF-Token")
                cookie_token = request.cookies.get("csrf_token")
                if not header_token or not cookie_token or header_token != cookie_token or header_token != session.csrf_token:
                    return Response(content='{"detail":"CSRF validation failed"}', media_type="application/json", status_code=403)
        except Exception as e:
            print(f"[CSRF MIDDLEWARE] EXCEPTION: {e}", flush=True)
            import traceback
            traceback.print_exc()
        return await call_next(request)

app.add_middleware(CSRFMiddleware)

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
        key="ws_session",
        value=session_token,
        httponly=True,
        max_age=86400,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE
    )
    # CSRF cookie (readable)
    response.set_cookie(
        key="csrf_token",
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
async def logout(response: Response, ws_session: Optional[str] = Cookie(None)):
    # Just delete the cookie - session will expire naturally
    response.delete_cookie("ws_session")
    return {"success": True}

@app.get("/api/auth/session")
async def check_session(ws_session: Optional[str] = Cookie(None)):
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
async def check_auth(ws_session: Optional[str] = Cookie(None)):
    """Check if user is authenticated - used by frontend auth.js"""
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
    files: Optional[Dict[str, Any]] = None
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
                body_size = len(response.content or b"")
                logger.error(
                    "❌ [PROXY %s] Non-200 status=%s body_size=%s bytes",
                    request_id,
                    response.status_code,
                    body_size,
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
        body_size = len(e.response.content or b"")
        logger.error(
            "❌ [PROXY %s] HTTP ERROR: status=%s duration=%sms body_size=%s bytes",
            request_id,
            e.response.status_code,
            duration_ms,
            body_size,
        )
        raise HTTPException(status_code=e.response.status_code, detail="Upstream service error")
    except Exception as e:
        duration_ms = int((time.time() - start_ts) * 1000)
        logger.error(f"💥 [PROXY {request_id}] EXCEPTION after {duration_ms}ms: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"💥 [PROXY {request_id}] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")

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

# Root & Frontend
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/ui/login.html")

# Mount static frontend
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info(f"Frontend mounted at /ui from {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend not found at {FRONTEND_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
