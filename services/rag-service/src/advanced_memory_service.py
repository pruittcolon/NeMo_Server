#!/usr/bin/env python3
"""
Advanced Memory Service with FAISS-based RAG system
Based on Bbs1412/rag-with-gemma3 approach for better search and retrieval
"""

import os
import sqlite3
import uuid
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import defaultdict, deque
import json
import re

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from llama_cpp import Llama, llama_cpp as llama_backend
import faiss
os.environ.setdefault("GGML_CUDA_FORCE_MMQ", "0")
os.environ.setdefault("GGML_CUDA_MMQ_MAX_SEQ", "0")
from dataclasses import dataclass
import config

@dataclass
class Document:
    """Document structure for FAISS storage"""
    id: str
    text: str
    metadata: Dict[str, Any]
    embedding: Optional[np.ndarray] = None

def count_tokens(text: str) -> int:
    """Rough token count estimation (1 token ≈ 4 characters for English)"""
    if not text:
        return 0
    # Remove extra whitespace and count words + punctuation
    cleaned = re.sub(r'\s+', ' ', text.strip())
    return len(cleaned.split()) + len(re.findall(r'[^\w\s]', cleaned))

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token limit"""
    if count_tokens(text) <= max_tokens:
        return text
    
    # More aggressive truncation - start with a conservative estimate
    # Estimate 4 characters per token, then adjust
    estimated_length = max_tokens * 3  # Conservative estimate
    test_text = text[:estimated_length]
    
    # If still too long, binary search for the right length
    if count_tokens(test_text) > max_tokens:
        left, right = 0, estimated_length
        best_length = 0
        
        while left <= right:
            mid = (left + right) // 2
            test_text = text[:mid]
            if count_tokens(test_text) <= max_tokens:
                best_length = mid
                left = mid + 1
            else:
                right = mid - 1
        
        if best_length > 0:
            return text[:best_length] + "... [truncated]"
        return ""
    else:
        return test_text

class ConversationMemory:
    """Manages conversation history for context"""
    
    def __init__(self, max_history: int = 5) -> None:
        self.conversations: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))

    def add(self, session_id: str, question: str, answer: str) -> None:
        self.conversations[session_id].append({
            "question": question,
            "answer": answer,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def context(self, session_id: str) -> str:
        turns = self.conversations.get(session_id)
        if not turns:
            return ""
        lines: List[str] = []
        for turn in turns:
            lines.append(f"Q: {turn['question']}")
            lines.append(f"A: {turn['answer'][:200]}...")
        return "\n".join(lines)

    def clear(self, session_id: str) -> None:
        if session_id in self.conversations:
            del self.conversations[session_id]

class AdvancedMemoryService:
    """Advanced RAG service with FAISS-based vector search and dynamic GPU management"""
    
    def __init__(
        self,
        db_path: str,
        embedding_model_name: str = "all-MiniLM-L6-v2",
        gemma_model_path: Optional[str] = None,
        top_k_hits: int = 5,
        max_gemma_tokens: int = 512,
        max_context_length: int = 2000,
        embedding_cache_size: int = 1000,
        faiss_index_path: Optional[str] = None,
    ):
        self.db_path = db_path
        self.embedding_model_name = embedding_model_name
        self.gemma_model_path = gemma_model_path
        self.top_k_hits = top_k_hits
        self.max_gemma_tokens = max_gemma_tokens
        self.max_context_length = max_context_length
        self.embedding_cache_size = embedding_cache_size
        
        # FAISS setup
        self.faiss_index_path = faiss_index_path or os.path.join(os.path.dirname(db_path), "faiss_index")
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        self.faiss_index = None
        self.document_store: Dict[str, Document] = {}
        
        # Thread safety
        self.lock = threading.RLock()
        self.llm_lock = threading.RLock()
        
        # Dynamic GPU management
        self._gemma_gpu_mode = False
        self._other_models_on_cpu = False
        
        # Initialize components
        self._init_embedding_model()
        self._init_llm()
        self._init_faiss_index()
        self._init_db()
        self._load_existing_data()
        self.conversations = ConversationMemory()
        
        print(f"[INIT] Advanced Memory Service initialized with FAISS")
        
        # Log current VRAM usage
        self._log_vram_usage()

    def _log_vram_usage(self) -> None:
        """Log current VRAM usage for monitoring"""
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            cached = torch.cuda.memory_reserved(0) / (1024**3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"[VRAM] Allocated: {allocated:.1f}GB, Cached: {cached:.1f}GB, Total: {total:.1f}GB")
        else:
            print("[VRAM] No GPU available for monitoring")

    def _switch_to_gemma_gpu_mode(self) -> None:
        """Gemma is always on GPU - just clear cache for optimal performance"""
        if self._gemma_gpu_mode:
            return  # Already in Gemma GPU mode
            
        print("[GPU_SWITCH] Gemma is always on GPU - clearing cache for optimal performance...")
        
        # Clear GPU cache for optimal performance
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Embedding model is already on CPU to prioritize Gemma
        self._gemma_gpu_mode = True
        print("[GPU_SWITCH] ✅ Gemma GPU mode active (always on GPU)")

    def _switch_to_transcription_gpu_mode(self) -> None:
        """Gemma stays on GPU - just clear cache for optimal performance"""
        if not self._gemma_gpu_mode:
            return  # Already in transcription GPU mode
            
        print("[GPU_SWITCH] Gemma stays on GPU - clearing cache for optimal performance...")
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Gemma stays on GPU for maximum performance
        self._gemma_gpu_mode = True  # Keep Gemma on GPU
        print("[GPU_SWITCH] ✅ Transcription mode active (Gemma stays on GPU)")
        
        # Embedding model stays on CPU to prioritize Gemma
        print("[GPU_SWITCH] Embedding model stays on CPU to prioritize Gemma GPU performance")

    def _init_embedding_model(self) -> None:
        """Initialize the embedding model - use CPU to prioritize Gemma GPU usage"""
        try:
            print(f"[INIT] Loading embedding model: {self.embedding_model_name}")
            
            # Use CPU for embedding model to prioritize Gemma GPU usage
            device = 'cpu'  # Always use CPU to save VRAM for Gemma
            print(f"[INIT] Using CPU for embedding model to prioritize Gemma GPU performance")
            
            source_path = config.EMBEDDING_MODEL_PATH
            if os.path.isdir(source_path):
                print(f"[INIT] Loading embedding model from local path: {source_path}")
                self.embedding_model = SentenceTransformer(source_path, device=device)
            else:
                print(
                    f"[WARN] Local embedding model not found at {source_path}. "
                    f"Attempting to load '{self.embedding_model_name}' from "
                    f"{'Hugging Face' if config.ALLOW_MODEL_DOWNLOAD else 'an existing cache'}."
                )
                try:
                    # SentenceTransformer 2.7.0 doesn't support local_files_only parameter
                    self.embedding_model = SentenceTransformer(
                        self.embedding_model_name,
                        device=device
                    )
                except Exception as exc:
                    suffix = (
                        "Download it manually and set EMBEDDING_MODEL_PATH."
                        if config.ALLOW_MODEL_DOWNLOAD
                        else "Enable downloads via ALLOW_MODEL_DOWNLOAD=1 or provide a local cache."
                    )
                    raise RuntimeError(
                        f"Failed to load embedding model '{self.embedding_model_name}'. {suffix}"
                    ) from exc
            print(f"[INIT] Embedding model loaded successfully on {device}")
        except Exception as e:
            print(f"[ERROR] Failed to load embedding model: {e}")
            raise

    def _init_llm(self) -> None:
        """Initialize the Gemma LLM with maximum GPU priority"""
        self._llm = None
        
        if self.gemma_model_path and os.path.exists(self.gemma_model_path):
            try:
                print(f"[INIT] Loading Gemma model with maximum GPU priority: {self.gemma_model_path}")
                
                device_pref = getattr(config, "GEMMA_DEVICE", "cpu").lower()
                requested_gpu_layers = getattr(config, "GEMMA_GPU_LAYERS", -1)
                
                if torch.cuda.is_available() and device_pref == "gpu":
                    total_memory = torch.cuda.get_device_properties(0).total_memory
                    allocated_memory = torch.cuda.memory_allocated(0)
                    free_memory = total_memory - allocated_memory
                    free_gb = free_memory / (1024**3)
                    
                    print(f"[INIT] Available VRAM for Gemma: {free_gb:.1f}GB")
                    
                    if requested_gpu_layers >= 0:
                        gpu_layers = requested_gpu_layers
                        print(f"[INIT] Using configured GEMMA_GPU_LAYERS={gpu_layers}")
                    else:
                        # Conservative auto-allocation: aim for ~0.2 GB per layer
                        auto_layers = max(0, int(free_gb / 0.2))
                        gpu_layers = min(auto_layers, 40)
                        print(f"[INIT] Auto-selected GPU layers: {gpu_layers}")
                else:
                    gpu_layers = 0
                    if device_pref == "gpu":
                        print("[INIT] GPU requested but not available. Falling back to CPU for Gemma.")
                    else:
                        print("[INIT] GEMMA_DEVICE set to CPU - running Gemma on CPU")
                
                # Clear GPU cache before loading Gemma
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()  # Clear twice
                    print("[INIT] Cleared GPU cache for Gemma model")
                    
                    # Force garbage collection before loading
                    import gc
                    gc.collect()
                    print("[INIT] Ran garbage collection")
                
                print(f"[INIT] Llama config: n_ctx=2048, n_threads=2, n_gpu_layers={gpu_layers}, n_batch=256")
                llama_kwargs = dict(
                    model_path=self.gemma_model_path,
                    n_ctx=2048,  # Reduced from 2048 to fit in GPU memory
                    n_threads=2,  # Optimized threads
                    n_gpu_layers=gpu_layers,  # Maximum GPU layer usage
                    n_batch=256,  # Reduced from 512 to fit in GPU memory
                    verbose=True,  # Enable verbose for debugging
                    low_vram=False,  # Disable low VRAM - Gemma has full GPU freedom
                )
                
                try:
                    self._llm = Llama(**llama_kwargs)
                    print("[INIT] ✅ Gemma model loaded successfully!")
                    self._gemma_gpu_mode = gpu_layers > 0
                    
                    # Log VRAM usage after loading
                    try:
                        if torch.cuda.is_available():
                            torch.cuda.synchronize()  # Wait for all operations to complete
                            vram_allocated = torch.cuda.memory_allocated(0) / 1024**3
                            vram_reserved = torch.cuda.memory_reserved(0) / 1024**3
                            vram_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                            print(f"[GEMMA] VRAM Usage: {vram_allocated:.2f}/{vram_total:.2f} GB allocated")
                            print(f"[GEMMA] VRAM Reserved: {vram_reserved:.2f} GB")
                            print(f"[GEMMA] GPU Layers: {gpu_layers} (optimized for concurrent operation)")
                            print(f"[GEMMA] VRAM Available for Transcription: {(vram_total - vram_reserved):.2f} GB")
                    except Exception as e:
                        print(f"[GEMMA] Could not log VRAM: {e}")
                except Exception as gpu_error:
                    # GPU failed, try CPU first (more stable)
                    print(f"[WARN] GPU initialization failed: {gpu_error}")
                    print("[WARN] Retrying Gemma model on CPU (more stable)...")
                    
                    # Try CPU with full context
                    cpu_kwargs = {
                        'model_path': self.gemma_model_path,
                        'n_ctx': 2048,
                        'n_threads': 8,  # More threads for CPU performance
                        'n_gpu_layers': 0,  # CPU only
                        'n_batch': 128,  # Moderate batch for CPU
                        'verbose': True,  # Enable verbose for debugging
                    }
                    
                    try:
                        self._llm = Llama(**cpu_kwargs)
                        print("[INIT] ✅ Gemma model loaded on CPU successfully!")
                        self._gemma_gpu_mode = False
                    except Exception as cpu_error:
                        print(f"[ERROR] Failed to load Gemma on CPU: {cpu_error}")
                        print(f"[ERROR] Model path: {self.gemma_model_path}")
                        print(f"[ERROR] File exists: {os.path.exists(self.gemma_model_path)}")
                        print(f"[ERROR] File size: {os.path.getsize(self.gemma_model_path) if os.path.exists(self.gemma_model_path) else 'N/A'} bytes")
                        self._llm = None
                        self._gemma_gpu_mode = False
            except Exception as e:
                print(f"[ERROR] Failed to load Gemma model: {e}")
                self._llm = None
                self._gemma_gpu_mode = False

    def _init_faiss_index(self) -> None:
        """Initialize or load FAISS index"""
        try:
            if os.path.exists(self.faiss_index_path):
                print(f"[INIT] Loading existing FAISS index from {self.faiss_index_path}")
                self.faiss_index = faiss.read_index(self.faiss_index_path)
                # Load document store
                doc_store_path = f"{self.faiss_index_path}.docs"
                if os.path.exists(doc_store_path):
                    with open(doc_store_path, 'r', encoding='utf-8') as f:
                        docs_data = json.load(f)
                        for doc_id, doc_data in docs_data.items():
                            self.document_store[doc_id] = Document(
                                id=doc_data['id'],
                                text=doc_data['text'],
                                metadata=doc_data['metadata'],
                                embedding=np.array(doc_data['embedding']) if doc_data.get('embedding') else None
                            )
                print(f"[INIT] FAISS index loaded with {self.faiss_index.ntotal} documents")
            else:
                print(f"[INIT] Creating new FAISS index")
                self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)  # Inner product for cosine similarity
                print(f"[INIT] New FAISS index created")
        except Exception as e:
            print(f"[ERROR] Failed to initialize FAISS index: {e}")
            self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)

    def _init_db(self) -> None:
        """Initialize SQLite database"""
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Create transcripts table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    speaker TEXT,
                    start REAL,
                    end REAL,
                    text TEXT,
                    created_at TEXT
                )
            """)
            
            # Create memories table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    body TEXT,
                    created_at TEXT
                )
            """)
            
            # Create transcript_records table (new transcript storage system)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcript_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE,
                    session_id TEXT,
                    full_text TEXT,
                    audio_duration REAL,
                    timestamp TEXT,
                    created_at TEXT
                )
            """)
            
            # Create transcript_segments table (enhanced segments with speaker/emotion)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcript_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transcript_id INTEGER,
                    seq INTEGER,
                    start_time REAL,
                    end_time REAL,
                    text TEXT,
                    speaker TEXT,
                    speaker_confidence REAL,
                    emotion TEXT,
                    emotion_confidence REAL,
                    emotion_scores TEXT,
                    created_at TEXT,
                    FOREIGN KEY (transcript_id) REFERENCES transcript_records (id)
                )
            """)
            
            # Create job_transcripts table (job bundles)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_transcripts (
                    job_id TEXT PRIMARY KEY,
                    full_text TEXT,
                    raw_json TEXT,
                    created_at TEXT
                )
            """)
            
            conn.commit()
            conn.close()

    def _load_existing_data(self) -> None:
        """Load existing transcripts and memories from database into FAISS index"""
        if self.faiss_index.ntotal > 0:
            print(f"[INIT] FAISS index already has {self.faiss_index.ntotal} documents, skipping data load")
            return
            
        try:
            print(f"[INIT] Loading existing data from database...")
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Load transcripts
            cur.execute("SELECT job_id, speaker, start, end, text, created_at FROM transcripts WHERE text IS NOT NULL AND text != ''")
            transcripts = cur.fetchall()
            print(f"[INIT] Found {len(transcripts)} transcripts to load")
            
            embeddings_to_add = []
            documents_to_add = []
            
            for transcript in transcripts:
                text = transcript['text']
                if len(text.strip()) < 3:  # Skip very short texts
                    continue
                    
                doc_id = f"transcript_{transcript['job_id']}_{transcript['created_at']}"
                embedding = self.get_embedding(text)
                
                document = Document(
                    id=doc_id,
                    text=text,
                    metadata={
                        "type": "transcript",
                        "job_id": transcript['job_id'],
                        "speaker": transcript['speaker'],
                        "start": transcript['start'],
                        "end": transcript['end'],
                        "created_at": transcript['created_at']
                    },
                    embedding=embedding
                )
                
                self.document_store[doc_id] = document
                embeddings_to_add.append(embedding)
                documents_to_add.append(document)
            
            # Load memories
            cur.execute("SELECT id, title, body, created_at, speaker_id, owner_user_id FROM memories WHERE body IS NOT NULL AND body != ''")
            memories = cur.fetchall()
            print(f"[INIT] Found {len(memories)} memories to load")
            
            for memory in memories:
                text = f"{memory['title']}\n{memory['body']}"
                if len(text.strip()) < 3:  # Skip very short texts
                    continue
                    
                doc_id = f"memory_{memory['id']}"
                embedding = self.get_embedding(text)
                
                speaker_id = memory['speaker_id'] if 'speaker_id' in memory.keys() else None
                owner_user_id = memory['owner_user_id'] if 'owner_user_id' in memory.keys() else None
                document = Document(
                    id=doc_id,
                    text=text,
                    metadata={
                        "type": "memory",
                        "memory_id": memory['id'],
                        "title": memory['title'],
                        "body": memory['body'],
                        "created_at": memory['created_at'],
                        "speaker_id": speaker_id,
                        "owner_user_id": owner_user_id
                    },
                    embedding=embedding
                )
                
                self.document_store[doc_id] = document
                embeddings_to_add.append(embedding)
                documents_to_add.append(document)
            
            conn.close()
            
            # Add all embeddings to FAISS index at once
            if embeddings_to_add:
                embeddings_array = np.vstack(embeddings_to_add)
                self.faiss_index.add(embeddings_array)
                print(f"[INIT] Loaded {len(embeddings_to_add)} documents into FAISS index")
                
                # Save the index
                self._save_faiss_index()
            else:
                print(f"[INIT] No documents to load")
                
        except Exception as e:
            print(f"[ERROR] Failed to load existing data: {e}")
            import traceback
            traceback.print_exc()

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text"""
        try:
            embedding = self.embedding_model.encode(text, convert_to_tensor=False)
            return embedding.astype(np.float32)
        except Exception as e:
            print(f"[ERROR] Failed to get embedding: {e}")
            return np.zeros(self.embedding_dim, dtype=np.float32)

    def add_transcript(self, job_id: str, speaker: str, start: float, end: float, text: str) -> None:
        """Add transcript to database and FAISS index"""
        with self.lock:
            # Add to database
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO transcripts (job_id, speaker, start, end, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (job_id, speaker, start, end, text, datetime.utcnow().isoformat()))
            
            conn.commit()
            conn.close()
            
            # Add to FAISS index
            doc_id = f"transcript_{job_id}_{uuid.uuid4().hex[:8]}"
            embedding = self.get_embedding(text)
            
            document = Document(
                id=doc_id,
                text=text,
                metadata={
                    "type": "transcript",
                    "job_id": job_id,
                    "speaker": speaker,
                    "start": start,
                    "end": end,
                    "created_at": datetime.utcnow().isoformat()
                },
                embedding=embedding
            )
            
            self.document_store[doc_id] = document
            self.faiss_index.add(embedding.reshape(1, -1))
            
            # Save FAISS index periodically
            if self.faiss_index.ntotal % 10 == 0:
                self._save_faiss_index()

    def add_memory(self, title: str, body: str) -> str:
        """Add memory to database and FAISS index"""
        with self.lock:
            memory_id = str(uuid.uuid4())
            
            # Add to database
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO memories (id, title, body, created_at)
                VALUES (?, ?, ?, ?)
            """, (memory_id, title, body, datetime.utcnow().isoformat()))
            
            conn.commit()
            conn.close()
            
            # Add to FAISS index
            doc_id = f"memory_{memory_id}"
            text = f"{title}\n{body}"
            embedding = self.get_embedding(text)
            
            document = Document(
                id=doc_id,
                text=text,
                metadata={
                    "type": "memory",
                    "memory_id": memory_id,
                    "title": title,
                    "body": body,
                    "created_at": datetime.utcnow().isoformat()
                },
                embedding=embedding
            )
            
            self.document_store[doc_id] = document
            self.faiss_index.add(embedding.reshape(1, -1))
            
            # Save FAISS index
            self._save_faiss_index()
            
            return memory_id

    def add_transcript(
        self,
        text: str,
        segments: List[Dict[str, Any]],
        job_id: str,
        session_id: str,
        audio_duration: float
    ) -> int:
        """
        Store transcription with segments in database
        
        Args:
            text: Full transcribed text
            segments: List of segment dicts with speaker, text, timing, emotion
            job_id: Unique job identifier  
            session_id: Session identifier
            audio_duration: Duration in seconds
        
        Returns:
            transcript_id: Database ID of stored transcript
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            try:
                # Create transcript_records table if it doesn't exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transcript_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT UNIQUE,
                        session_id TEXT,
                        full_text TEXT,
                        audio_duration REAL,
                        timestamp TEXT,
                        created_at TEXT
                    )
                """)
                
                # Create transcript_segments table if it doesn't exist (enhanced segments)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transcript_segments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transcript_id INTEGER,
                        seq INTEGER,
                        start_time REAL,
                        end_time REAL,
                        text TEXT,
                        speaker TEXT,
                        speaker_confidence REAL,
                        emotion TEXT,
                        emotion_confidence REAL,
                        emotion_scores TEXT,
                        created_at TEXT,
                        FOREIGN KEY (transcript_id) REFERENCES transcript_records (id)
                    )
                """)
                
                # Insert main transcript record
                timestamp = datetime.utcnow().isoformat()
                cur.execute("""
                    INSERT INTO transcript_records 
                    (job_id, session_id, full_text, audio_duration, timestamp, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (job_id, session_id, text, audio_duration, timestamp, timestamp))
                
                transcript_id = cur.lastrowid
                
                # Insert segments
                for i, seg in enumerate(segments):
                    emotion_scores_json = json.dumps(seg.get('emotions', {}))
                    cur.execute("""
                        INSERT INTO transcript_segments 
                        (transcript_id, seq, start_time, end_time, text, speaker, 
                         speaker_confidence, emotion, emotion_confidence, emotion_scores, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        transcript_id, i,
                        seg.get('start', 0.0),
                        seg.get('end', 0.0),
                        seg.get('text', ''),
                        seg.get('speaker', 'SPK'),
                        seg.get('speaker_confidence'),
                        seg.get('emotion', 'neutral'),
                        seg.get('emotion_confidence', 0.0),
                        emotion_scores_json,
                        timestamp
                    ))
                
                # Also store in legacy transcripts table for backward compatibility
                for seg in segments:
                    cur.execute("""
                        INSERT INTO transcripts (job_id, speaker, start, end, text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        job_id,
                        seg.get('speaker', 'SPK'),
                        seg.get('start', 0.0),
                        seg.get('end', 0.0),
                        seg.get('text', ''),
                        timestamp
                    ))
                
                conn.commit()
                print(f"[DB] Stored transcript {transcript_id} with {len(segments)} segments")
                return transcript_id
                
            except Exception as e:
                print(f"[DB ERROR] Failed to store transcript: {e}")
                conn.rollback()
                raise
            finally:
                conn.close()

    def _save_faiss_index(self) -> None:
        """Save FAISS index and document store to disk"""
        try:
            faiss.write_index(self.faiss_index, self.faiss_index_path)
            
            # Save document store
            doc_store_path = f"{self.faiss_index_path}.docs"
            docs_data = {}
            for doc_id, doc in self.document_store.items():
                docs_data[doc_id] = {
                    'id': doc.id,
                    'text': doc.text,
                    'metadata': doc.metadata,
                    'embedding': doc.embedding.tolist() if doc.embedding is not None else None
                }
            
            with open(doc_store_path, 'w', encoding='utf-8') as f:
                json.dump(docs_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[ERROR] Failed to save FAISS index: {e}")

    def _search_with_faiss(self, query: str, limit: int) -> List[Tuple[float, str]]:
        """Internal method to perform a raw search against the FAISS index."""
        if self.faiss_index.ntotal == 0:
            return []

        query_embedding = self.get_embedding(query).reshape(1, -1)
        # Normalize for cosine similarity search with an IP index
        faiss.normalize_L2(query_embedding)

        scores, indices = self.faiss_index.search(query_embedding, limit)

        # Get the mapping from FAISS's internal index to our document IDs
        doc_ids = list(self.document_store.keys())

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1:
                results.append((float(score), doc_ids[idx]))
        return results

    def search_documents(self, query: str, limit: int = 5, doc_type: Optional[str] = None):
        """
        Primary, high-speed search function. Uses FAISS and then filters.
        """
        # Fetch a larger number of results from FAISS to ensure we have enough after filtering.
        candidate_limit = max(20, limit * 3)

        try:
            # 1. Get top candidates from FAISS
            raw_results = self._search_with_faiss(query, candidate_limit)

            # 2. Hydrate and filter the results
            hydrated_results = []
            for score, doc_id in raw_results:
                doc = self.document_store.get(doc_id)
                if not doc:
                    continue

                # Filter by doc_type if required
                if doc_type and doc.metadata.get('type') != doc_type:
                    continue

                hydrated_results.append({
                    'id': doc.id,
                    'text': doc.text,
                    'metadata': doc.metadata,
                    'score': score,
                })

                if len(hydrated_results) >= limit:
                    break # Stop once we have enough results

            return hydrated_results

        except Exception as e:
            print(f"[ERROR] Document search failed: {e}")
            return []

    def answer_question(self, question: str, session_id: str = "default") -> Tuple[str, str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Answer question using RAG approach"""
        try:
            # Search for relevant documents
            search_results = self.search_documents(question, limit=self.top_k_hits)
            
            if not search_results:
                return "No relevant information found in the knowledge base.", "", [], []
            
            # Separate transcript and memory hits
            transcript_hits = []
            memory_hits = []
            
            for result in search_results:
                if result["metadata"].get("type") == "transcript":
                    transcript_hits.append({
                        "text": result["text"],
                        "speaker": result["metadata"].get("speaker", "Unknown"),
                        "score": result["score"]
                    })
                elif result["metadata"].get("type") == "memory":
                    memory_hits.append({
                        "title": result["metadata"].get("title", ""),
                        "body": result["metadata"].get("body", ""),
                        "score": result["score"]
                    })
            
            # Build context with strict token limits (max 1000 tokens for context)
            context_parts = []
            max_context_tokens = 1000  # Conservative limit for Gemma 4096 context window
            
            if transcript_hits:
                context_parts.append("Recent conversations:")
                for hit in transcript_hits[:1]:  # Only top 1 transcript hit
                    # Truncate each hit to fit token budget
                    text = truncate_to_tokens(hit['text'], 200)  # 200 tokens per hit
                    context_parts.append(f"- {hit['speaker']}: {text}")
            
            if memory_hits:
                context_parts.append("\nRelevant memories:")
                for hit in memory_hits[:1]:  # Only top 1 memory hit
                    # Truncate memory content to fit token budget
                    body = truncate_to_tokens(hit['body'], 200)  # 200 tokens per memory
                    context_parts.append(f"- {hit['title']}: {body}")
            
            context = "\n".join(context_parts)
            
            # Add conversation history (heavily truncated)
            conversation_context = self.conversations.context(session_id)
            if conversation_context:
                # Truncate conversation history to fit remaining token budget
                remaining_tokens = max_context_tokens - count_tokens(context)
                if remaining_tokens > 100:  # Only add if we have enough tokens left
                    conversation_context = truncate_to_tokens(conversation_context, remaining_tokens - 50)
                    context = f"Previous conversation:\n{conversation_context}\n\n{context}"
            
            # Final safety check - ensure total context is under token limit
            if count_tokens(context) > max_context_tokens:
                context = truncate_to_tokens(context, max_context_tokens)
            
            # Generate answer using Gemma
            answer, error = self._generate_answer(question, context, session_id)
            
            # Store conversation
            if answer and not error:
                self.conversations.add(session_id, question, answer)
            
            return answer, error, transcript_hits, memory_hits
            
        except Exception as e:
            return "", f"Error processing question: {str(e)}", [], []

    def _generate_answer(self, question: str, context: str, session_id: str) -> Tuple[str, str]:
        """Generate answer using Gemma with two-stage prompting"""
        if self._llm is None:
            return "", "LLM not available"
        
        try:
            # Stage 1: Check if context is relevant
            relevance_check = self._check_context_relevance(question, context)
            if not relevance_check:
                return "The provided context does not contain information relevant to your question.", ""
            
            # Stage 2: Generate full answer
            return self._generate_full_answer(question, context)
            
        except Exception as e:
            return "", f"Generation error: {str(e)}"

    def _check_context_relevance(self, question: str, context: str) -> bool:
        """Check if context contains relevant information"""
        max_retries = 3
        
        # Use proper token counting for relevance check
        max_question_tokens = 100
        max_context_tokens = 500
        
        question = truncate_to_tokens(question, max_question_tokens)
        context = truncate_to_tokens(context, max_context_tokens)
        
        for attempt in range(max_retries):
            emphasis = "YES OR NO ONLY. " * (attempt + 1)
            prompt = f"""Is the answer to this question: "{question}" contained in this context?

{emphasis}Answer with only "yes" or "no".

Context: {context}

Answer:"""

            try:
                with self.llm_lock:
                    response = self._llm(
                        prompt=prompt,
                        max_tokens=5,
                        temperature=0.0,
                        top_p=1.0,
                        repeat_penalty=1.0,
                        stop=[],
                    )
                
                if response:
                    if isinstance(response, dict) and "choices" in response:
                        raw_text = response["choices"][0]["text"]
                    elif isinstance(response, dict) and "text" in response:
                        raw_text = response["text"]
                    elif hasattr(response, 'text'):
                        raw_text = response.text
                    else:
                        raw_text = str(response)
                    
                    answer = str(raw_text).strip().lower()
                    print(f"[DEBUG] Relevance check attempt {attempt + 1}: '{answer}'")
                    
                    if answer in ['yes', 'y']:
                        return True
                    elif answer in ['no', 'n']:
                        return False
                    else:
                        print(f"[DEBUG] Invalid response '{answer}', retrying...")
                        continue
                        
            except Exception as e:
                print(f"[DEBUG] Error in relevance check attempt {attempt + 1}: {e}")
                continue
        
        print("[DEBUG] All relevance check attempts failed, defaulting to True")
        return True

    def _generate_full_answer(self, question: str, context: str) -> Tuple[str, str]:
        """Generate full answer after confirming context relevance"""
        # Use proper token counting for Gemma 4096 context window
        # Reserve tokens: 1000 for context, 500 for question, 500 for prompt template, 2000 for response
        max_context_tokens = 1000
        max_question_tokens = 500
        max_response_tokens = 512
        
        # Truncate context to fit token budget
        context = truncate_to_tokens(context, max_context_tokens)
        
        # Truncate question to fit token budget
        question = truncate_to_tokens(question, max_question_tokens)
        
        prompt = f"""You are a helpful AI assistant with access to stored memories and transcripts. Answer questions based on the provided context. Be direct, helpful, and cite relevant information when available.

Context: {context}

Question: {question}

Answer:"""

        # Final safety check - ensure total prompt is under 3000 tokens
        total_tokens = count_tokens(prompt)
        if total_tokens > 3000:
            # Emergency truncation
            context = truncate_to_tokens(context, 500)
            question = truncate_to_tokens(question, 200)
            prompt = f"""Answer this question based on the context:

Context: {context}

Question: {question}

Answer:"""

        try:
            print("[LLM] generate_full_answer: calling LLM")
            print(f"[LLM] Prompt length: {len(prompt)} chars, tokens: {count_tokens(prompt)}")
            with self.llm_lock:
                response = self._llm(
                    prompt=prompt,
                    max_tokens=max_response_tokens,
                    temperature=0.2,
                    top_p=0.85,
                    repeat_penalty=1.1,
                    stop=["\n\nQuestion:", "\n\nContext:", "\n\n---", "Question:", "Context:"],
                )
            print(f"[LLM] generate_full_answer: LLM responded with type: {type(response)}")
            print(f"[LLM] Response content: '{response}'")
            print(f"[LLM] Response length: {len(str(response)) if response else 0}")
            
            if response:
                if isinstance(response, dict) and "choices" in response:
                    raw_text = response["choices"][0]["text"]
                elif isinstance(response, dict) and "text" in response:
                    raw_text = response["text"]
                elif hasattr(response, 'text'):
                    raw_text = response.text
                else:
                    raw_text = str(response)
                
                print(f"[LLM] Raw response text: '{raw_text}'")
                answer = str(raw_text).strip()
                print(f"[LLM] Cleaned answer: '{answer}'")
                
                # Clean up response
                if answer.startswith("Answer:"):
                    answer = answer[7:].strip()
                    print(f"[LLM] After removing 'Answer:': '{answer}'")
                
                # Ensure valid UTF-8
                try:
                    answer = answer.encode('utf-8', errors='ignore').decode('utf-8')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    answer = answer.encode('utf-8', errors='replace').decode('utf-8')
                
                print(f"[LLM] Final answer being returned: '{answer}'")
                return answer, ""
            
            print("[LLM] ERROR: No response generated - returning empty answer")
            return "", "No response generated"
            
        except Exception as e:
            return "", f"Generation error: {str(e)}"

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for session"""
        self.conversations.clear(session_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        # Query actual counts from database
        memory_count = 0
        transcript_count = 0
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM memories")
            memory_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM transcripts")
            transcript_count = cur.fetchone()[0]
            conn.close()
        except Exception as e:
            print(f"[STATS] Error querying database counts: {e}")
        
        return {
            "total_documents": self.faiss_index.ntotal,
            "memory_count": memory_count,
            "transcript_count": transcript_count,
            "embedding_model": self.embedding_model_name,
            "llm_available": self._llm is not None,
            "faiss_index_path": self.faiss_index_path
        }

# -----------------------------------------------------------------------------
# Compatibility layer for main3.py (DB schema + helper methods)
# -----------------------------------------------------------------------------

from typing import Callable


def _compat_now_iso(self) -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _compat_connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _compat_init_db(self) -> None:
    with self.lock:
        conn = self._connect()
        cur = conn.cursor()
        # Base tables
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                speaker TEXT,
                start REAL,
                end REAL,
                text TEXT,
                created_at TEXT
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                body TEXT,
                created_at TEXT
            )
            '''
        )
        # Add expected columns if missing
        def _ensure_column(table: str, column: str, decl: str) -> None:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            except sqlite3.OperationalError:
                pass
        _ensure_column('transcripts', 'embedding', 'BLOB')
        _ensure_column('transcripts', 'dominant_emotion', 'TEXT')
        _ensure_column('transcripts', 'emotion_confidence', 'REAL')
        _ensure_column('transcripts', 'emotion_scores', 'TEXT')
        _ensure_column('memories', 'tags', 'TEXT')
        _ensure_column('memories', 'source_job_id', 'TEXT')
        _ensure_column('memories', 'embedding', 'BLOB')
        _ensure_column('memories', 'speaker_id', 'TEXT')
        _ensure_column('memories', 'owner_user_id', 'TEXT')
        # Job bundles
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS job_transcripts (
                job_id TEXT PRIMARY KEY,
                full_text TEXT,
                raw_json TEXT,
                created_at TEXT
            )
            '''
        )
        # Indexes
        cur.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_job_id ON transcripts(job_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)')
        conn.commit()
        conn.close()


# Install patched methods before any instantiation
AdvancedMemoryService.now_iso = _compat_now_iso
AdvancedMemoryService._connect = _compat_connect
AdvancedMemoryService._init_db = _compat_init_db


def _compat_save_segments(self, result: Dict[str, Any], job_id: str, log_callback: Optional[Callable[[str], None]] = None) -> None:
    segments = result.get('segments') or []
    if not segments:
        return

    rows_to_insert: List[Tuple] = []
    for segment in segments:
        text = (segment.get('text') or '').strip()
        if not text:
            continue
        speaker = (segment.get('speaker') or 'UNKNOWN').strip()
        start = float(segment.get('start', 0.0) or 0.0)
        end = float(segment.get('end', 0.0) or 0.0)
        emb = self.get_embedding(text)
        
        # Extract emotion data from segment
        dominant_emotion = segment.get('emotion', 'neutral')
        emotion_confidence = segment.get('emotion_confidence', 0.0)
        emotion_scores = json.dumps(segment.get('emotions', {}))
        
        rows_to_insert.append((job_id, speaker, start, end, text, emb.astype(np.float32).tobytes(), self.now_iso(), 
                    dominant_emotion, emotion_confidence, emotion_scores))
        
        # Update FAISS/doc store (can remain in the loop)
        doc_id = f"transcript_{job_id}_{uuid.uuid4().hex[:8]}"
        self.document_store[doc_id] = Document(
            id=doc_id,
            text=text,
            metadata={
                'type': 'transcript',
                'job_id': job_id,
                'speaker': speaker,
                'start': start,
                'end': end,
                'created_at': self.now_iso(),
                'dominant_emotion': dominant_emotion,
                'emotion_confidence': emotion_confidence,
                'emotion_scores': emotion_scores,
            },
            embedding=emb,
        )
        self.faiss_index.add(emb.reshape(1, -1))
        if callable(log_callback):
            try:
                log_callback(f"[{self.now_iso()}] ({job_id}) {speaker}: {text} [emotion: {dominant_emotion}]")
            except Exception:
                pass

    if rows_to_insert:
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            try:
                cur.executemany(
                    '''
                    INSERT INTO transcripts (job_id, speaker, start, end, text, embedding, created_at, dominant_emotion, emotion_confidence, emotion_scores)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    rows_to_insert,
                )
                conn.commit()
            finally:
                conn.close()
    
    if self.faiss_index.ntotal % 20 == 0:
        self._save_faiss_index()

AdvancedMemoryService.save_segments = _compat_save_segments


def _compat_save_job_bundle(self, job_id: str, full_text: str, result: Dict[str, Any]) -> None:
    with self.lock:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT OR REPLACE INTO job_transcripts (job_id, full_text, raw_json, created_at)
            VALUES (?, ?, ?, ?)
            ''',
            (job_id, full_text, json.dumps(result, ensure_ascii=False), self.now_iso()),
        )
        conn.commit()
        conn.close()


AdvancedMemoryService.save_job_bundle = _compat_save_job_bundle


def _compat_maybe_autocreate_memory(self, text: str, job_id: str) -> None:
    if not text:
        return
    low = text.lower()
    triggers = ['remember', 'note this', 'note:', 'todo:', 'action item', 'task:', 'deadline', 'buy', 'order']
    if not any(tok in low for tok in triggers):
        return
    snippet = text.strip().split('\n')[0].strip()
    if len(snippet) > 200:
        snippet = snippet[:197] + '...'
    emb = self.get_embedding(snippet)
    with self.lock:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO memories (title, body, tags, source_job_id, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('Note', snippet, json.dumps(['auto', 'from_transcript']), job_id, emb.astype(np.float32).tobytes(), self.now_iso()),
        )
        conn.commit()
        conn.close()


AdvancedMemoryService.maybe_autocreate_memory = _compat_maybe_autocreate_memory


from emotion_analyzer import analyze_emotion

def _compat_save_ingest_line(self, text: str, speaker: str, timestamp: str) -> None:
    emb = self.get_embedding(text)
    job_id = f"ingest-{uuid.uuid4().hex[:8]}"
    
    emotion_data = analyze_emotion(text)
    dominant_emotion = emotion_data.get('dominant_emotion', 'neutral')
    emotion_confidence = emotion_data.get('confidence', 0.0)
    emotion_scores = json.dumps(emotion_data.get('emotions', {}))
    
    with self.lock:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO transcripts (job_id, speaker, start, end, text, embedding, created_at, dominant_emotion, emotion_confidence, emotion_scores)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (job_id, speaker, None, None, text, emb.astype(np.float32).tobytes(), timestamp or self.now_iso(),
             dominant_emotion, emotion_confidence, emotion_scores),
        )
        conn.commit()
        conn.close()
    # Update FAISS
    doc_id = f"transcript_{job_id}_{uuid.uuid4().hex[:8]}"
    self.document_store[doc_id] = Document(
        id=doc_id,
        text=text,
        metadata={
            'type': 'transcript', 
            'job_id': job_id, 
            'speaker': speaker, 
            'created_at': timestamp or self.now_iso(),
            'dominant_emotion': dominant_emotion,
            'emotion_confidence': emotion_confidence,
            'emotion_scores': emotion_scores,
        },
        embedding=emb,
    )
    self.faiss_index.add(emb.reshape(1, -1))
    if self.faiss_index.ntotal % 20 == 0:
        self._save_faiss_index()


AdvancedMemoryService.save_ingest_line = _compat_save_ingest_line


def _compat_cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def search_transcripts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search transcripts by query using the FAISS index."""
    return self.search_documents(query, limit, doc_type='transcript')


def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search memories by query using the FAISS index."""
    return self.search_documents(query, limit, doc_type='memory')


AdvancedMemoryService.search_transcripts = search_transcripts
AdvancedMemoryService.search_memories = search_memories

# List all memories with pagination
def list_memories(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """List all memories with pagination"""
    with self.lock:
        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Get memories from database
            cur.execute(
                "SELECT id, title, body, created_at, speaker_id, owner_user_id FROM memories WHERE body IS NOT NULL AND body != '' ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            memories = cur.fetchall()
            
            conn.close()
            
            # Convert to result format - return just the list (not wrapped in dict)
            results = []
            for memory in memories:
                results.append({
                    "id": memory['id'],
                    "title": memory['title'] or 'Untitled',
                    "content": memory['body'] or '',
                    "timestamp": memory['created_at'] or '',
                    "created_at": memory['created_at'] or '',
                    "speaker_id": memory['speaker_id'],
                    "owner_user_id": memory['owner_user_id']
                })
            
            return results
        except Exception as e:
            print(f"[LIST_MEMORIES] Error: {e}")
            return []

AdvancedMemoryService.list_memories = list_memories

# Rebuild FAISS index from DB (full sync)

def _compat_rebuild_index_from_db(self) -> None:
    with self.lock:
        try:
            # Reset index and store
            self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)
            self.document_store.clear()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Transcripts
            cur.execute("SELECT job_id, speaker, start, end, text, created_at FROM transcripts WHERE text IS NOT NULL AND text != ''")
            transcripts = cur.fetchall()
            embeddings_to_add = []
            for t in transcripts:
                text = t['text']
                if len((text or '').strip()) < 3:
                    continue
                emb = self.get_embedding(text)
                doc_id = f"transcript_{t['job_id']}_{uuid.uuid4().hex[:8]}"
                self.document_store[doc_id] = Document(
                    id=doc_id,
                    text=text,
                    metadata={
                        'type': 'transcript',
                        'job_id': t['job_id'],
                        'speaker': t['speaker'],
                        'start': t['start'],
                        'end': t['end'],
                        'created_at': t['created_at'] or self.now_iso(),
                    },
                    embedding=emb,
                )
                embeddings_to_add.append(emb)
            # Memories
            cur.execute("SELECT id, title, body, created_at FROM memories WHERE body IS NOT NULL AND body != ''")
            memories = cur.fetchall()
            for m in memories:
                text = f"{m['title'] or ''}\n{m['body'] or ''}"
                if len(text.strip()) < 3:
                    continue
                emb = self.get_embedding(text)
                doc_id = f"memory_{m['id']}"
                self.document_store[doc_id] = Document(
                    id=doc_id,
                    text=text,
                    metadata={
                        'type': 'memory',
                        'memory_id': m['id'],
                        'title': m['title'],
                        'body': m['body'],
                        'created_at': m['created_at'] or self.now_iso(),
                    },
                    embedding=emb,
                )
                embeddings_to_add.append(emb)
            conn.close()
            if embeddings_to_add:
                arr = np.vstack(embeddings_to_add).astype(np.float32)
                self.faiss_index.add(arr)
                self._save_faiss_index()
            print(f"[REBUILD] Rebuilt FAISS index with {self.faiss_index.ntotal} documents")
        except Exception as e:
            print(f"[REBUILD] Failed to rebuild FAISS: {e}")

AdvancedMemoryService.rebuild_index_from_db = _compat_rebuild_index_from_db

# Enhanced answer_question that leverages conversation history to guide retrieval
from typing import Tuple as _Tuple, List as _List, Dict as _Dict

def _compat_answer_question(self, question: str, session_id: str = 'default') -> _Tuple[str, str, _List[_Dict[str, any]], _List[_Dict[str, any]]]:
    try:
        # Primary search with raw question
        search_results = self.search_documents(question, limit=self.top_k_hits)
        # If we have conversation context, do a context-augmented search too
        conv_ctx = self.conversations.context(session_id)
        if conv_ctx:
            aug_query = f"{question}\n{conv_ctx}"
            aug_results = self.search_documents(aug_query, limit=self.top_k_hits)
            # Merge unique results by id, preferring higher score
            tmp = {}
            for r in (search_results + aug_results):
                rid = r.get('id')
                if rid not in tmp or r.get('score', 0) > tmp[rid].get('score', 0):
                    tmp[rid] = r
            search_results = list(tmp.values())
            # sort by score descending
            search_results.sort(key=lambda x: x.get('score', 0), reverse=True)

        if not search_results:
            return "No relevant information found in the knowledge base.", "", [], []

        # Build hits
        transcript_hits = []
        memory_hits = []
        for result in search_results:
            if result.get('metadata', {}).get('type') == 'transcript':
                transcript_hits.append({
                    'text': result.get('text', ''),
                    'speaker': result.get('metadata', {}).get('speaker', 'Unknown'),
                    'score': result.get('score')
                })
            elif result.get('metadata', {}).get('type') == 'memory':
                memory_hits.append({
                    'title': result.get('metadata', {}).get('title', ''),
                    'body': result.get('metadata', {}).get('body', ''),
                    'score': result.get('score')
                })

        # Create context
        parts = []
        if transcript_hits:
            parts.append('Recent conversations:')
            for hit in transcript_hits[:3]:
                parts.append(f"- {hit['speaker']}: {hit['text']}")
        if memory_hits:
            parts.append('\nRelevant memories:')
            for hit in memory_hits[:3]:
                parts.append(f"- {hit['title']}: {hit['body']}")
        context = '\n'.join(parts)
        # Add conversation history upfront
        if conv_ctx:
            context = f"Previous conversation:\n{conv_ctx}\n\n{context}" if context else conv_ctx

        # Loosen relevance gate: if we have any hits, skip gate
        answer, error = self._generate_full_answer(question, context)
        if not answer and not error:
            # fallback to strict gate
            answer, error = self._generate_answer(question, context, session_id)

        if answer and not error:
            self.conversations.add(session_id, question, answer)
        return answer, error, transcript_hits, memory_hits
    except Exception as e:
        return "", f"Error processing question: {str(e)}", [], []

AdvancedMemoryService.answer_question = _compat_answer_question

# Override search_documents to avoid FAISS->doc mapping issues by scoring in Python

def _compat_search_documents(self, query: str, limit: int = 5):
    try:
        q = self.get_embedding(query)
        qn = q / (np.linalg.norm(q) + 1e-8)
        results = []
        for doc in self.document_store.values():
            emb = doc.embedding
            if emb is None:
                continue
            dn = emb / (np.linalg.norm(emb) + 1e-8)
            score = float(np.dot(qn, dn))
            results.append({
                'id': doc.id,
                'text': doc.text,
                'metadata': doc.metadata,
                'score': score,
            })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[: max(1, limit)]
    except Exception as e:
        print(f"[ERROR] Python search_documents failed: {e}")
        return []

AdvancedMemoryService.search_documents = _compat_search_documents

# Add heuristic augmented search for follow-ups

def _compat_answer_question_v2(self, question: str, session_id: str = 'default'):
    try:
        conv_ctx = self.conversations.context(session_id)
        results = []
        # base
        results.extend(self.search_documents(question, limit=self.top_k_hits))
        # augmented with conversation
        if conv_ctx:
            aug_query = f"{question}\n{conv_ctx}"
            results.extend(self.search_documents(aug_query, limit=self.top_k_hits))
            # heuristic if follow-up words present
            qlow = question.lower()
            if any(k in qlow for k in ['solve','solution','propos','cover']):
                heuristic = 'zero downtime solution plan proposed cover fix cutover blue-green deployment replicas failover ha rolling update'
                # if context mentions zero downtime explicitly, bias query
                if 'zero downtime' in conv_ctx.lower():
                    aug2 = heuristic
                else:
                    aug2 = question + ' ' + heuristic
                results.extend(self.search_documents(aug2, limit=self.top_k_hits))
        # dedupe by id with best score
        by_id = {}
        for r in results:
            rid = r.get('id')
            if rid not in by_id or r.get('score',0) > by_id[rid].get('score',0):
                by_id[rid] = r
        search_results = list(by_id.values())
        search_results.sort(key=lambda x: x.get('score',0), reverse=True)
        if not search_results:
            return "No relevant information found in the knowledge base.", "", [], []
        transcript_hits, memory_hits = [], []
        for r in search_results:
            m = r.get('metadata',{})
            if m.get('type')=='transcript':
                transcript_hits.append({'text': r.get('text',''), 'speaker': m.get('speaker','Unknown'), 'score': r.get('score')})
            elif m.get('type')=='memory':
                memory_hits.append({'title': m.get('title',''), 'body': m.get('body',''), 'score': r.get('score')})
        # build context
        parts=[]
        if transcript_hits:
            parts.append('Recent conversations:')
            for hit in transcript_hits[:3]: parts.append(f"- {hit['speaker']}: {hit['text']}")
        if memory_hits:
            parts.append('\nRelevant memories:')
            for hit in memory_hits[:3]: parts.append(f"- {hit['title']}: {hit['body']}")
        context='\n'.join(parts)
        if conv_ctx: context = f"Previous conversation:\n{conv_ctx}\n\n{context}" if context else conv_ctx
        # generate directly (skip strict gate)
        answer, error = self._generate_full_answer(question, context)
        if answer and not error:
            self.conversations.add(session_id, question, answer)
        return answer, error, transcript_hits, memory_hits
    except Exception as e:
        return "", f"Error processing question: {str(e)}", [], []

AdvancedMemoryService.answer_question = _compat_answer_question_v2

# Core document search (embedding similarity)


def _compat_search_documents_generic(self, query: str, limit: int = 5, doc_type: Optional[str] = None):
    try:
        query_vec = self.get_embedding(query)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        scored = []
        for document in self.document_store.values():
            embedding = document.embedding
            if embedding is None:
                continue
            emb_norm = embedding / (np.linalg.norm(embedding) + 1e-8)
            score = float(np.dot(query_norm, emb_norm))
            scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        seen = set()
        for score, document in scored:
            if document.id in seen:
                continue
            seen.add(document.id)
            
            # Filter by doc_type if provided
            if doc_type and document.metadata.get('type') != doc_type:
                continue

            results.append({
                'id': document.id,
                'text': document.text,
                'metadata': document.metadata,
                'score': score,
            })
            if len(results) >= max(1, limit):
                break
        return results
    except Exception as e:
        print(f"[ERROR] Generic search_documents failed: {e}")
        return []

AdvancedMemoryService.search_documents = _compat_search_documents_generic



# Fix add_memory to use autoincrement id and persist FAISS/doc store

from emotion_analyzer import analyze_emotion

def _compat_add_memory(self, title: str, body: str, **kwargs) -> int:
    speaker_id = kwargs.get("speaker_id")
    owner_user_id = kwargs.get("owner_user_id")
    metadata = kwargs.get("metadata") or {}
    with self.lock:
        conn = self._connect()
        cur = conn.cursor()
        emb = self.get_embedding(f"{title}\n{body}")
        
        # Analyze emotion for the memory content
        emotion_data = analyze_emotion(f"{title}\n{body}")
        dominant_emotion = emotion_data.get('dominant_emotion', 'neutral')
        emotion_confidence = emotion_data.get('confidence', 0.0)
        emotion_scores = json.dumps(emotion_data.get('emotions', {}))
        
        try:
            cur.execute(
                '''
                INSERT INTO memories (title, body, tags, source_job_id, embedding, created_at, dominant_emotion, emotion_confidence, emotion_scores, speaker_id, owner_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (title, body, json.dumps(metadata.get("tags", [])), metadata.get("source_job_id", 'manual'),
                 emb.astype(np.float32).tobytes(), self.now_iso(), 
                 dominant_emotion, emotion_confidence, emotion_scores, speaker_id, owner_user_id),
            )
            memory_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        doc_id = f"memory_{memory_id}"
        text = f"{title}\n{body}"
        document = Document(
            id=doc_id,
            text=text,
            metadata={
                'type': 'memory',
                'memory_id': memory_id,
                'title': title,
                'body': body,
                'created_at': self.now_iso(),
                'dominant_emotion': dominant_emotion,
                'emotion_confidence': emotion_confidence,
                'emotion_scores': emotion_scores,
                'speaker_id': speaker_id,
                'owner_user_id': owner_user_id,
                'metadata': metadata,
            },
            embedding=emb,
        )
        self.document_store[doc_id] = document
        self.faiss_index.add(emb.reshape(1, -1))
        self._save_faiss_index()
        return memory_id

AdvancedMemoryService.add_memory = _compat_add_memory

def _compat_answer_question_v3(self, question: str, session_id: str = "default"):
    try:
        conv_ctx = self.conversations.context(session_id)
        queries = [question]
        if conv_ctx:
            queries.append(f"{question}\n{conv_ctx}")
        aggregated = {}
        fetch_limit = max(20, self.top_k_hits * 10)
        for q in queries:
            for item in self.search_documents(q, limit=fetch_limit):
                doc_id = item.get('id')
                if doc_id not in aggregated or item.get('score', 0) > aggregated[doc_id].get('score', 0):
                    aggregated[doc_id] = item
            for row in self.search_memories(q, limit=self.top_k_hits):
                doc_id = f"memory_row_{row.get('id')}"
                metadata = {
                    'type': 'memory',
                    'title': row.get('title', ''),
                    'body': row.get('body', ''),
                    'source_job_id': row.get('source_job_id'),
                }
                aggregated[doc_id] = {
                    'id': doc_id,
                    'text': row.get('body', ''),
                    'metadata': metadata,
                    'score': row.get('score', 0),
                }
            for row in self.search_transcripts(q, limit=self.top_k_hits):
                doc_id = f"transcript_row_{row.get('id')}"
                metadata = {
                    'type': 'transcript',
                    'speaker': row.get('speaker', 'Unknown'),
                    'start': row.get('start'),
                    'end': row.get('end'),
                    'job_id': row.get('job_id'),
                }
                aggregated[doc_id] = {
                    'id': doc_id,
                    'text': row.get('text', ''),
                    'metadata': metadata,
                    'score': row.get('score', 0),
                }
        related_job_ids = {
            item.get('metadata', {}).get('job_id')
            for item in aggregated.values()
            if item.get('metadata', {}).get('type') == 'transcript' and item.get('metadata', {}).get('job_id')
        }
        related_job_ids.discard(None)
        if related_job_ids:
            query_vec = self.get_embedding(question)
            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
            for document in self.document_store.values():
                meta = document.metadata
                if meta.get('type') != 'transcript':
                    continue
                if meta.get('job_id') not in related_job_ids:
                    continue
                doc_id = document.id
                if doc_id in aggregated:
                    continue
                emb = document.embedding
                if emb is None:
                    continue
                emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
                score = float(np.dot(query_norm, emb_norm))
                aggregated[doc_id] = {
                    'id': doc_id,
                    'text': document.text,
                    'metadata': meta,
                    'score': score,
                }
        search_results = sorted(aggregated.values(), key=lambda x: x.get('score', 0), reverse=True)
        if not search_results:
            return "No relevant information found in the knowledge base.", "", [], []
        transcript_hits = []
        memory_hits = []
        seen_transcript_text = set()
        seen_memory_text = set()
        for result in search_results:
            meta = result.get('metadata', {})
            score = result.get('score')
            if meta.get('type') == 'transcript':
                text_value = (result.get('text') or '').strip()
                if len(text_value) < 3:
                    continue
                key = text_value.lower()
                if key in seen_transcript_text:
                    continue
                seen_transcript_text.add(key)
                transcript_hits.append({
                    'type': 'transcript',
                    'text': text_value,
                    'speaker': meta.get('speaker', 'Unknown'),
                    'score': score,
                })
            elif meta.get('type') == 'memory':
                body_value = (meta.get('body') or result.get('text') or '').strip()
                if len(body_value) < 3:
                    continue
                key = body_value.lower()
                if key in seen_memory_text:
                    continue
                seen_memory_text.add(key)
                memory_hits.append({
                    'type': 'memory',
                    'title': meta.get('title', ''),
                    'body': body_value,
                    'text': body_value,
                    'score': score,
                })
        parts = []
        if transcript_hits:
            parts.append('Recent conversations:')
            for hit in transcript_hits[:self.top_k_hits]:
                parts.append(f"- {hit['speaker']}: {hit['text']}")
        if memory_hits:
            parts.append('\nRelevant memories:')
            for hit in memory_hits[:self.top_k_hits]:
                parts.append(f"- {hit['title']}: {hit['body']}")
        context = '\n'.join(parts)
        if conv_ctx:
            context = f"Previous conversation:\n{conv_ctx}\n\n{context}" if context else conv_ctx
        answer, error = self._generate_full_answer(question, context)
        if answer and not error:
            self.conversations.add(session_id, question, answer)
        return answer, error, transcript_hits, memory_hits
    except Exception as e:
        return "", f"Error processing question: {str(e)}", [], []

AdvancedMemoryService.answer_question = _compat_answer_question_v3
