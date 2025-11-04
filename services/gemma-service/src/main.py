"""
Gemma AI Service - GPU Coordinator Integration
Handles LLM inference with dynamic GPU access via coordinator
"""
import os
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from llama_cpp import Llama
import httpx
import sys

# Add shared modules to path
sys.path.insert(0, '/app')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
GEMMA_MODEL_PATH = os.getenv("GEMMA_MODEL_PATH", "/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf")
GEMMA_GPU_LAYERS = int(os.getenv("GEMMA_GPU_LAYERS", "25"))  # Increased for 64k context
GEMMA_CONTEXT_SIZE = int(os.getenv("GEMMA_CONTEXT_SIZE", "65536"))  # 64k context
GEMMA_BATCH_SIZE = int(os.getenv("GEMMA_BATCH_SIZE", "512"))
JWT_ONLY = os.getenv("JWT_ONLY", "false").lower() in {"1", "true", "yes"}
GPU_COORDINATOR_URL = os.getenv("GPU_COORDINATOR_URL", "http://gpu-coordinator:8002")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:8004")

# Global model instance
gemma_model: Optional[Llama] = None
model_on_gpu: bool = False
service_auth = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_service_headers(expires_in: int = 60) -> Dict[str, str]:
    """Get service authentication headers (JWT only)."""
    if not service_auth:
        raise RuntimeError("Service authentication not initialized")
    try:
        token = service_auth.create_token(expires_in=expires_in)
        return {"X-Service-Token": token}
    except Exception as exc:
        logger.error(f"[GEMMA] Failed to create service JWT: {exc}")
        raise


# ============================================================================
# MODEL MANAGEMENT
# ============================================================================

def load_model_cpu():
    """Load model on CPU/RAM - ready for GPU transfer"""
    global gemma_model, model_on_gpu
    
    logger.info(f"[GEMMA] Loading model from: {GEMMA_MODEL_PATH}")
    logger.info(f"[GEMMA] Mode: CPU (n_gpu_layers=0)")
    logger.info(f"[GEMMA] Context size: {GEMMA_CONTEXT_SIZE} tokens")
    
    if not Path(GEMMA_MODEL_PATH).exists():
        raise RuntimeError(f"Model file not found: {GEMMA_MODEL_PATH}")
    
    try:
        gemma_model = Llama(
            model_path=GEMMA_MODEL_PATH,
            n_ctx=GEMMA_CONTEXT_SIZE,
            n_batch=GEMMA_BATCH_SIZE,
            n_gpu_layers=0,  # CPU mode
            n_threads=4,
            verbose=False,
        )
        model_on_gpu = False
        logger.info("[GEMMA] Model loaded on CPU/RAM successfully!")
        
    except Exception as e:
        logger.error(f"[GEMMA] ERROR loading model: {e}")
        raise


def load_model_gpu():
    """Load model directly on GPU at startup"""
    global gemma_model, model_on_gpu
    
    logger.info(f"[GEMMA] Loading model from: {GEMMA_MODEL_PATH}")
    logger.info(f"[GEMMA] Mode: GPU (n_gpu_layers={GEMMA_GPU_LAYERS})")
    logger.info(f"[GEMMA] Context size: {GEMMA_CONTEXT_SIZE} tokens")
    
    if not Path(GEMMA_MODEL_PATH).exists():
        raise RuntimeError(f"Model file not found: {GEMMA_MODEL_PATH}")
    
    gemma_model = Llama(
        model_path=GEMMA_MODEL_PATH,
        n_ctx=GEMMA_CONTEXT_SIZE,
        n_batch=GEMMA_BATCH_SIZE,
        n_gpu_layers=GEMMA_GPU_LAYERS,  # GPU mode
        n_threads=2,
        verbose=False,
    )
    model_on_gpu = True
    logger.info("[GEMMA] Model loaded on GPU successfully!")
    
    # Log VRAM usage
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            vram_used = result.stdout.strip().split('\n')[0]
            logger.info(f"[GEMMA] VRAM used: {vram_used} MB")
    except Exception as e:
        logger.warning(f"[GEMMA] Could not query VRAM: {e}")


def move_model_to_gpu():
    """Move model from CPU to GPU for fast inference"""
    global gemma_model, model_on_gpu
    
    if model_on_gpu:
        logger.info("[GEMMA] Model already on GPU")
        return
    
    logger.info("[GEMMA] 🚀 Moving model from CPU to GPU for fast inference...")
    
    # Save reference to old model in case we need to restore
    old_model = gemma_model
    
    try:
        # Delete CPU model to free RAM
        del gemma_model
        gemma_model = None
        
        # Reload on GPU
        load_model_gpu()
        
        logger.info("[GEMMA] ✅ Model moved to GPU successfully")
        
    except Exception as e:
        logger.error(f"[GEMMA] ❌ ERROR moving to GPU: {e}")
        logger.info("[GEMMA] Keeping model on CPU...")
        # Restore old model or reload on CPU
        if old_model is not None:
            gemma_model = old_model
            model_on_gpu = False
        else:
            load_model_cpu()
        raise


def move_model_to_cpu():
    """Move model from GPU back to CPU to free VRAM"""
    global gemma_model, model_on_gpu
    
    if not model_on_gpu:
        logger.info("[GEMMA] Model already on CPU")
        return
    
    logger.info("[GEMMA] 💾 Moving model from GPU back to CPU to free VRAM...")
    
    try:
        # Delete GPU model to free VRAM
        del gemma_model
        
        # Reload on CPU (background mode)
        load_model_cpu()
        
        logger.info("[GEMMA] ✅ Model moved back to CPU successfully")
        
    except Exception as e:
        logger.error(f"[GEMMA] ❌ ERROR moving to CPU: {e}")
        raise


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
            # Allowed callers: gateway, transcription-service (signals)
            allowed = ["gateway", "transcription-service"]
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


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    # Startup
    logger.info("Starting Gemma AI Service...")
    logger.info("=" * 80)
    
    # Initialize service auth (Phase 3)
    global service_auth
    try:
        from shared.security.secrets import get_secret
        from shared.security.service_auth import get_service_auth
        jwt_secret = get_secret("jwt_secret", default="dev_jwt_secret")
        if jwt_secret:
            service_auth = get_service_auth(service_id="gemma-service", service_secret=jwt_secret)
            logger.info("✅ JWT service auth initialized (enforcing JWT-only, aud=internal, replay protected)")
    except Exception as e:
        logger.error(f"❌ JWT service auth initialization failed: {e}")
        raise
    
    # START ON CPU (lightweight, waits in background)
    # User will call /warmup to move to GPU before inference
    logger.info("[GEMMA] � Loading on CPU (background mode)...")
    logger.info("[GEMMA] Call /warmup endpoint to move to GPU for fast inference")
    load_model_cpu()
    logger.info("[GEMMA] ✅ Loaded on CPU successfully!")
    logger.info("Gemma AI Service started successfully (CPU background mode)")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Gemma AI Service...")
    global gemma_model
    if gemma_model:
        del gemma_model
    logger.info("Gemma AI Service shutdown complete")


# Initialize FastAPI
app = FastAPI(
    title="Gemma AI Service",
    description="LLM inference service with dynamic GPU access",
    version="1.0.0",
    lifespan=lifespan
)

# Add JWT middleware (Phase 2: Permissive)
app.add_middleware(ServiceAuthMiddleware)

# ============================================================================
# REQUEST MODELS
# ============================================================================

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stop: Optional[List[str]] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    context: Optional[List[Dict[str, Any]]] = None
    stop: Optional[List[str]] = None


class RAGChatRequest(BaseModel):
    """RAG-enhanced chat request"""
    query: str
    max_tokens: int = 500
    temperature: float = 0.7
    top_p: float = 0.9
    session_id: Optional[str] = None
    top_k_results: int = 8
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_n_transcripts: Optional[int] = None
    speakers: Optional[List[str]] = None
    bias_emotions: Optional[List[str]] = None
    use_memories: bool = False
    include_memories_top_k: int = 3

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    status = {
        "status": "healthy" if gemma_model is not None else "unhealthy",
        "model_loaded": gemma_model is not None,
        "model_on_gpu": model_on_gpu,
        "model_path": GEMMA_MODEL_PATH,
        "gpu_layers": GEMMA_GPU_LAYERS,
        "context_size": GEMMA_CONTEXT_SIZE,
    }
    
    # Try to get VRAM usage
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            vram_info = result.stdout.strip().split('\n')[0].split(',')
            status["vram_used_mb"] = int(vram_info[0].strip())
            status["vram_total_mb"] = int(vram_info[1].strip())
    except:
        pass
    
    return status


@app.post("/move-to-cpu")
async def move_to_cpu_endpoint():
    """Move model from GPU to CPU (called when other services start)"""
    global model_on_gpu
    
    if not model_on_gpu:
        return {"status": "already_on_cpu", "message": "Model is already on CPU"}
    
    logger.info("[GEMMA] 📡 Received signal to move to CPU (other services starting)")
    
    try:
        move_model_to_cpu()
        return {
            "status": "success",
            "message": "Model moved to CPU, GPU freed for transcription",
            "model_on_gpu": False
        }
    except Exception as e:
        logger.error(f"[GEMMA] Failed to move to CPU: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/warmup")
async def warmup_gpu():
    """
    Warmup endpoint - moves model to GPU and waits until ready
    Call this BEFORE sending your actual generate request
    """
    global model_on_gpu, gemma_model
    
    if gemma_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    logger.info("[GEMMA] 🔥 Warmup requested - preparing GPU...")
    task_id = f"gemma-warmup-{uuid.uuid4().hex[:8]}"
    gpu_acquired = False
    response_payload: Optional[Dict[str, Any]] = None
    release_payload: Optional[Dict[str, Any]] = None
    
    try:
        logger.info(f"📡 [WARMUP] Requesting GPU slot from coordinator (task={task_id})...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            coord_response = await client.post(
                f"{GPU_COORDINATOR_URL}/gemma/request",
                json={
                    "task_id": task_id,
                    "messages": [{"role": "system", "content": "warmup"}],
                    "max_tokens": 1,
                    "temperature": 0.7
                },
                headers=get_service_headers()
            )
            if coord_response.status_code != 200:
                logger.error(f"❌ [WARMUP] Failed to acquire GPU slot (status {coord_response.status_code})")
                raise HTTPException(status_code=503, detail="Failed to acquire GPU slot")
        gpu_acquired = True
        
        if not model_on_gpu:
            logger.info("[GEMMA] 🚀 Attempting to move model to GPU for warmup...")
            try:
                move_model_to_gpu()
                logger.info("[GEMMA] ✅ Model ready on GPU!")
                response_payload = {
                    "status": "ready",
                    "message": "Model warmed up and ready on GPU",
                    "model_on_gpu": True,
                    "task_id": task_id
                }
                release_payload = {"result": {"status": "warmup", "model_on_gpu": True}}
            except Exception as gpu_error:
                logger.warning(f"[GEMMA] ⚠️ Could not move to GPU: {gpu_error}")
                logger.info("[GEMMA] 💾 GPU load failed - continuing on CPU")
                response_payload = {
                    "status": "ready_cpu",
                    "message": "Model ready on CPU (GPU unavailable)",
                    "model_on_gpu": False,
                    "task_id": task_id,
                    "warning": "Using CPU - inference will be slower"
                }
                release_payload = {"result": {"status": "warmup_cpu", "warning": str(gpu_error)}}
        else:
            logger.info("[GEMMA] ✅ Model already on GPU!")
            response_payload = {
                "status": "ready",
                "message": "Model already on GPU",
                "model_on_gpu": True,
                "task_id": task_id
            }
            release_payload = {"result": {"status": "warmup_cached", "model_on_gpu": True}}
    except HTTPException:
        release_payload = {"result": {"error": "warmup_failed_before_acquire"}}
        raise
    except Exception as e:
        release_payload = {"result": {"error": str(e)}}
        raise
    finally:
        if gpu_acquired:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                        json=release_payload or {"result": {"status": "warmup_unknown"}},
                        headers=get_service_headers()
                    )
                logger.info("[GEMMA] ✅ Released GPU slot, transcription can resume")
            except Exception as release_error:
                logger.error(f"[GEMMA] ❌ Failed to release GPU slot: {release_error}")
    
    return response_payload


@app.post("/generate")
async def generate_text(
    request: GenerateRequest
):
    """
    Generate text from prompt
    Uses GPU coordinator for exclusive GPU access
    """
    if gemma_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    task_id = f"gemma-gen-{uuid.uuid4().hex[:12]}"
    
    logger.info("=" * 80)
    logger.info(f"🔄 [GENERATE] Task {task_id} started")
    logger.info(f"🔄 [GENERATE] Prompt: {request.prompt[:100]}...")
    logger.info(f"🔄 [GENERATE] Max tokens: {request.max_tokens}, Temp: {request.temperature}")
    
    gpu_slot_acquired = False
    try:
        # Request GPU from coordinator
        logger.info(f"📡 [TASK {task_id}] Requesting GPU slot from coordinator...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            coord_response = await client.post(
                f"{GPU_COORDINATOR_URL}/gemma/request",
                json={
                    "task_id": task_id,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature
                },
                headers=get_service_headers()
            )
            
            if coord_response.status_code != 200:
                logger.error(f"❌ [TASK {task_id}] Failed to acquire GPU slot: {coord_response.status_code}")
                raise HTTPException(status_code=503, detail="Failed to acquire GPU slot from coordinator")
            
            logger.info(f"✅ [TASK {task_id}] GPU slot acquired")
        gpu_slot_acquired = True
        
        # Model should already be on GPU from warmup call
        # If not, move it now (but this will be slower)
        using_cpu_fallback = False
        if not model_on_gpu:
            logger.warning(f"⚠️ [TASK {task_id}] Model not on GPU! Did you forget to call /warmup first?")
            try:
                move_model_to_gpu()
                logger.info(f"🚀 [TASK {task_id}] Moved to GPU, executing inference...")
            except Exception as gpu_error:
                logger.warning(f"⚠️ [TASK {task_id}] GPU load failed, using CPU: {gpu_error}")
                logger.info(f"🐌 [TASK {task_id}] Executing inference on CPU (slow)...")
                using_cpu_fallback = True
                # Release GPU slot since we're using CPU
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                            json={"error": "GPU unavailable - using CPU"},
                            headers=get_service_headers()
                        )
                    logger.info(f"🔓 [TASK {task_id}] Released GPU slot (using CPU instead)")
                    gpu_slot_acquired = False
                except Exception as release_error:
                    logger.error(f"❌ Failed to release GPU slot: {release_error}")
        else:
            logger.info(f"🚀 [TASK {task_id}] Executing inference on GPU (already warmed up)...")
        
        # Execute inference
        response = gemma_model(
            request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=request.stop or [],
            echo=False,
        )
        
        result = {
            "text": response["choices"][0]["text"],
            "tokens_generated": response["usage"]["completion_tokens"],
            "task_id": task_id,
            "mode": "cpu" if using_cpu_fallback else "gpu"
        }
        
        logger.info(f"✅ [TASK {task_id}] Inference complete - Generated {result['tokens_generated']} tokens")
        logger.info(f"📝 [TASK {task_id}] Response preview: {result['text'][:200]}...")
        
        # Move model back to CPU to free VRAM for transcription
        try:
            move_model_to_cpu()
            logger.info(f"💾 [TASK {task_id}] Model back to CPU, VRAM freed")
        except Exception as cpu_error:
            logger.warning(f"⚠️ [TASK {task_id}] Failed to move back to CPU: {cpu_error}")
        
        # Release GPU slot back to coordinator (only if we acquired it)
        if not using_cpu_fallback:
            logger.info(f"🔓 [TASK {task_id}] Releasing GPU slot...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                    json={"result": result},
                headers=get_service_headers()
            )
            logger.info(f"✅ [TASK {task_id}] GPU slot released, model in CPU background mode")
            gpu_slot_acquired = False
        else:
            logger.info(f"✅ [TASK {task_id}] Complete (GPU slot already released, used CPU)")

        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"❌ [TASK {task_id}] Error: {e}")
        logger.error("=" * 80)
        
        # Release GPU on error
        try:
            if gpu_slot_acquired:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                        json={"result": {"error": str(e)}},
                        headers=get_service_headers()
                    )
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat(
    request: ChatRequest
):
    """
    Chat with conversation history
    Uses GPU coordinator for exclusive GPU access
    """
    if gemma_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    task_id = f"gemma-chat-{uuid.uuid4().hex[:12]}"
    
    logger.info("=" * 80)
    logger.info(f"💬 [CHAT] Task {task_id} started")
    logger.info(f"💬 [CHAT] Messages: {len(request.messages)}, Max tokens: {request.max_tokens}")
    
    try:
        # Request GPU from coordinator
        logger.info(f"📡 [TASK {task_id}] Requesting GPU slot from coordinator...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            coord_response = await client.post(
                f"{GPU_COORDINATOR_URL}/gemma/request",
                json={
                    "task_id": task_id,
                    "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "context": request.context or []
                },
                headers=get_service_headers()
            )
            
            if coord_response.status_code != 200:
                logger.error(f"❌ [TASK {task_id}] Failed to acquire GPU slot: {coord_response.status_code}")
                raise HTTPException(status_code=503, detail="Failed to acquire GPU slot from coordinator")
            
            logger.info(f"✅ [TASK {task_id}] GPU slot acquired")
        gpu_slot_acquired = True
        gpu_slot_released = False
        
        if not model_on_gpu:
            logger.info(f"[TASK {task_id}] Model not on GPU – attempting warm transfer")
            try:
                move_model_to_gpu()
                logger.info(f"[TASK {task_id}] Model successfully moved to GPU")
            except Exception as gpu_error:
                logger.warning(f"⚠️ [TASK {task_id}] Failed to move model to GPU: {gpu_error}")
                logger.info(f"⚠️ [TASK {task_id}] Releasing GPU slot and falling back to CPU mode")
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                            json={"result": {"warning": str(gpu_error), "mode": "cpu"}},
                headers=get_service_headers()
                        )
                    gpu_slot_acquired = False
                    gpu_slot_released = True
                except Exception as release_error:
                    logger.error(f"❌ [TASK {task_id}] Failed to release GPU slot after move failure: {release_error}")

        # Build prompt from messages
        prompt = ""
        
        # Add context if provided
        if request.context:
            prompt += "Context from memories:\n"
            for ctx in request.context[:3]:  # Top 3 memories
                prompt += f"- {ctx.get('content', '')[:200]}\n"
            prompt += "\n"
        
        # Add conversation history
        for msg in request.messages:
            role = msg.role.upper()
            prompt += f"{role}: {msg.content}\n"
        
        prompt += "ASSISTANT: "
        
        logger.info(f"[TASK {task_id}] Executing inference...")
        
        # Execute inference on GPU
        llama_kwargs = {
            "prompt": prompt,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "echo": False,
        }

        if request.stop:
            llama_kwargs["stop"] = request.stop

        response = gemma_model(**llama_kwargs)
        
        generated_text = response["choices"][0]["text"].strip()
        tokens_generated = response["usage"].get("completion_tokens", 0)

        if tokens_generated == 0:
            logger.warning(f"⚠️ [TASK {task_id}] Chat generated 0 tokens. Check stop tokens/prompt.")

        result = {
            "message": generated_text or "",
            "tokens_generated": tokens_generated,
            "task_id": task_id,
            "mode": "gpu" if model_on_gpu else "cpu"
        }
        
        logger.info(f"✅ [TASK {task_id}] Inference complete - Generated {result['tokens_generated']} tokens")
        logger.info(f"💬 [TASK {task_id}] Response: {result['message'][:200]}...")
        
        # Release GPU slot back to coordinator
        if gpu_slot_acquired and not gpu_slot_released:
            logger.info(f"🔓 [TASK {task_id}] Releasing GPU slot...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                    json={"result": result},
                headers=get_service_headers()
            )
            logger.info(f"✅ [TASK {task_id}] GPU slot released, model remains on GPU")
            gpu_slot_released = True
        logger.info("=" * 80)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [TASK {task_id}] Error: {e}")
        logger.error("=" * 80)
        
        # Release GPU on error if still held
        try:
            if gpu_slot_acquired and not gpu_slot_released:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                        json={"result": {"error": str(e)}},
                        headers=get_service_headers()
                    )
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/rag")
async def chat_with_rag(
    request: RAGChatRequest
):
    """
    RAG-enhanced chat: Retrieves relevant context from transcripts, then generates answer
    
    Flow:
    1. Search RAG service for relevant segments
    2. Build context prompt with results
    3. Generate answer with Gemma
    4. Return answer with sources
    """
    if gemma_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    task_id = f"gemma-rag-{uuid.uuid4().hex[:12]}"
    gpu_slot_acquired = False
    gpu_slot_released = False
    used_gpu = False

    def format_timestamp(seconds: Optional[float]) -> Optional[str]:
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return None
        minutes = int(value // 60)
        secs = int(value % 60)
        return f"{minutes:02d}:{secs:02d}"

    async def fetch_rag_results(doc_type: str, top_k: int) -> List[Dict[str, Any]]:
        payload = {
            "query": request.query,
            "top_k": top_k,
            "doc_type": doc_type,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "last_n_transcripts": request.last_n_transcripts,
            "speakers": request.speakers,
            "bias_emotions": request.bias_emotions,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{RAG_SERVICE_URL}/search/semantic",
                json=payload,
                headers=get_service_headers(),
            )
        if response.status_code != 200:
            logger.warning(f"[TASK {task_id}] RAG search {doc_type} failed: {response.status_code}")
            return []
        data = response.json()
        results = data.get("results", [])
        logger.info(f"[TASK {task_id}] Retrieved {len(results)} {doc_type} results")
        return results

    try:
        transcript_results = await fetch_rag_results("transcript_segment", request.top_k_results)
        memory_results: List[Dict[str, Any]] = []
        if request.use_memories:
            memory_results = await fetch_rag_results("memory", request.include_memories_top_k)

        if not transcript_results and not memory_results:
            logger.info(f"[TASK {task_id}] No RAG context found for query")
            return {
                "answer": "I couldn't find any conversation excerpts that answer that question within the selected scope.",
                "mode": "cpu" if not model_on_gpu else "gpu",
                "tokens_generated": 0,
                "confidence": 0.0,
                "sources": [],
                "task_id": task_id,
            }

        context_lines: List[str] = []
        sources: List[Dict[str, Any]] = []
        citation_index = 1

        def append_context(result_list: List[Dict[str, Any]], prefix: str = "C") -> None:
            nonlocal citation_index
            for result in result_list:
                metadata = result.get("metadata") or {}
                text = result.get("text") or ""
                label = f"{prefix}{citation_index}"

                if result.get("type") == "memory":
                    title = metadata.get("title") or "Memory"
                    context_lines.append(f"[{label}] Memory • {title}: \"{text}\"")
                    sources.append({
                        "label": label,
                        "type": "memory",
                        "title": title,
                        "text_preview": text[:180],
                        "score": result.get("score", 0.0),
                        "created_at": metadata.get("created_at"),
                        "memory_id": metadata.get("memory_id"),
                    })
                else:
                    speaker = metadata.get("speaker") or "Unknown speaker"
                    emotion = metadata.get("emotion") or "neutral"
                    timestamp_display = format_timestamp(metadata.get("start_time")) or "--:--"
                    context_lines.append(f"[{label}] {timestamp_display} • {speaker} ({emotion}): \"{text}\"")
                    sources.append({
                        "label": label,
                        "type": "transcript_segment",
                        "speaker": speaker,
                        "timestamp": timestamp_display,
                        "start_time": metadata.get("start_time"),
                        "end_time": metadata.get("end_time"),
                        "job_id": metadata.get("job_id"),
                        "transcript_id": metadata.get("transcript_id"),
                        "segment_id": metadata.get("segment_id"),
                        "emotion": emotion,
                        "score": result.get("score", 0.0),
                        "text_preview": text[:180],
                        "created_at": metadata.get("created_at"),
                    })
                citation_index += 1

        append_context(transcript_results[: request.top_k_results])
        if memory_results:
            append_context(memory_results[: request.include_memories_top_k], prefix="M")

        instruction = (
            "You are an assistant that answers questions using the provided conversation excerpts. "
            "Each excerpt has a label like [C1]. Use those labels in your answer as citations. "
            "If the excerpts do not contain the answer, say that you cannot find evidence."
        )
        context_block = "\n".join(context_lines)
        prompt = (
            f"{instruction}\n\n"
            f"Conversation excerpts:\n{context_block}\n\n"
            f"User question: {request.query}\n\n"
            "Answer:"
        )

        logger.info(f"[TASK {task_id}] Prompt prepared with {len(context_lines)} excerpts")

        # Acquire GPU slot
        logger.info(f"[TASK {task_id}] Requesting GPU access…")
        async with httpx.AsyncClient(timeout=30.0) as client:
            coord_response = await client.post(
                f"{GPU_COORDINATOR_URL}/gemma/request",
                json={
                    "task_id": task_id,
                    "messages": [{"role": "user", "content": request.query}],
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                },
                headers=get_service_headers()
            )
        if coord_response.status_code != 200:
            raise HTTPException(status_code=503, detail="Failed to acquire GPU")
        gpu_slot_acquired = True

        if not model_on_gpu:
            try:
                move_model_to_gpu()
                used_gpu = True
            except Exception as gpu_error:
                logger.warning(f"⚠️ [TASK {task_id}] Failed to move model to GPU: {gpu_error}. Falling back to CPU.")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                        json={"result": {"warning": str(gpu_error), "mode": "cpu"}},
                    headers=get_service_headers()
                    )
                gpu_slot_acquired = False
                gpu_slot_released = True
        else:
            used_gpu = True

        generation_kwargs = {
            "prompt": prompt,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "echo": False,
        }

        response = gemma_model(**generation_kwargs)
        answer_text = response["choices"][0]["text"].strip()
        tokens_generated = response["usage"].get("completion_tokens", 0)

        if tokens_generated == 0:
            logger.warning(f"⚠️ [TASK {task_id}] Generated 0 tokens; check prompt/stop settings")

        score_values = [res.get("score", 0.0) for res in transcript_results[:3] if isinstance(res, dict)]
        if score_values:
            avg_score = sum(score_values) / len(score_values)
            confidence = max(0.0, min(0.99, (avg_score + 1.0) / 2.0))
        else:
            confidence = 0.4 if answer_text else 0.0

        result = {
            "answer": answer_text or "I couldn't derive an answer from the provided excerpts.",
            "query": request.query,
            "sources": sources,
            "sources_count": len(sources),
            "tokens_generated": tokens_generated,
            "task_id": task_id,
            "has_context": bool(transcript_results or memory_results),
            "mode": "gpu" if model_on_gpu else "cpu",
            "confidence": confidence,
        }

        if gpu_slot_acquired and not gpu_slot_released:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                    json={"result": result},
                headers=get_service_headers()
                )
            gpu_slot_released = True

        if model_on_gpu and used_gpu:
            move_model_to_cpu()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TASK {task_id}] Error: {e}")
        import traceback
        traceback.print_exc()

        try:
            if gpu_slot_acquired and not gpu_slot_released:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{GPU_COORDINATOR_URL}/gemma/release/{task_id}",
                        json={"result": {"error": str(e)}},
                    headers=get_service_headers()
                    )
        except Exception as release_error:
            logger.error(f"[TASK {task_id}] Failed to release GPU after error: {release_error}")

        try:
            if model_on_gpu and used_gpu:
                move_model_to_cpu()
        except Exception as cpu_error:
            logger.error(f"[TASK {task_id}] Failed to move model back to CPU after error: {cpu_error}")

        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """Get service statistics"""
    stats = {
        "model_loaded": gemma_model is not None,
        "model_on_gpu": model_on_gpu,
        "gpu_layers": GEMMA_GPU_LAYERS,
        "context_size": GEMMA_CONTEXT_SIZE,
        "coordinator_url": GPU_COORDINATOR_URL,
    }
    
    # Get VRAM usage
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info = result.stdout.strip().split('\n')[0].split(',')
            stats["vram_used_mb"] = int(info[0].strip())
            stats["vram_total_mb"] = int(info[1].strip())
            stats["gpu_utilization"] = int(info[2].strip())
    except:
        pass
    
    return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
