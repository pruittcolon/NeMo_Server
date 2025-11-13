"""
GPU Coordinator Service
FastAPI application for managing GPU ownership
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import sys

from .gpu_lock_manager import get_lock_manager, GPUState
from .gpu_monitor import get_gpu_monitor
from .task_persistence import get_task_persistence

# Add shared modules to path
sys.path.insert(0, '/app')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Build Postgres URL from secrets or env (Phase 5)
def get_postgres_url() -> str:
    """Build Postgres connection string from secrets or environment"""
    from shared.security.secrets import get_secret
    pg_user = get_secret("postgres_user", default="postgres")
    pg_password = get_secret("postgres_password", default="postgres")
    pg_host = os.getenv("POSTGRES_HOST", "postgres")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "nemo_queue")
    url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    logger.info(f"📊 Postgres URL built: postgresql://{pg_user}:***@{pg_host}:{pg_port}/{pg_db}")
    return url

POSTGRES_URL = get_postgres_url()
JWT_ONLY = os.getenv("JWT_ONLY", "false").lower() in {"1", "true", "yes"}

# Global auth
service_auth = None


# Request/Response models
class GemmaTaskRequest(BaseModel):
    """Gemma task request"""
    task_id: str
    messages: list
    max_tokens: int = 512
    temperature: float = 0.7
    context: list = []


class GemmaTaskResponse(BaseModel):
    """Gemma task response"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    status: str
    result: Dict[str, Any] = None
    error: str = None


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT service authentication (Phase 3: Enforce JWT-only + replay)."""
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks
        if request.url.path == "/health":
            return await call_next(request)

        jwt_token = request.headers.get("X-Service-Token")
        if not jwt_token or not service_auth:
            logger.error(f"❌ Missing JWT for {request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Missing service token"})

        try:
            # Allowed callers: gateway, gemma-service
            allowed = ["gateway", "gemma-service"]
            payload = service_auth.verify_token(jwt_token, allowed_services=allowed, expected_aud="internal")

            # Replay protection
            from shared.security.service_auth import get_replay_protector
            import time as _t
            ttl = max(10, int(payload["expires_at"] - _t.time()) + 10)
            ok, reason = get_replay_protector().check_and_store(payload.get("request_id", ""), ttl)
            if not ok:
                logger.error(f"❌ JWT replay blocked: reason={reason}")
                return JSONResponse(status_code=401, content={"detail": "Replay detected"})

            rid_short = str(payload.get('request_id',''))[:8]
            logger.info(f"✅ JWT OK s={payload.get('service_id')} aud=internal rid={rid_short} path={request.url.path}")
            return await call_next(request)
        except Exception as e:
            logger.error(f"❌ JWT rejected: {e} path={request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Invalid service token"})


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    # Startup
    logger.info("Starting GPU Coordinator Service...")
    
    # Initialize service auth (Phase 3)
    global service_auth
    try:
        from shared.security.service_auth import get_service_auth, load_service_jwt_keys
        jwt_keys = load_service_jwt_keys("queue-service")
        service_auth = get_service_auth(service_id="queue-service", service_secret=jwt_keys)
        logger.info(
            "✅ JWT service auth initialized (enforcing JWT-only, aud=internal, replay protected, keys=%s)",
            len(jwt_keys),
        )
    except Exception as e:
        logger.error(f"❌ JWT service auth initialization failed: {e}")
        raise
    
    # Connect to Redis
    lock_manager = get_lock_manager()
    lock_manager.redis_url = REDIS_URL
    await lock_manager.connect()
    
    # Connect to PostgreSQL
    persistence = get_task_persistence()
    persistence.db_url = POSTGRES_URL
    await persistence.connect()
    
    # Recover any pending tasks from crash
    if persistence.enabled:
        pending_tasks = await persistence.get_pending_tasks()
        if pending_tasks:
            logger.info(f"Found {len(pending_tasks)} pending tasks from previous session")
            # These will be processed by Gemma service on startup
    
    logger.info("GPU Coordinator Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down GPU Coordinator Service...")
    await lock_manager.disconnect()
    await persistence.disconnect()
    logger.info("GPU Coordinator Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="GPU Coordinator Service",
    description="Manages GPU ownership between Transcription and Gemma",
    version="1.0.0",
    lifespan=lifespan
)

# Add JWT middleware (Phase 2: Permissive)
app.add_middleware(ServiceAuthMiddleware)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    lock_manager = get_lock_manager()
    persistence = get_task_persistence()
    gpu_monitor = get_gpu_monitor()
    
    return {
        "status": "healthy",
        "redis_connected": lock_manager.redis_client is not None,
        "postgres_connected": persistence.enabled,
        "gpu_monitor_available": gpu_monitor.available,
        "current_state": lock_manager.state.value
    }


@app.get("/status")
async def get_status():
    """Get current GPU coordinator status"""
    lock_manager = get_lock_manager()
    gpu_monitor = get_gpu_monitor()
    persistence = get_task_persistence()
    
    gpu_status = gpu_monitor.get_full_status()
    lock_status = await lock_manager.get_status()
    
    task_stats = {}
    if persistence.enabled:
        task_stats = await persistence.get_task_stats()
    
    return {
        "lock_status": lock_status,
        "gpu_status": gpu_status,
        "task_stats": task_stats
    }


@app.post("/gemma/request", response_model=GemmaTaskResponse)
async def request_gpu_for_gemma(request: GemmaTaskRequest):
    """
    Request GPU for Gemma task (immediate priority)
    
    This endpoint:
    1. Adds task to PostgreSQL for persistence
    2. Signals transcription to pause
    3. Waits for pause acknowledgment
    4. Returns success (Gemma service will then execute)
    """
    lock_manager = get_lock_manager()
    persistence = get_task_persistence()
    
    # Add task to persistence
    if persistence.enabled:
        await persistence.add_task(
            task_id=request.task_id,
            payload=request.dict()
        )
    
    # Request GPU
    success = await lock_manager.request_gpu_for_gemma(
        task_id=request.task_id,
        task_data=request.dict()
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to acquire GPU")
    
    # Mark as running
    if persistence.enabled:
        await persistence.mark_running(request.task_id)
    
    return GemmaTaskResponse(
        task_id=request.task_id,
        status="gpu_acquired",
        message="GPU acquired, ready for execution"
    )


@app.post("/gemma/release/{task_id}")
async def release_gpu_from_gemma(task_id: str, result: Dict[str, Any] = None):
    """
    Release GPU after Gemma completes
    
    Args:
        task_id: Task identifier
        result: Optional task result
    """
    lock_manager = get_lock_manager()
    persistence = get_task_persistence()
    
    # Release GPU
    await lock_manager.release_gpu_from_gemma(task_id, result)
    
    # Mark as completed
    if persistence.enabled:
        if result and result.get("error"):
            await persistence.mark_failed(task_id, result["error"])
        else:
            await persistence.mark_completed(task_id, result)
    
    return {"status": "released", "task_id": task_id}


@app.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get task status
    
    Args:
        task_id: Task identifier
    """
    persistence = get_task_persistence()
    
    if not persistence.enabled:
        raise HTTPException(status_code=503, detail="Task persistence not available")
    
    task = await persistence.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        result=task.get("result"),
        error=task.get("error")
    )


@app.get("/tasks/pending")
async def get_pending_tasks():
    """Get all pending tasks"""
    persistence = get_task_persistence()
    
    if not persistence.enabled:
        return {"tasks": []}
    
    tasks = await persistence.get_pending_tasks()
    return {"tasks": tasks, "count": len(tasks)}


@app.post("/admin/force-reset")
async def force_reset_gpu():
    """
    Force reset GPU to transcription (emergency recovery)
    Use with caution!
    """
    lock_manager = get_lock_manager()
    await lock_manager.force_reset()
    
    return {"status": "reset", "message": "GPU forcefully returned to transcription"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=False
    )





