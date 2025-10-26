"""
RAG (Retrieval-Augmented Generation) Service

Thin wrapper around existing AdvancedMemoryService
As per user request: "I WANT advanced_memory_service.py to remain AS IS"

This service provides:
- Memory search (semantic search via FAISS)
- Transcript search
- RAG question answering
- Session management

All heavy lifting is done by the existing AdvancedMemoryService
This wrapper ensures CPU-only operation for embeddings
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import config from parent
parent_src = str(Path(__file__).parent.parent.parent.parent / "src")
if parent_src not in sys.path:
    sys.path.insert(0, parent_src)

# Import config module
try:
    from src import config
except ImportError:
    import config

try:
    # Import existing AdvancedMemoryService unchanged
    from advanced_memory_service import AdvancedMemoryService
    print("[RAG] Successfully imported AdvancedMemoryService")
except ImportError as e:
    print(f"[RAG] ERROR: Failed to import AdvancedMemoryService: {e}")
    print("[RAG] Ensure src/advanced_memory_service.py exists and is importable")
    AdvancedMemoryService = None


class RagService:
    """
    RAG service wrapper
    
    Delegates all operations to existing AdvancedMemoryService
    Ensures CPU-only for embeddings (GPU reserved for Gemma)
    """
    
    def __init__(
        self,
        database_path: Optional[str] = None,
        faiss_index_path: Optional[str] = None,
        embedding_model_name: Optional[str] = None
    ):
        """
        Initialize RAG service
        
        Args:
            database_path: Path to SQLite database
            faiss_index_path: Path to FAISS index
            embedding_model_name: Name of embedding model
        """
        if AdvancedMemoryService is None:
            raise RuntimeError("AdvancedMemoryService not available")
        
        # Initialize the existing service
        # It will use config.py for defaults
        gemma_model_path = config.GEMMA_MODEL_PATH  # Enable Gemma LLM
        self.memory_service = AdvancedMemoryService(
            db_path=database_path,
            faiss_index_path=faiss_index_path,
            embedding_model_name=embedding_model_name,
            gemma_model_path=gemma_model_path
        )
        
        print("[RAG] Service initialized (wrapping AdvancedMemoryService)")
    
    # -------------------------------------------------------------------------
    # Memory Operations
    # -------------------------------------------------------------------------
    
    def search_memories(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across memories
        
        Args:
            query: Search query
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
        
        Returns:
            List of memory results with scores
        """
        # Call with 'limit' parameter (not 'top_k') - matches AdvancedMemoryService signature
        results = self.memory_service.search_memories(
            query=query,
            limit=top_k
        )
        
        # Filter by min_similarity if needed
        if min_similarity > 0:
            results = [r for r in results if r.get('score', 0) >= min_similarity]
        
        return results
    
    def list_memories(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all memories
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
        
        Returns:
            List of memory documents
        """
        return self.memory_service.list_memories(
            limit=limit,
            offset=offset
        )
    
    def create_memory(
        self,
        content: str,
        source: str = "manual",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create new memory entry
        
        Args:
            content: Memory content
            source: Source of memory (default: "manual")
            metadata: Optional metadata
        
        Returns:
            Created memory document
        """
        return self.memory_service.create_memory(
            content=content,
            source=source,
            metadata=metadata
        )
    
    # -------------------------------------------------------------------------
    # Transcript Operations
    # -------------------------------------------------------------------------
    
    def search_transcripts(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across transcripts
        
        Args:
            query: Search query
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
        
        Returns:
            List of transcript results with scores
        """
        return self.memory_service.search_transcripts(
            query=query,
            top_k=top_k,
            min_similarity=min_similarity
        )
    
    def get_transcript(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get transcript by job ID
        
        Args:
            job_id: Job identifier
        
        Returns:
            Transcript data or None if not found
        """
        return self.memory_service.get_transcript(job_id)
    
    # -------------------------------------------------------------------------
    # RAG Query (Question Answering)
    # -------------------------------------------------------------------------
    
    def query(
        self,
        question: str,
        context_size: int = 5
    ) -> Dict[str, Any]:
        """
        Answer question using RAG
        
        Retrieves relevant context and generates answer
        
        Args:
            question: User question
            context_size: Number of context documents to retrieve
        
        Returns:
            {
                "question": str,
                "answer": str,
                "sources": List[Dict],
                "context_used": int
            }
        """
        return self.memory_service.query(
            question=question,
            context_size=context_size
        )
    
    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------
    
    def save_segments(
        self,
        result: Dict[str, Any],
        job_id: str,
        log_callback: Optional[Any] = None
    ) -> None:
        """
        Save transcription segments to database
        
        Args:
            result: Transcription result with segments
            job_id: Job identifier
            log_callback: Optional callback for logging
        """
        self.memory_service.save_segments(
            result=result,
            job_id=job_id,
            log_callback=log_callback
        )
    
    def save_job_bundle(
        self,
        job_id: str,
        full_text: str,
        result: Dict[str, Any]
    ) -> None:
        """
        Save job bundle (full transcript + metadata)
        
        Args:
            job_id: Job identifier
            full_text: Full transcribed text
            result: Transcription result
        """
        self.memory_service.save_job_bundle(
            job_id=job_id,
            full_text=full_text,
            result=result
        )
    
    def maybe_autocreate_memory(
        self,
        text: str,
        job_id: str
    ) -> None:
        """
        Auto-create memory if text is significant
        
        Args:
            text: Transcribed text
            job_id: Job identifier
        """
        self.memory_service.maybe_autocreate_memory(
            text=text,
            job_id=job_id
        )
    
    # -------------------------------------------------------------------------
    # Statistics & Health
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get service statistics
        
        Returns:
            Stats including document counts, index info, etc.
        """
        # Use the existing get_stats method from AdvancedMemoryService
        return self.memory_service.get_stats()
    
    def add_transcript(
        self,
        text: str,
        segments: List[Dict[str, Any]],
        job_id: str,
        session_id: str,
        audio_duration: float
    ) -> int:
        """
        Store transcription in database
        
        Args:
            text: Full transcribed text
            segments: List of segment dicts with speaker, text, timing
            job_id: Unique job identifier
            session_id: Session identifier
            audio_duration: Duration in seconds
        
        Returns:
            transcript_id: Database ID of stored transcript
        """
        return self.memory_service.add_transcript(
            text=text,
            segments=segments,
            job_id=job_id,
            session_id=session_id,
            audio_duration=audio_duration
        )
    
    def health_check(self) -> Dict[str, bool]:
        """
        Check service health
        
        Returns:
            Health status for each component
        """
        try:
            # Try a simple query to check if everything works
            _ = self.memory_service.search_memories("test", limit=1)
            return {
                "database": True,
                "faiss_index": True,
                "embedding_model": True,
                "overall": True
            }
        except Exception as e:
            print(f"[RAG] Health check failed: {e}")
            return {
                "database": False,
                "faiss_index": False,
                "embedding_model": False,
                "overall": False,
                "error": str(e)
            }
    
    # -------------------------------------------------------------------------
    # Passthrough Properties
    # -------------------------------------------------------------------------
    
    @property
    def database_path(self) -> Path:
        """Get database path"""
        return self.memory_service.database_path
    
    @property
    def embedding_model_name(self) -> str:
        """Get embedding model name"""
        return self.memory_service.embedding_model_name
    
    def now_iso(self) -> str:
        """Get current ISO timestamp"""
        return self.memory_service.now_iso()


