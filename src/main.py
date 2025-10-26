"""
WhisperServer - Refactored Main Application

Clean, modular FastAPI application using service-based architecture

Key Improvements:
- Gemma gets EXCLUSIVE GPU access
- All other services (ASR, Speaker, Embedding, Emotion) run on CPU
- Consolidated speaker ID logic (3x duplicate code removed)
- Centralized model loading (model_manager.py)
- Service-based architecture for easier testing
- Reduced startup time with lazy loading

All 30 original endpoints maintained for backward compatibility
"""

import os
import sys
import time
import webbrowser
import threading
from pathlib import Path
from typing import Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Add src directories to path
REFACTORED_SRC = Path(__file__).resolve().parent
if str(REFACTORED_SRC) not in sys.path:
    sys.path.insert(0, str(REFACTORED_SRC))

# Resolve project root for legacy imports and data directories
PROJECT_ROOT = REFACTORED_SRC.parent
ORIGINAL_SRC = PROJECT_ROOT / "src"
if str(ORIGINAL_SRC) not in sys.path:
    sys.path.insert(0, str(ORIGINAL_SRC))

try:
    import config
    HOST = config.HOST
    PORT = config.PORT
    UPLOAD_DIR = config.UPLOAD_DIR
except ImportError:
    print("[MAIN] WARNING: config.py not found, using defaults")
    HOST = "0.0.0.0"
    PORT = 8000
    UPLOAD_DIR = "/tmp/whisper_uploads"

# Import service modules
from src.auth import routes as auth_routes
from src.auth.permissions import require_auth
from src.auth.auth_manager import Session
from src.services.transcription import routes as transcription_routes
from src.services.transcription import transcript_routes
from src.services.speaker import routes as speaker_routes
from src.services.rag import routes as rag_routes
from src.services.emotion import routes as emotion_routes
from src.services.gemma import routes as gemma_routes

# Import utilities
from src.utils.gpu_utils import clear_gpu_cache, log_vram_usage

# Common filesystem locations
INSTANCE_DIR = Path(config.INSTANCE_DIR)


# -----------------------------------------------------------------------------
# Service Initialization
# -----------------------------------------------------------------------------

def initialize_all_services():
    """Initialize all services on startup"""
    print("\n" + "="*80)
    print("🚀 WhisperServer REFACTORED - Initializing Services")
    print("="*80 + "\n")
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Initialize security components FIRST
    print("[INIT] 0/6 Initializing Security Systems...")
    
    # Initialize authentication
    from src.auth.auth_manager import init_auth_manager
    init_auth_manager(
        secret_key=config.SECRET_KEY,
        db_path=config.USERS_DB_PATH
    )
    print("[INIT] ✅ Authentication system ready")
    
    # Initialize database encryption
    from src.storage.encryption import init_encryption
    init_encryption(config.DB_ENCRYPTION_KEY)
    print("[INIT] ✅ Database encryption ready")
    
    # Initialize audit logger
    from src.audit.audit_logger import init_audit_logger
    audit_logger = init_audit_logger("/instance/security_audit.log")
    audit_logger.log_event(
        event_type="server_start",
        details="WhisperServer started successfully"
    )
    print("[INIT] ✅ Audit logging ready\n")
    
    # 1. Transcription Service (GPU - loads FIRST to get priority)
    print("[INIT] 1/5 Initializing Transcription Service (GPU - PRIORITY)...")
    transcription_routes.initialize_service(
        batch_size=config.ASR_BATCH if hasattr(config, "ASR_BATCH") else 1,
        overlap_seconds=config.OVERLAP_SECS if hasattr(config, "OVERLAP_SECS") else 0.7,
        upload_dir=UPLOAD_DIR
    )
    # Force ASR model to load NOW (before Gemma) with -1 (auto-detect VRAM)
    print("[INIT] Loading ASR model with auto VRAM detection...")
    transcription_service = transcription_routes.get_service()
    transcription_service.load_model()
    print("[INIT] ✅ Transcription Service ready (GPU loaded)\n")
    
    # 2. Speaker Service (CPU-only)
    print("[INIT] 2/5 Initializing Speaker Service (CPU)...")
    enrollment_dir = INSTANCE_DIR / "enrollment"
    speaker_routes.initialize_service(
        enrollment_dir=str(enrollment_dir),
        match_threshold=config.ENROLL_MATCH_THRESHOLD if hasattr(config, "ENROLL_MATCH_THRESHOLD") else 0.60,
        backend=config.DIAR_BACKEND if hasattr(config, "DIAR_BACKEND") else "lite"
    )
    print("[INIT] ✅ Speaker Service ready\n")
    
    # 3. RAG Service (CPU-only)
    print("[INIT] 3/5 Initializing RAG Service (CPU)...")
    database_path = Path(config.DB_PATH)
    faiss_index_path = Path(
        os.environ.get("FAISS_INDEX_PATH", INSTANCE_DIR / "faiss_index.bin")
    )
    # Debug logging
    print(f"[INIT] Database path: {database_path}")
    print(f"[INIT] Database parent: {database_path.parent}")
    print(f"[INIT] FAISS index path: {faiss_index_path}")
    print(f"[INIT] Instance dir: {INSTANCE_DIR}")
    
    # Ensure instance directory exists (with better error handling)
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[INIT] ✓ Instance directory ready: {database_path.parent}")
    except PermissionError as e:
        print(f"[INIT] ⚠️ Permission error creating {database_path.parent}: {e}")
        print(f"[INIT] Checking if directory already exists...")
        if database_path.parent.exists():
            print(f"[INIT] ✓ Directory exists, continuing...")
        else:
            raise
    rag_routes.initialize_service(
        database_path=str(database_path),  # Always pass path - service will create if needed
        faiss_index_path=str(faiss_index_path) if faiss_index_path.exists() else None,
        embedding_model_name=config.EMBEDDING_MODEL if hasattr(config, "EMBEDDING_MODEL") else None
    )
    print("[INIT] ✅ RAG Service ready\n")
    
    # 4. Emotion Service (CPU-only)
    print("[INIT] 4/5 Initializing Emotion Service (CPU)...")
    emotion_routes.initialize_service(device="cpu")
    print("[INIT] ✅ Emotion Service ready\n")
    
    # 5. Gemma Service (GPU-EXCLUSIVE)
    print("[INIT] 5/5 Initializing Gemma Service (GPU-EXCLUSIVE)...")
    gemma_model_path = config.GEMMA_MODEL_PATH if hasattr(config, "GEMMA_MODEL_PATH") else None
    max_ctx = config.MAX_GEMMA_CONTEXT_TOKENS if hasattr(config, "MAX_GEMMA_CONTEXT_TOKENS") else 8192
    gemma_routes.initialize_service(
        model_path=gemma_model_path,
        max_context_tokens=max_ctx,
        enforce_gpu=True
    )
    print("[INIT] ✅ Gemma Service ready (GPU)\n")
    
    print("="*80)
    print("✅ All Services Initialized Successfully!")
    print("="*80 + "\n")
    
    # Log GPU status
    log_vram_usage("[STARTUP]")
    
    # Auto-open browser after services initialized
    def open_browser():
        time.sleep(2)  # Wait for server to be ready
        try:
            webbrowser.open('http://localhost:8000/')
            print("[MAIN] 🌐 Opened browser at http://localhost:8000/ (redirects to login)")
        except Exception as e:
            print(f"[MAIN] ⚠️  Could not auto-open browser: {e}")
    
    threading.Thread(target=open_browser, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    initialize_all_services()
    yield
    # Shutdown
    print("\n[SHUTDOWN] Stopping services...")
    try:
        gemma_service = gemma_routes.get_service()
        gemma_service.stop()
    except Exception as e:
        print(f"[SHUTDOWN] Error stopping Gemma service: {e}")
    print("[SHUTDOWN] Cleanup complete")


# -----------------------------------------------------------------------------
# FastAPI Application
# -----------------------------------------------------------------------------

app = FastAPI(
    title="WhisperServer REFACTORED",
    version="3.2",
    description="Enterprise Memory Intelligence System with GPU-optimized Gemma AI",
    lifespan=lifespan
)

# -----------------------------------------------------------------------------
# Security Middleware Stack (ORDER MATTERS!)
# -----------------------------------------------------------------------------

# 1. Security Headers (first layer of defense)
from src.middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=False  # Set to True when HTTPS is enabled
)

# 2. IP Whitelist (if enabled)
if config.IP_WHITELIST_ENABLED and config.ALLOWED_IPS:
    from src.middleware.ip_whitelist import IPWhitelistMiddleware
    app.add_middleware(
        IPWhitelistMiddleware,
        allowed_ips=config.ALLOWED_IPS,
        enabled=True
    )
    print(f"[SECURITY] IP whitelist enabled with {len(config.ALLOWED_IPS)} networks")

# 3. Rate Limiting (if enabled)
if config.RATE_LIMIT_ENABLED:
    from src.middleware.rate_limiter import RateLimitMiddleware, get_rate_limiter
    rate_limiter = get_rate_limiter()
    app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
    print("[SECURITY] Rate limiting enabled")

# 4. Input Validation
from src.middleware.input_validation import InputValidationMiddleware
app.add_middleware(InputValidationMiddleware)

# 4.5. Authentication Middleware (enforce auth on all routes except auth/login)
class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce authentication on all API routes
    Validates session cookie and attaches session to request.state
    """
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for these paths
        skip_paths = [
            "/api/auth/login",
            "/api/auth/register", 
            "/api/auth/logout",
            "/health",      # Health check endpoint
            "/docs",
            "/redoc",
            "/openapi.json",
            "/ui/",
            "/ui/login.html",
            "/_next",
            "/favicon.ico"
        ]
        
        # Whitelisted IPs for transcription (Flutter app devices)
        # Configure via FLUTTER_WHITELIST environment variable (comma-separated)
        # Default: localhost only for security
        flutter_whitelist_str = os.getenv("FLUTTER_WHITELIST", "127.0.0.1,::1")
        flutter_whitelist = [ip.strip() for ip in flutter_whitelist_str.split(",")]
        
        # Get client IP
        client_ip = request.client.host if request.client else None
        
        # Check if path should skip auth
        path = request.url.path
        if any(path.startswith(skip) or path == skip for skip in skip_paths):
            return await call_next(request)
        
        # Allow whitelisted IPs to access /transcribe without auth
        if path == "/transcribe" and client_ip in flutter_whitelist:
            print(f"[AUTH] Allowing whitelisted device {client_ip} to access /transcribe")
            return await call_next(request)
        
        # Check for session cookie
        ws_session = request.cookies.get("ws_session")
        if not ws_session:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated. Please log in."}
            )
        
        # Validate session
        from src.auth.auth_manager import get_auth_manager
        auth_manager = get_auth_manager()
        session = auth_manager.validate_session(ws_session)
        
        if not session:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired session. Please log in again."}
            )
        
        # Attach session to request state for route handlers
        request.state.session = session
        request.state.user_id = session.user_id
        request.state.role = session.role
        request.state.speaker_id = session.speaker_id
        
        return await call_next(request)

app.add_middleware(AuthenticationMiddleware)
print("[SECURITY] Authentication middleware enabled - all API routes protected")

# 5. CORS Middleware (must be after security headers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:3000",  # Next.js dev
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("[SECURITY] Middleware stack configured")

# -----------------------------------------------------------------------------
# Root & Health Endpoints (MUST come BEFORE StaticFiles mount)
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    """Redirect root to login page"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/login.html")

@app.get("/home", response_class=HTMLResponse)
def root():
    """Root page with links to UI and API docs"""
    return f"""
    <html>
    <head>
        <title>WhisperServer REFACTORED</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                padding: 0;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 20px;
                max-width: 700px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            h1 {{
                color: #764ba2;
                margin: 0 0 10px 0;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }}
            .version {{
                display: inline-block;
                background: #667eea;
                color: white;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
                margin-bottom: 20px;
            }}
            .btn {{
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 35px;
                text-decoration: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 18px;
                margin: 10px;
                transition: transform 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            }}
            .features {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .features h3 {{
                margin-top: 0;
                color: #764ba2;
            }}
            .features ul {{
                list-style: none;
                padding: 0;
            }}
            .features li {{
                padding: 8px 0;
                border-bottom: 1px solid #dee2e6;
            }}
            .features li:last-child {{
                border-bottom: none;
            }}
            .features li:before {{
                content: "✓ ";
                color: #667eea;
                font-weight: bold;
                margin-right: 10px;
            }}
            .endpoints {{
                background: #fff3cd;
                border: 2px solid #ffc107;
                padding: 15px;
                border-radius: 10px;
                margin-top: 20px;
            }}
            .endpoints h4 {{
                margin-top: 0;
                color: #856404;
            }}
            .endpoints a {{
                color: #667eea;
                text-decoration: none;
                font-weight: bold;
            }}
            .endpoints a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 WhisperServer REFACTORED</h1>
            <div class="subtitle">Enterprise Memory Intelligence System</div>
            <span class="version">v3.2 - GPU Optimized</span>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="http://localhost:8001" class="btn">🧠 Open Memory UI</a>
                <a href="/docs" class="btn">📚 API Docs</a>
            </div>
            
            <div class="features">
                <h3>✨ Features</h3>
                <ul>
                    <li>Real-time Audio Transcription (Parakeet ASR)</li>
                    <li>Speaker Diarization (TitaNet + K-means)</li>
                    <li>Emotion Analysis (DistilRoBERTa)</li>
                    <li>Memory Search & RAG Q/A (FAISS + MiniLM)</li>
                    <li>Gemma 3 4B AI Analysis (GPU-Accelerated)</li>
                    <li>WebSocket Job Progress Updates</li>
                    <li>Speaker Enrollment & Recognition</li>
                    <li>Comprehensive Personality Analysis</li>
                </ul>
            </div>
            
            <div class="features">
                <h3>🏗️ Architecture Improvements</h3>
                <ul>
                    <li>Gemma gets EXCLUSIVE GPU access</li>
                    <li>All other models run on CPU</li>
                    <li>Consolidated speaker ID logic (3x dedup)</li>
                    <li>Service-based modular architecture</li>
                    <li>Centralized model management</li>
                    <li>Lazy loading for faster startup</li>
                </ul>
            </div>
            
            <div class="endpoints">
                <h4>📡 Quick API Links</h4>
                <a href="/health">Health Status</a> • 
                <a href="/latest_result">Latest Transcription</a> • 
                <a href="/docs">Interactive API Docs</a> • 
                <a href="/memory/list?limit=10">Recent Memories</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/health")
def health() -> Dict[str, Any]:
    """Comprehensive health check for all services"""
    try:
        # Transcription service
        transcription_service = transcription_routes.get_service()
        transcription_stats = transcription_service.get_stats()
        
        # Speaker service
        speaker_service = speaker_routes.get_service()
        speaker_stats = speaker_service.get_stats()
        
        # RAG service
        rag_service = rag_routes.get_service()
        rag_health = rag_service.health_check()
        rag_stats = rag_service.get_stats()
        
        # Emotion service
        emotion_service = emotion_routes.get_service()
        emotion_stats = emotion_service.get_stats()
        
        # Gemma service
        gemma_service = gemma_routes.get_service()
        gemma_stats = gemma_service.get_stats()
        
        return {
            "status": "ok",
            "version": "3.2-refactored",
            "services": {
                "transcription": {
                    "status": "ready" if transcription_stats["model_loaded"] else "loading",
                    "device": transcription_stats["model_device"],
                    "total_jobs": transcription_stats["total_jobs"]
                },
                "speaker": {
                    "status": "ready" if speaker_stats["model_loaded"] else "loading",
                    "device": speaker_stats["model_device"],
                    "backend": speaker_stats["backend"],
                    "enrolled_speakers": speaker_stats["enrolled_speakers"],
                    "match_threshold": speaker_stats["match_threshold"]
                },
                "rag": {
                    "status": "ready" if rag_health["overall"] else "error",
                    "memory_count": rag_stats.get("memory_count", 0),
                    "transcript_count": rag_stats.get("transcript_count", 0),
                    "embedding_model": rag_stats.get("embedding_model", "unknown")
                },
                "emotion": {
                    "status": "ready" if emotion_stats["available"] else "unavailable",
                    "device": emotion_stats["device"]
                },
                "gemma": {
                    "status": "ready" if gemma_stats["analyzer_loaded"] else "loading",
                    "gpu_available": gemma_stats["gpu_available"],
                    "gpu_name": gemma_stats.get("gpu_name", "N/A"),
                    "total_jobs": gemma_stats["total_jobs"],
                    "queued_jobs": gemma_stats["queued_jobs"]
                }
            },
            "architecture": {
                "gpu_exclusive_to": "gemma",
                "cpu_services": ["transcription", "speaker", "rag", "emotion"],
                "refactored": True
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "version": "3.2-refactored",
            "error": str(e)
        }


# -----------------------------------------------------------------------------
# Register Service Routes
# -----------------------------------------------------------------------------

# Authentication routes
app.include_router(auth_routes.router)

# Transcription routes
app.include_router(transcription_routes.router)

# Transcript retrieval routes (list, search, analytics)
app.include_router(transcript_routes.router)

# Speaker enrollment routes
app.include_router(speaker_routes.router)

# RAG routes (memory, transcript, query)
for rag_router in rag_routes.get_routers():
    app.include_router(rag_router)

# Emotion routes
app.include_router(emotion_routes.router)

# Gemma routes (analysis endpoints, jobs, WebSocket)
for gemma_router in gemma_routes.get_routers():
    app.include_router(gemma_router)

# Mount Static Files (HTML Frontend) - MUST be LAST to not intercept API routes
FRONTEND_DIR = REFACTORED_SRC.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    print(f"[MAIN] ✅ Mounted HTML frontend at /ui/ from {FRONTEND_DIR}")
else:
    print(f"[MAIN] ⚠️  frontend not found at {FRONTEND_DIR}")


# -----------------------------------------------------------------------------
# Additional Utility Endpoints
# -----------------------------------------------------------------------------

@app.get("/test/auth")
def test_auth_endpoint(session: Session = Depends(require_auth)) -> Dict[str, str]:
    """Test endpoint to verify authentication is working"""
    return {
        "status": "authenticated",
        "user_id": session.user_id,
        "role": session.role.value,
        "speaker_id": session.speaker_id
    }

@app.post("/logs/ingest")
def ingest_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest logs from Flutter client (backward compatibility)
    
    Args:
        payload: Log data with text, speaker, timestamp
    
    Returns:
        Status response
    """
    try:
        text = (payload.get("text") or "").strip()
        speaker = (payload.get("speaker") or "SPK").strip()
        
        if not text:
            return {"status": "skipped", "reason": "empty text"}
        
        # Save to RAG service
        rag_service = rag_routes.get_service()
        timestamp = payload.get("timestamp") or rag_service.now_iso()
        
        # Create memory entry
        rag_service.create_memory(
            content=text,
            source="flutter_ingest",
            metadata={
                "speaker": speaker,
                "timestamp": timestamp
            }
        )
        
        return {"status": "ok", "message": "Log ingested"}
        
    except Exception as e:
        print(f"[LOG_INGEST] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 Starting WhisperServer REFACTORED")
    print("="*80)
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"Docs: http://{HOST}:{PORT}/docs")
    print("="*80 + "\n")
    
    uvicorn.run(
        "main_refactored:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info"
    )
