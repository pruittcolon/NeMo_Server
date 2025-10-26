"""
RAG API Routes

FastAPI endpoints for memory and transcript operations
Extracted from main3.py (various memory/transcript endpoints)

Endpoints:
- GET /memory/search - Semantic search across memories
- GET /memory/list - List all memories
- POST /memory/create - Create new memory
- GET /transcript/search - Search transcripts
- GET /transcript/{job_id} - Get transcript by ID
- POST /query - RAG question answering

Maintains backward compatibility with original API
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from .service import RagService
from src.auth.permissions import get_current_user, require_auth, User


# Create routers
memory_router = APIRouter(prefix="/memory", tags=["memory"])
transcript_router = APIRouter(prefix="/transcript", tags=["transcript"])
query_router = APIRouter(prefix="", tags=["query"])

# Service instance (will be initialized by main app)
_service: Optional[RagService] = None


def initialize_service(
    database_path: Optional[str] = None,
    faiss_index_path: Optional[str] = None,
    embedding_model_name: Optional[str] = None
) -> RagService:
    """
    Initialize RAG service
    
    Args:
        database_path: Path to SQLite database
        faiss_index_path: Path to FAISS index
        embedding_model_name: Embedding model name
    
    Returns:
        Initialized RagService
    """
    global _service
    _service = RagService(
        database_path=database_path,
        faiss_index_path=faiss_index_path,
        embedding_model_name=embedding_model_name
    )
    return _service


def get_service() -> RagService:
    """Get RAG service instance"""
    if _service is None:
        raise RuntimeError("RAG service not initialized")
    return _service


# -------------------------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------------------------

class MemoryCreate(BaseModel):
    """Request model for memory creation"""
    content: str
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    """Request model for RAG query"""
    question: str
    context_size: int = 5


# -------------------------------------------------------------------------
# Memory Endpoints
# -------------------------------------------------------------------------

@memory_router.get("/search")
def search_memories(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(10, ge=1, le=100, description="Number of results"),
    min_similarity: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity"),
    user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Semantic search across memories
    
    Args:
        q: Search query
        top_k: Number of results (1-100)
        min_similarity: Minimum similarity threshold (0.0-1.0)
    
    Returns:
        List of memory results with scores
    """
    service = get_service()
    
    try:
        results = service.search_memories(
            query=q,
            top_k=top_k,
            min_similarity=min_similarity
        )
        return results
    except Exception as e:
        print(f"[RAG API] Memory search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/list")
def list_memories(
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    List all memories with pagination
    
    Args:
        limit: Maximum results (1-1000)
        offset: Pagination offset
    
    Returns:
        List of memory documents
    """
    service = get_service()
    
    try:
        results = service.list_memories(
            limit=limit,
            offset=offset
        )
        return results
    except Exception as e:
        print(f"[RAG API] List memories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.post("/create")
def create_memory(
    payload: MemoryCreate,
    user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create new memory entry
    
    Args:
        payload: Memory creation request
    
    Returns:
        Created memory document with ID
    """
    service = get_service()
    
    try:
        result = service.create_memory(
            content=payload.content,
            source=payload.source,
            metadata=payload.metadata
        )
        return result
    except Exception as e:
        print(f"[RAG API] Create memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/stats")
def get_memory_stats(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get memory service statistics
    
    Returns:
        Stats including document counts, index info
    """
    service = get_service()
    return service.get_stats()


@memory_router.get("/health")
def check_memory_health(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Check memory service health
    
    Returns:
        Health status for each component
    """
    service = get_service()
    return service.health_check()


# -------------------------------------------------------------------------
# Transcript Endpoints
# -------------------------------------------------------------------------

@transcript_router.get("/search")
def search_transcripts(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(10, ge=1, le=100, description="Number of results"),
    min_similarity: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity"),
    user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Semantic search across transcripts
    
    Args:
        q: Search query
        top_k: Number of results (1-100)
        min_similarity: Minimum similarity threshold (0.0-1.0)
    
    Returns:
        List of transcript results with scores
    """
    service = get_service()
    
    try:
        results = service.search_transcripts(
            query=q,
            top_k=top_k,
            min_similarity=min_similarity
        )
        return results
    except Exception as e:
        print(f"[RAG API] Transcript search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@transcript_router.get("/{job_id}")
def get_transcript(
    job_id: str,
    user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get transcript by job ID
    
    Args:
        job_id: Job identifier
    
    Returns:
        Transcript data
    
    Raises:
        HTTPException: 404 if not found
    """
    service = get_service()
    
    result = service.get_transcript(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    return result


# -------------------------------------------------------------------------
# Query Endpoint (RAG Question Answering)
# -------------------------------------------------------------------------

@query_router.post("/query")
def rag_query(
    payload: QueryRequest,
    session = Depends(require_auth)
) -> Dict[str, Any]:
    """
    Answer question using RAG (Retrieval-Augmented Generation)
    
    Retrieves relevant context from memory/transcripts and generates answer
    
    Args:
        payload: Query request with question and context size
    
    Returns:
        {
            "question": str,
            "answer": str,
            "sources": List[Dict],
            "context_used": int
        }
    """
    service = get_service()
    
    try:
        result = service.query(
            question=payload.question,
            context_size=payload.context_size
        )
        return result
    except Exception as e:
        print(f"[RAG API] Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Export routers
# -------------------------------------------------------------------------

def get_routers() -> List[APIRouter]:
    """Get all RAG-related routers"""
    return [memory_router, transcript_router, query_router]

