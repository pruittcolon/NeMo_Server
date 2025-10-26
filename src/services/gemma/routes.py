"""
Gemma AI Analysis API Routes

FastAPI endpoints for Gemma AI analysis
Extracted from main3.py (analysis endpoints)

Endpoints:
- POST /analyze/personality - Personality analysis
- POST /analyze/emotional_triggers - Emotional trigger detection
- POST /analyze/gemma_summary - Generate summary
- POST /analyze/comprehensive - Comprehensive analysis
- GET /job/{job_id} - Get job status
- GET /jobs - List jobs
- WebSocket /ws/gemma - Real-time job progress updates

Maintains backward compatibility with original API
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio
import json

from .service import GemmaService


# Create router
router = APIRouter(prefix="/analyze", tags=["gemma"])
jobs_router = APIRouter(prefix="", tags=["jobs"])
ws_router = APIRouter(prefix="/ws", tags=["websocket"])

# Service instance (will be initialized by main app)
_service: Optional[GemmaService] = None

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for job updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

# Global connection manager
connection_manager = ConnectionManager()


def initialize_service(
    model_path: Optional[str] = None,
    max_context_tokens: int = 8192,
    enforce_gpu: bool = True
) -> GemmaService:
    """
    Initialize Gemma service
    
    Args:
        model_path: Path to Gemma GGUF model
        max_context_tokens: Maximum context window
        enforce_gpu: Enforce GPU-only operation
    
    Returns:
        Initialized GemmaService
    """
    global _service
    _service = GemmaService(
        model_path=model_path,
        max_context_tokens=max_context_tokens,
        enforce_gpu=enforce_gpu
    )
    
    # Set up WebSocket broadcast callback
    def broadcast_update(job_dict: Dict[str, Any]):
        """Sync broadcast wrapper for async WebSocket"""
        try:
            # Create new event loop for thread-safe broadcasting
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(connection_manager.broadcast(job_dict))
            loop.close()
        except Exception as e:
            print(f"[GEMMA ROUTES] Broadcast error: {e}")
    
    _service.set_broadcast_callback(broadcast_update)
    
    return _service


def get_service() -> GemmaService:
    """Get Gemma service instance"""
    if _service is None:
        raise RuntimeError("Gemma service not initialized")
    return _service


# -------------------------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------------------------

class PersonalityAnalysisRequest(BaseModel):
    """Request model for personality analysis"""
    segments: List[Dict[str, Any]]


class EmotionalTriggersRequest(BaseModel):
    """Request model for emotional trigger detection"""
    segments: List[Dict[str, Any]]


class GemmaSummaryRequest(BaseModel):
    """Request model for summary generation"""
    context: Dict[str, Any]


class ComprehensiveAnalysisRequest(BaseModel):
    """Request model for comprehensive analysis"""
    segments: List[Dict[str, Any]]


class ChatRequest(BaseModel):
    """Request model for simple chat"""
    message: str
    max_length: int = 150


# -------------------------------------------------------------------------
# Analysis Endpoints
# -------------------------------------------------------------------------

@router.post("/personality")
def start_personality_analysis(payload: PersonalityAnalysisRequest) -> Dict[str, str]:
    """
    Start personality analysis job
    
    Args:
        payload: Request with segments
    
    Returns:
        {"job_id": str, "status": "queued"}
    """
    service = get_service()
    
    try:
        job_id = service.submit_job(
            job_type="personality_analysis",
            params={"segments": payload.segments}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        print(f"[GEMMA API] Personality analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emotional_triggers")
def start_emotional_triggers(payload: EmotionalTriggersRequest) -> Dict[str, str]:
    """
    Start emotional trigger detection job
    
    Args:
        payload: Request with segments
    
    Returns:
        {"job_id": str, "status": "queued"}
    """
    service = get_service()
    
    try:
        job_id = service.submit_job(
            job_type="emotional_triggers",
            params={"segments": payload.segments}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        print(f"[GEMMA API] Emotional triggers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gemma_summary")
def start_gemma_summary(payload: GemmaSummaryRequest) -> Dict[str, str]:
    """
    Start Gemma summary generation job
    
    Args:
        payload: Request with context
    
    Returns:
        {"job_id": str, "status": "queued"}
    """
    service = get_service()
    
    try:
        job_id = service.submit_job(
            job_type="gemma_summary",
            params={"context": payload.context}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        print(f"[GEMMA API] Summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comprehensive")
def start_comprehensive_analysis(payload: ComprehensiveAnalysisRequest) -> Dict[str, str]:
    """
    Start comprehensive analysis job (all analyses combined)
    
    Args:
        payload: Request with segments
    
    Returns:
        {"job_id": str, "status": "queued"}
    """
    service = get_service()
    
    try:
        job_id = service.submit_job(
            job_type="comprehensive",
            params={"segments": payload.segments}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        print(f"[GEMMA API] Comprehensive analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
def gemma_chat(payload: ChatRequest) -> Dict[str, str]:
    """
    Synchronous chat endpoint
    
    Args:
        payload: Chat message
    
    Returns:
        {"response": str}
    """
    service = get_service()
    
    try:
        # Submit job and wait for result
        job_id = service.submit_job(
            job_type="gemma_summary",
            params={
                "context": {
                    "transcripts": [],
                    "user_message": payload.message
                }
            }
        )
        
        # Poll for result (timeout 30s)
        import time
        timeout = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            job = service.get_job(job_id)
            if job and job.get('status') == 'completed':
                result = job.get('result', {})
                return {"response": result.get('summary', 'No response')}
            elif job and job.get('status') == 'failed':
                raise HTTPException(status_code=500, detail=job.get('error', 'Job failed'))
            
            time.sleep(0.5)
        
        raise HTTPException(status_code=408, detail="Request timeout")
        
    except Exception as e:
        print(f"[GEMMA API] Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
def get_gemma_stats() -> Dict[str, Any]:
    """
    Get Gemma service statistics
    
    Returns:
        Service stats including GPU status, job counts
    """
    service = get_service()
    return service.get_stats()


# -------------------------------------------------------------------------
# Job Management Endpoints
# -------------------------------------------------------------------------

@jobs_router.get("/job/{job_id}")
def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get job status and result
    
    Args:
        job_id: Job identifier
    
    Returns:
        Job details including status, progress, result
    
    Raises:
        HTTPException: 404 if job not found
    """
    service = get_service()
    
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@jobs_router.get("/jobs")
def list_jobs(limit: int = 50) -> Dict[str, Any]:
    """
    List recent jobs
    
    Args:
        limit: Maximum number of jobs to return
    
    Returns:
        {"jobs": List[Dict], "count": int}
    """
    service = get_service()
    
    jobs = service.list_jobs(limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


# -------------------------------------------------------------------------
# WebSocket Endpoint
# -------------------------------------------------------------------------

@ws_router.websocket("/gemma")
async def websocket_gemma_updates(websocket: WebSocket):
    """
    WebSocket endpoint for real-time job progress updates
    
    Clients connect to receive broadcast messages when jobs update
    
    Message format:
    {
        "job_id": str,
        "job_type": str,
        "status": str,
        "progress": float,
        "result": Dict or null,
        "error": str or null
    }
    """
    await connection_manager.connect(websocket)
    print(f"[GEMMA WS] Client connected (total: {len(connection_manager.active_connections)})")
    
    try:
        while True:
            # Keep connection alive by receiving messages
            # (clients can send ping messages if needed)
            data = await websocket.receive_text()
            
            # Echo back as keepalive (optional)
            if data == "ping":
                await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
        print(f"[GEMMA WS] Client disconnected (remaining: {len(connection_manager.active_connections)})")
    
    except Exception as e:
        print(f"[GEMMA WS] Error: {e}")
        connection_manager.disconnect(websocket)


# -------------------------------------------------------------------------
# Export routers
# -------------------------------------------------------------------------

def get_routers() -> List[APIRouter]:
    """Get all Gemma-related routers"""
    return [router, jobs_router, ws_router]


