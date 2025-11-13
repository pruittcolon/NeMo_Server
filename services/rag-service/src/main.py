"""
RAG Service - FAISS Vector Search with Full Metadata Storage

Provides semantic search across transcripts with speaker, emotion, and audio metrics.
Enables natural language queries like "what did they say about wireless signal?"
"""

import os
import json
import sqlite3
import uuid
import threading
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set
from contextlib import asynccontextmanager
from pathlib import Path
import logging

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import sys
from shared.crypto.db_encryption import create_encrypted_db

# Add shared modules to path
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/src')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

JWT_ONLY = os.getenv("JWT_ONLY", "false").lower() in {"1", "true", "yes"}
DB_PATH = Path(os.getenv("DB_PATH", "/app/instance/rag.db"))
FAISS_INDEX_PATH = Path(os.getenv("FAISS_INDEX_PATH", "/app/faiss_index/index.bin"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension
EMAIL_ANALYZER_ENABLED = os.getenv("EMAIL_ANALYZER_ENABLED", "true").lower() in {"1", "true", "yes"}

# Global state
rag_service = None
service_auth = None

WORD_REGEX = re.compile(r"[A-Za-z0-9']+")
FILLER_PATTERNS = [
    re.compile(rf"\b{phrase}\b", re.IGNORECASE)
    for phrase in [
        "um",
        "uh",
        "er",
        "ah",
        "like",
        "you know",
        "i mean",
        "sort of",
        "kind of",
        "basically",
        "actually",
    ]
]


# ============================================================================
# DATA MODELS
# ============================================================================

class TranscriptSegment(BaseModel):
    """Single segment of a transcript"""
    text: str
    speaker: str
    start_time: float
    end_time: float
    emotion: Optional[str] = None
    emotion_confidence: Optional[float] = None
    emotion_scores: Optional[Dict[str, float]] = None
    audio_metrics: Optional[Dict[str, float]] = None  # pitch, energy, speaking_rate, etc.


class TranscriptIndexRequest(BaseModel):
    """Request to index a full transcript"""
    job_id: str
    session_id: str
    full_text: str
    audio_duration: float
    segments: List[TranscriptSegment]


class SemanticSearchRequest(BaseModel):
    """Request for semantic search"""
    query: str
    top_k: int = 5
    doc_type: Optional[str] = None  # 'transcript_segment' or 'memory'
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_n_transcripts: Optional[int] = None
    speakers: Optional[List[str]] = None
    bias_emotions: Optional[List[str]] = None


class MemoryAddRequest(BaseModel):
    """Request to add a memory/note"""
    title: str
    body: str
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# RAG SERVICE CLASS
# ============================================================================

class RAGService:
    """
    Vector-based RAG service with FAISS indexing
    
    Features:
    - Semantic search with sentence-transformers
    - FAISS vector index for fast similarity search
    - Full metadata storage (speaker, emotion, audio metrics)
    - Persistent storage (SQLite + FAISS)
    """
    
    def __init__(
        self,
        db_path: Path,
        faiss_index_path: Path,
        embedding_model_name: str = EMBEDDING_MODEL,
        db_encryption_key: Optional[str] = None,
    ):
        self.db_path = db_path
        self.faiss_index_path = faiss_index_path
        self.embedding_model_name = embedding_model_name
        self.embedding_dim = EMBEDDING_DIM

        # Thread safety
        self.lock = threading.RLock()

        # FAISS index and document store
        self.faiss_index = None
        self.document_store: Dict[str, Dict[str, Any]] = {}

        # Database (SQLCipher if key provided)
        self._db = create_encrypted_db(
            db_path=str(self.db_path),
            encryption_key=db_encryption_key,
            use_encryption=db_encryption_key is not None,
            connect_kwargs={"check_same_thread": False},
        )
        if self._db.use_encryption:
            logger.info("RAG database encryption ENABLED")
        else:
            logger.warning("RAG database encryption DISABLED")

        # Initialize components
        self._init_directories()
        self._init_database()
        self.emotion_column = "emotion"
        # Defer embeddings/FAISS until needed to speed startup
        self.embedding_model = None
        self.faiss_index = None
        self._detect_schema()
        if os.getenv("RAG_ENABLE_SEMANTIC", "true").lower() not in {"1", "true", "yes"}:
            logger.info("[RAG] Semantic indexing disabled via RAG_ENABLE_SEMANTIC=false")
        else:
            logger.info("[RAG] Semantic indexing enabled (lazy init)")
        
        logger.info("RAG Service initialized successfully")
        logger.info(f"[RAG] Using emotion column: {self.emotion_column}")
    
    def _init_directories(self):
        """Ensure required directories exist"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directories initialized: {self.db_path.parent}, {self.faiss_index_path.parent}")
    
    def _init_embedding_model(self):
        """Initialize SentenceTransformer for embeddings"""
        try:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            
            # Set cache folder to use models directory
            import os
            cache_folder = os.getenv("HF_HOME", "/app/models")
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = cache_folder
            
            # Load model (will use cache if available, download if not)
            self.embedding_model = SentenceTransformer(self.embedding_model_name, device='cpu', cache_folder=cache_folder)
            
            logger.info(f"Embedding model loaded successfully (CPU) from cache: {cache_folder}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def _init_database(self):
        """Initialize SQLite database schema"""
        with self.lock:
            conn = self._db.connect()
            try:
                module_name = getattr(conn.__class__, "__module__", "")
                if module_name.startswith("pysqlcipher3") or module_name.startswith("sqlcipher3"):
                    import sys as _sys
                    mod = _sys.modules.get(module_name)
                    row_cls = getattr(mod, 'Row', None)
                    if row_cls is not None:
                        conn.row_factory = row_cls
                    else:
                        def _dict_factory(cursor, row):
                            out = {}
                            desc = getattr(cursor, "description", None) or []
                            for idx, col in enumerate(desc):
                                name = col[0] if isinstance(col, (list, tuple)) else str(col)
                                out[name] = row[idx]
                            return out
                        conn.row_factory = _dict_factory
                else:
                    conn.row_factory = sqlite3.Row
            except Exception:
                try:
                    conn.row_factory = sqlite3.Row
                except Exception:
                    pass
            cur = conn.cursor()
            
            # Transcript records (full transcript metadata)
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
            
            # Transcript segments (individual segments with ALL metadata)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcript_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transcript_id INTEGER,
                    seq INTEGER,
                    text TEXT,
                    speaker TEXT,
                    start_time REAL,
                    end_time REAL,
                    speaker_confidence REAL,
                    emotion TEXT,
                    emotion_confidence REAL,
                    emotion_scores TEXT,
                    audio_metrics TEXT,
                    embedding BLOB,
                    doc_id TEXT UNIQUE,
                    created_at TEXT,
                    FOREIGN KEY (transcript_id) REFERENCES transcript_records(id)
                )
            """)
            self._ensure_segment_column_extensions(cur)
            
            # Memories table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT UNIQUE,
                    title TEXT,
                    body TEXT,
                    metadata TEXT,
                    embedding BLOB,
                    doc_id TEXT UNIQUE,
                    created_at TEXT
                )
            """)

            # Analysis artifacts table (stores persisted analyzer runs and meta-analyses)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analysis_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT UNIQUE,
                    analysis_id TEXT,
                    title TEXT,
                    body TEXT,
                    metadata TEXT,
                    embedding BLOB,
                    created_at TEXT
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_created_at
                ON analysis_artifacts(created_at)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_artifact_id
                ON analysis_artifacts(artifact_id)
            """)

            # Artifact chunks table (optional fine-grained retrieval)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analysis_artifact_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    token_estimate INTEGER,
                    embedding BLOB,
                    created_at TEXT,
                    UNIQUE(artifact_id, seq)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_artifact
                ON analysis_artifact_chunks(artifact_id, seq)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_created
                ON analysis_artifact_chunks(created_at)
            """)
            
            # Indexes for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_transcript ON transcript_segments(transcript_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_speaker ON transcript_segments(speaker)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_timestamp ON transcript_segments(start_time)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_doc_id ON transcript_segments(doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_doc_id ON memories(doc_id)")
            
            conn.commit()
            conn.commit()
            try:
                self.db_path.chmod(0o600)
            except Exception:
                pass
            
            logger.info("Database schema initialized")

    def _detect_schema(self):
        """Detect whether transcript_segments uses 'emotion' or 'dominant_emotion'."""
        candidate = "emotion"
        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(transcript_segments)")
                rows = cur.fetchall()
            columns = set()
            for row in rows:
                try:
                    columns.add(row["name"])
                except (KeyError, TypeError):
                    # row can be tuple (index, name, type, ...); name at position 1
                    columns.add(row[1])
            if "emotion" in columns:
                candidate = "emotion"
            elif "dominant_emotion" in columns:
                candidate = "dominant_emotion"
            else:
                logger.warning("[RAG] emotion column not found in schema, defaulting to 'emotion'")
        except Exception as exc:
            logger.warning(f"[RAG] Failed to detect emotion column: {exc}")
        self.emotion_column = candidate

    def _connect(self) -> sqlite3.Connection:
        conn = self._db.connect()
        # Use sqlite3.Row for std sqlite; for SQLCipher connections use a dict row
        try:
            module_name = getattr(conn.__class__, "__module__", "")
            if module_name.startswith("pysqlcipher3") or module_name.startswith("sqlcipher3"):
                class _CompatRow(dict):
                    __slots__ = ("_sequence",)

                    def __init__(self, cursor_description, row_tuple):
                        ordered = []
                        description = cursor_description or []
                        for idx, col in enumerate(description):
                            name = col[0] if isinstance(col, (list, tuple)) else str(col)
                            ordered.append((name, row_tuple[idx]))
                        super().__init__(ordered)
                        self._sequence = tuple(row_tuple)

                    def __getitem__(self, key):
                        if isinstance(key, int):
                            return self._sequence[key]
                        return super().__getitem__(key)

                def _compat_factory(cursor, row):
                    return _CompatRow(cursor.description, row)

                conn.row_factory = _compat_factory
            else:
                conn.row_factory = sqlite3.Row
        except Exception:
            try:
                conn.row_factory = sqlite3.Row
            except Exception:
                pass
        return conn

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
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

    @staticmethod
    def _trim_text(value: Optional[str], max_chars: int = 1200) -> str:
        if not value:
            return ""
        if len(value) <= max_chars:
            return value
        return value[:max_chars].rstrip() + "…"

    @staticmethod
    def _value_from_row(row: Any, key: str, default: Any = None) -> Any:
        if row is None:
            return default
        try:
            if isinstance(row, dict):
                return row.get(key, default)
            if hasattr(row, "keys") and key in row.keys():  # sqlite3.Row
                return row[key]
            return row[key]
        except Exception:
            return default

    @staticmethod
    def _format_timestamp_value(value: Any) -> Optional[str]:
        if value in (None, "", 0):
            return None
        try:
            dt = datetime.fromisoformat(str(value))
            return dt.isoformat()
        except Exception:
            try:
                numeric = float(value)
                # Heuristic: treat large values as ms
                if numeric > 1e12:
                    numeric /= 1000.0
                return datetime.utcfromtimestamp(numeric).isoformat() + "Z"
            except Exception:
                text = str(value).strip()
                return text or None

    def _build_segment_filters(self, filters: Dict[str, Any], *, include_text_constraint: bool = True) -> Tuple[List[str], List[Any]]:
        conditions: List[str] = []
        if include_text_constraint:
            conditions.extend(["ts.text IS NOT NULL", "ts.text != ''"])
        params: List[Any] = []

        speakers = self._normalize_filter_list(filters.get("speakers"))
        if speakers:
            placeholders = ",".join(["?"] * len(speakers))
            conditions.append(f"LOWER(ts.speaker) IN ({placeholders})")
            params.extend([s.lower() for s in speakers])

        emotions = self._normalize_filter_list(filters.get("emotions"))
        if emotions:
            placeholders = ",".join(["?"] * len(emotions))
            conditions.append(f"LOWER(COALESCE(ts.{self.emotion_column}, '')) IN ({placeholders})")
            params.extend([e.lower() for e in emotions])

        start_date_utc = filters.get("start_date_utc") or filters.get("start_date_iso")
        end_date_utc = filters.get("end_date_utc") or filters.get("end_date_iso")
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        if start_date_utc:
            conditions.append("tr.created_at >= ?")
            params.append(str(start_date_utc))
        elif start_date:
            conditions.append("tr.created_at >= ?")
            params.append(f"{start_date}T00:00:00")
        if end_date_utc:
            conditions.append("tr.created_at <= ?")
            params.append(str(end_date_utc))
        elif end_date:
            conditions.append("tr.created_at <= ?")
            params.append(f"{end_date}T23:59:59")

        last_n = filters.get("last_n_transcripts")
        if last_n:
            try:
                recent_ids = self._get_recent_transcript_ids(int(last_n))
            except Exception:
                recent_ids = set()
            if recent_ids:
                placeholders = ",".join(["?"] * len(recent_ids))
                conditions.append(f"ts.transcript_id IN ({placeholders})")
                params.extend(list(recent_ids))

        raw_keywords = filters.get("keywords")
        keywords = [k.strip() for k in str(raw_keywords or "").split(",") if k.strip()]
        search_type = (filters.get("search_type") or "keyword").lower()
        if keywords and search_type != "semantic":
            match_all = (filters.get("match") or "any").lower() == "all"
            escaped_tokens = [self._escape_like(token.lower()) for token in keywords]
            like_clauses = ["LOWER(ts.text) LIKE ? ESCAPE '\\\\'" for _ in escaped_tokens]
            if match_all:
                conditions.extend(like_clauses)
            else:
                conditions.append("(" + " OR ".join(like_clauses) + ")")
            params.extend([f"%{token}%" for token in escaped_tokens])

        return conditions, params

    def count_transcripts_filtered(self, filters: Dict[str, Any]) -> int:
        search_type = (filters.get("search_type") or "keyword").lower()
        keywords = [k.strip() for k in str(filters.get("keywords", "")).split(",") if k.strip()]

        if keywords and search_type == "semantic":
            query = ", ".join(keywords)
            top_k = min(int(filters.get("limit", 50) or 50), 200)
            results = self.search_semantic(
                query=query,
                top_k=top_k,
                doc_type='transcript_segment',
                start_date=filters.get('start_date_utc') or filters.get('start_date'),
                end_date=filters.get('end_date_utc') or filters.get('end_date'),
                speakers=self._normalize_filter_list(filters.get('speakers')),
                bias_emotions=self._normalize_filter_list(filters.get('emotions')),
            )
            count = len(results or [])
            logger.info(f"[RAG] Semantic count for '{query}' -> {count}")
            return count

        include_text_constraint = bool(keywords) or search_type == "segments"
        conditions, params = self._build_segment_filters(filters, include_text_constraint=include_text_constraint)
        join_type = "JOIN" if include_text_constraint else "LEFT JOIN"

        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                logger.info(
                    "[RAG] count filters=%s join=%s where=%s params=%s",
                    {k: filters.get(k) for k in ("limit", "speakers", "emotions", "start_date", "end_date", "keywords", "search_type", "match")},
                    join_type,
                    where_clause,
                    params,
                )
                cur.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM transcript_segments ts
                    {join_type} transcript_records tr ON ts.transcript_id = tr.id
                    WHERE {where_clause}
                    """,
                    params,
                )
                row = cur.fetchone()
            count = int(row[0]) if row else 0
            logger.info(f"[RAG] SQL transcript count -> {count}")
            return count
        except Exception as e:
            logger.error(f"[RAG] Failed to count transcripts: {e}")
            return 0

    def query_transcripts_filtered(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        limit = max(1, min(int(filters.get("limit", 20) or 20), 200))
        offset = max(0, int(filters.get("offset", 0) or 0))
        context_lines = max(0, min(int(filters.get("context_lines", 3) or 0), 10))
        search_type = (filters.get("search_type") or "keyword").lower()
        keywords = [k.strip() for k in str(filters.get("keywords", "")).split(",") if k.strip()]
        sort_by = (filters.get("sort_by") or "created_at").lower()
        order = (filters.get("order") or "desc").lower()
        valid_sort_fields = {"created_at", "speaker", "emotion", "job_id", "start_time"}
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        if order not in {"asc", "desc"}:
            order = "desc"
        order_sql = "ASC" if order == "asc" else "DESC"

        if keywords and search_type == "semantic":
            query = ", ".join(keywords)
            results = self.search_semantic(
                query=query,
                top_k=limit,
                doc_type='transcript_segment',
                start_date=filters.get('start_date_utc') or filters.get('start_date'),
                end_date=filters.get('end_date_utc') or filters.get('end_date'),
                speakers=self._normalize_filter_list(filters.get('speakers')),
                bias_emotions=self._normalize_filter_list(filters.get('emotions')),
            ) or []
            items: List[Dict[str, Any]] = []
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                for result in results:
                    metadata = result.get('metadata') or {}
                    transcript_id = metadata.get('transcript_id')
                    seq = metadata.get('seq')
                    if transcript_id is None or seq is None:
                        continue
                    # Context before
                    cur.execute(
                        f"""
                        SELECT text, speaker, {self.emotion_column} AS emotion
                        FROM transcript_segments
                        WHERE transcript_id = ? AND seq < ?
                        ORDER BY seq DESC
                        LIMIT ?
                        """,
                        (transcript_id, seq, context_lines),
                    )
                    context_rows = cur.fetchall()
                    context = [
                        {
                            "speaker": row['speaker'],
                            "text": self._trim_text(row['text']),
                            "emotion": row['emotion'],
                        }
                        for row in reversed(context_rows)
                    ] if context_lines else []

                    # Context after
                    cur.execute(
                        f"""
                        SELECT text, speaker, {self.emotion_column} AS emotion
                        FROM transcript_segments
                        WHERE transcript_id = ? AND seq > ?
                        ORDER BY seq ASC
                        LIMIT ?
                        """,
                        (transcript_id, seq, context_lines),
                    )
                    after_rows = cur.fetchall()
                    context_after = [
                        {
                            "speaker": row['speaker'],
                            "text": self._trim_text(row['text']),
                            "emotion": row['emotion'],
                        }
                        for row in after_rows
                    ] if context_lines else []

                    items.append({
                        "segment_id": metadata.get('segment_id'),
                        "transcript_id": transcript_id,
                        "job_id": metadata.get('job_id'),
                        "speaker": metadata.get('speaker'),
                        "emotion": metadata.get('emotion'),
                        "text": self._trim_text(result.get('text')),
                        "score": result.get('score'),
                        "created_at": metadata.get('created_at'),
                        "start_time": metadata.get('start_time'),
                        "end_time": metadata.get('end_time'),
                        "context_before": context,
                        "context_after": context_after,
                    })

            def _timestamp_value(value: Any) -> float:
                if value in (None, ""):
                    return 0.0
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

            items.sort(key=_sort_key, reverse=(order == "desc"))
            total = len(items)
            return {"items": items, "count": len(items), "total": total}

        include_text_constraint = bool(keywords) or search_type == "segments"
        conditions, params = self._build_segment_filters(filters, include_text_constraint=include_text_constraint)
        join_type = "JOIN" if include_text_constraint else "LEFT JOIN"
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        total = self.count_transcripts_filtered(filters)

        # Determine ORDER BY clause safely
        if sort_by == "speaker":
            order_by = f"LOWER(ts.speaker) {order_sql}, tr.created_at DESC, ts.seq ASC"
        elif sort_by == "emotion":
            order_by = f"LOWER(COALESCE(ts.{self.emotion_column}, '')) {order_sql}, tr.created_at DESC, ts.seq ASC"
        elif sort_by == "job_id":
            order_by = f"COALESCE(tr.job_id, '') {order_sql}, tr.created_at DESC, ts.seq ASC"
        elif sort_by == "start_time":
            order_by = f"COALESCE(ts.start_time, 0) {order_sql}, tr.created_at DESC, ts.seq ASC"
        else:  # created_at
            order_by = f"tr.created_at {order_sql}, ts.seq ASC"

        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                logger.info(
                    "[RAG] query filters=%s join=%s where=%s params=%s limit=%s offset=%s",
                    {k: filters.get(k) for k in ("limit", "speakers", "emotions", "start_date", "end_date", "keywords", "search_type", "match")},
                    join_type,
                    where_clause,
                    params,
                    limit,
                    offset,
                )
                cur.execute(
                    f"""
                    SELECT ts.id, ts.text, ts.speaker, ts.{self.emotion_column} AS emotion, ts.emotion_confidence,
                           ts.transcript_id, ts.seq, ts.start_time, ts.end_time,
                           tr.job_id, tr.created_at
                    FROM transcript_segments ts
                    {join_type} transcript_records tr ON ts.transcript_id = tr.id
                    WHERE {where_clause}
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """,
                    params + [limit, offset],
                )
                rows = cur.fetchall()

                items: List[Dict[str, Any]] = []
                for row in rows:
                    if context_lines:
                        # Context before
                        cur.execute(
                            f"""
                            SELECT text, speaker, {self.emotion_column} AS emotion
                            FROM transcript_segments
                            WHERE transcript_id = ? AND seq < ?
                            ORDER BY seq DESC
                            LIMIT ?
                            """,
                            (row['transcript_id'], row['seq'], context_lines),
                        )
                        context_rows = cur.fetchall()
                        context = [
                            {
                                "speaker": ctx['speaker'],
                                "text": self._trim_text(ctx['text']),
                                "emotion": ctx['emotion'],
                            }
                            for ctx in reversed(context_rows)
                        ]
                        # Context after
                        cur.execute(
                            f"""
                            SELECT text, speaker, {self.emotion_column} AS emotion
                            FROM transcript_segments
                            WHERE transcript_id = ? AND seq > ?
                            ORDER BY seq ASC
                            LIMIT ?
                            """,
                            (row['transcript_id'], row['seq'], context_lines),
                        )
                        after_rows = cur.fetchall()
                        context_after = [
                            {
                                "speaker": ctx['speaker'],
                                "text": self._trim_text(ctx['text']),
                                "emotion": ctx['emotion'],
                            }
                            for ctx in after_rows
                        ]
                    else:
                        context = []
                        context_after = []

                    items.append({
                        "segment_id": row['id'],
                        "transcript_id": row['transcript_id'],
                        "job_id": row['job_id'],
                        "speaker": row['speaker'],
                        "emotion": row['emotion'],
                        "emotion_confidence": row.get('emotion_confidence'),
                        "text": self._trim_text(row['text']),
                        "created_at": row['created_at'],
                        "start_time": row['start_time'],
                        "end_time": row['end_time'],
                        "context_before": context,
                        "context_after": context_after,
                    })


            logger.info(f"[RAG] query_transcripts_filtered -> {len(items)} items (total={total}) sort_by={sort_by} order={order} limit={limit} offset={offset}")
            has_more = (offset + len(items)) < total if isinstance(total, int) else (len(items) == limit)
            next_offset = offset + len(items)
            return {
                "items": items,
                "count": len(items),
                "total": total,
                "has_more": bool(has_more),
                "next_offset": next_offset,
                "sort_by": sort_by,
                "order": order,
            }
        except Exception as e:
            logger.error(f"[RAG] Failed to query transcripts: {e}")
            return {"items": [], "count": 0, "total": 0}

    def get_transcript_time_range(self) -> Dict[str, Any]:
        """Return dataset coverage stats so the UI can guide users when filters return zero rows."""
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    MIN(created_at) AS min_created_at,
                    MAX(created_at) AS max_created_at,
                    COUNT(*) AS transcript_count
                FROM transcript_records
                """
            )
            transcripts_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    MIN(created_at) AS min_segment_at,
                    MAX(created_at) AS max_segment_at,
                    COUNT(*) AS segment_count
                FROM transcript_segments
                """
            )
            segments_row = cur.fetchone()

        transcript_count = int(self._value_from_row(transcripts_row, "transcript_count", 0) or 0)
        segment_count = int(self._value_from_row(segments_row, "segment_count", 0) or 0)
        start = self._format_timestamp_value(self._value_from_row(transcripts_row, "min_created_at"))
        end = self._format_timestamp_value(self._value_from_row(transcripts_row, "max_created_at"))
        seg_start = self._format_timestamp_value(self._value_from_row(segments_row, "min_segment_at"))
        seg_end = self._format_timestamp_value(self._value_from_row(segments_row, "max_segment_at"))

        payload = {
            "status": "ok",
            "transcript_count": transcript_count,
            "segment_count": segment_count,
            "transcript_range": {"start": start, "end": end},
            "segment_range": {"start": seg_start, "end": seg_end},
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        logger.info(
            "[RAG] Dataset window: transcripts=%s segments=%s range=%s→%s",
            transcript_count,
            segment_count,
            start,
            end,
        )
        return payload

    def get_unique_speakers(self) -> List[str]:
        """Return sorted list of unique speakers across stored transcripts."""
        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                speakers: Set[str] = set()

                # Primary source: individual transcript segments
                cur.execute(
                    """
                    SELECT DISTINCT speaker
                    FROM transcript_segments
                    WHERE speaker IS NOT NULL AND speaker != ''
                    """
                )
                speakers.update(row[0] for row in cur.fetchall() if row[0])

                # Some legacy databases stored primary speaker on transcript_records
                cur.execute("PRAGMA table_info(transcript_records)")
                transcript_columns = {row[1] if isinstance(row, tuple) else row["name"] for row in cur.fetchall()}
                if "primary_speaker" in transcript_columns:
                    try:
                        cur.execute(
                            """
                            SELECT DISTINCT primary_speaker
                            FROM transcript_records
                            WHERE primary_speaker IS NOT NULL AND primary_speaker != ''
                            """
                        )
                        speakers.update(row[0] for row in cur.fetchall() if row[0])
                    except sqlite3.OperationalError as exc:
                        logger.warning(
                            "[RAG] primary_speaker column reported but query failed (%s); skipping fallback",
                            exc,
                        )


            sorted_speakers = sorted(speakers, key=lambda s: s.lower())
            logger.info(f"[RAG] get_unique_speakers -> {len(sorted_speakers)} speakers")
            return sorted_speakers
        except Exception as e:
            logger.error(f"[RAG] Failed to get speakers: {e}")
            return []
    
    def _init_faiss_index(self):
        """Initialize or load FAISS index"""
        try:
            if self.faiss_index_path.exists():
                logger.info(f"Loading existing FAISS index from {self.faiss_index_path}")
                self.faiss_index = faiss.read_index(str(self.faiss_index_path))
                
                # Load document store
                doc_store_path = Path(str(self.faiss_index_path) + ".docs")
                if doc_store_path.exists():
                    with open(doc_store_path, 'r', encoding='utf-8') as f:
                        self.document_store = json.load(f)
                
                logger.info(f"FAISS index loaded with {self.faiss_index.ntotal} documents")
            else:
                logger.info("Creating new FAISS index (IndexFlatIP for cosine similarity)")
                self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)
                logger.info("New FAISS index created")
        except Exception as e:
            logger.error(f"Failed to initialize FAISS index: {e}")
            self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)

    # ------------------------------------------------------------------
    # Analysis Artifacts (Analyzer 2.0 persistence layer)
    # ------------------------------------------------------------------

    def archive_analysis_artifact(
        self,
        artifact_id: Optional[str],
        analysis_id: Optional[str],
        title: Optional[str],
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
        index_body: bool = False,
    ) -> str:
        if not body:
            raise ValueError("artifact body cannot be empty")

        artifact_id = artifact_id or f"artifact_{uuid.uuid4().hex}"
        created_at = datetime.utcnow().isoformat() + "Z"
        meta_json = json.dumps(metadata or {})
        embedding_blob = None
        if index_body and os.getenv("RAG_ENABLE_SEMANTIC", "true").lower() in {"1", "true", "yes"}:
            try:
                self._ensure_semantic_ready()
                embedding_blob = self.get_embedding(body[:4000]).tobytes()
            except Exception as exc:
                logger.warning(f"[RAG] Artifact embedding skipped: {exc}")
                embedding_blob = None

        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO analysis_artifacts
                (artifact_id, analysis_id, title, body, metadata, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    analysis_id,
                    title or "Analyzer Run",
                    body,
                    meta_json,
                    embedding_blob,
                    created_at,
                ),
            )
            conn.commit()
        logger.info(f"[RAG] Archived analysis artifact {artifact_id} (analysis_id={analysis_id})")
        try:
            self._replace_artifact_chunks(artifact_id, body, index_body=index_body)
        except Exception as exc:
            logger.warning(f"[RAG] Failed to chunk artifact {artifact_id}: {exc}")
        return artifact_id

    def _chunk_artifact_body(self, body: str, chunk_chars: int = 900, overlap_chars: int = 150) -> List[str]:
        text = (body or "").strip()
        if not text:
            return []
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        chunks: List[str] = []
        buffer = ""
        for para in paragraphs:
            candidate = f"{buffer}\n{para}".strip() if buffer else para
            if len(candidate) > chunk_chars and buffer:
                chunks.append(buffer.strip())
                if overlap_chars > 0 and len(buffer) > overlap_chars:
                    buffer = buffer[-overlap_chars:].strip()
                else:
                    buffer = ""
                candidate = para
            buffer = candidate
        if buffer:
            chunks.append(buffer.strip())
        return chunks

    def _replace_artifact_chunks(self, artifact_id: str, body: str, index_body: bool = False) -> None:
        chunks = self._chunk_artifact_body(body)
        timestamp = datetime.utcnow().isoformat() + "Z"
        if not chunks:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute("DELETE FROM analysis_artifact_chunks WHERE artifact_id = ?", (artifact_id,))
                conn.commit()
            return

        semantic_enabled = index_body and os.getenv("RAG_ENABLE_SEMANTIC", "true").lower() in {"1", "true", "yes"}
        if semantic_enabled:
            try:
                self._ensure_semantic_ready()
            except Exception as exc:
                logger.warning(f"[RAG] Chunk embedding disabled: {exc}")
                semantic_enabled = False

        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM analysis_artifact_chunks WHERE artifact_id = ?", (artifact_id,))
            for seq, chunk in enumerate(chunks):
                embedding_blob = None
                if semantic_enabled:
                    try:
                        embedding_blob = self.get_embedding(chunk[:2000]).tobytes()
                    except Exception as exc:
                        logger.warning(f"[RAG] Chunk embedding failure (artifact={artifact_id} seq={seq}): {exc}")
                        embedding_blob = None
                cur.execute(
                    """
                    INSERT INTO analysis_artifact_chunks
                    (artifact_id, seq, chunk_text, token_estimate, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        seq,
                        chunk,
                        len(chunk.split()),
                        embedding_blob,
                        timestamp,
                    ),
                )
            conn.commit()

    def list_artifact_chunks(self, artifact_id: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        if not artifact_id:
            return {"items": [], "count": 0, "has_more": False}
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, seq, chunk_text, token_estimate, created_at
                FROM analysis_artifact_chunks
                WHERE artifact_id = ?
                ORDER BY seq ASC
                LIMIT ? OFFSET ?
                """,
                (artifact_id, limit, offset),
            )
            rows = cur.fetchall()
        items = [
            {
                "chunk_id": row[0],
                "seq": row[1],
                "text": row[2],
                "token_estimate": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]
        return {"items": items, "count": len(items), "has_more": len(items) == limit, "next_offset": offset + len(items)}

    def search_artifact_chunks(
        self,
        query: str,
        artifact_ids: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if not query:
            return []
        limit = max(1, min(int(limit), 100))
        token = f"%{self._escape_like(query.lower())}%"
        params: List[Any] = []
        where = ["LOWER(chunk_text) LIKE ? ESCAPE '\\\\'"]
        params.append(token)
        if artifact_ids:
            placeholders = ",".join(["?"] * len(artifact_ids))
            where.append(f"artifact_id IN ({placeholders})")
            params.extend(artifact_ids)
        query_sql = f"""
            SELECT artifact_id, seq, chunk_text, substr(chunk_text, 1, 600) AS preview, created_at
            FROM analysis_artifact_chunks
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(query_sql, params)
            rows = cur.fetchall()
        return [
            {
                "artifact_id": row[0],
                "seq": row[1],
                "text": row[2],
                "preview": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    def list_analysis_artifacts(self, limit: int = 50, offset: int = 0, user_id: Optional[str] = None) -> Dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        logger.info('[RAG] list_analysis_artifacts limit=%s offset=%s user_id=%s', limit, offset, user_id)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            if user_id:
                cur.execute(
                    """
                    SELECT artifact_id, analysis_id, title, created_at, LENGTH(body) AS size, metadata
                    FROM analysis_artifacts
                    WHERE json_extract(metadata, '$.user_id') = ? OR json_type(metadata, '$.user_id') IS NULL
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT artifact_id, analysis_id, title, created_at, LENGTH(body) AS size, metadata
                    FROM analysis_artifacts
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            rows = cur.fetchall()
        items = []
        for row in rows:
            aid = self._value_from_row(row, "artifact_id") or (row[0] if not isinstance(row, dict) else None)
            anid = self._value_from_row(row, "analysis_id") or (row[1] if not isinstance(row, dict) else None)
            title = self._value_from_row(row, "title") or (row[2] if not isinstance(row, dict) else None)
            created = self._value_from_row(row, "created_at") or (row[3] if not isinstance(row, dict) else None)
            size_val = self._value_from_row(row, "size")
            if size_val is None and not isinstance(row, dict):
                try:
                    size_val = row[4]
                except Exception:
                    size_val = 0
            meta_raw = self._value_from_row(row, "metadata")
            if meta_raw is None and not isinstance(row, dict):
                try:
                    meta_raw = row[5]
                except Exception:
                    meta_raw = None
            try:
                metadata = json.loads(meta_raw) if meta_raw else {}
            except Exception:
                metadata = {}
            items.append(
                {
                    "artifact_id": aid,
                    "analysis_id": anid,
                    "title": title,
                    "created_at": created,
                    "size": int(size_val or 0),
                    "metadata": metadata,
                }
            )
        has_more = len(items) == limit
        logger.info('[RAG] list_analysis_artifacts -> %s items (has_more=%s)', len(items), has_more)
        return {"items": items, "count": len(items), "has_more": has_more, "next_offset": offset + len(items)}

    def get_analysis_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        if not artifact_id:
            return None
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT artifact_id, analysis_id, title, body, metadata, created_at
                FROM analysis_artifacts
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        aid = self._value_from_row(row, "artifact_id") or (row[0] if not isinstance(row, dict) else None)
        anid = self._value_from_row(row, "analysis_id") or (row[1] if not isinstance(row, dict) else None)
        title = self._value_from_row(row, "title") or (row[2] if not isinstance(row, dict) else None)
        body = self._value_from_row(row, "body") if isinstance(row, dict) else row[3]
        meta_raw = self._value_from_row(row, "metadata") if isinstance(row, dict) else row[4]
        try:
            metadata = json.loads(meta_raw) if meta_raw else {}
        except Exception:
            metadata = {}
        created = self._value_from_row(row, "created_at") or (row[5] if not isinstance(row, dict) else None)
        return {
            "artifact_id": aid,
            "analysis_id": anid,
            "title": title,
            "body": body,
            "metadata": metadata,
            "created_at": created,
        }

    def search_analysis_artifacts(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        if not query:
            return []
        limit = max(1, min(int(limit), 100))
        token = f"%{self._escape_like(query.lower())}%"
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT artifact_id, title, substr(body, 1, 600) AS preview, created_at
                FROM analysis_artifacts
                WHERE LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(body) LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (token, token, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "artifact_id": row[0],
                "title": row[1],
                "preview": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]

    def _ensure_semantic_ready(self):
        """Lazy init embeddings + FAISS and load data into index."""
        if self.embedding_model is None:
            self._init_embedding_model()
        if self.faiss_index is None:
            self._init_faiss_index()
            self._load_existing_data()
    
    def _load_existing_data(self):
        """Load existing segments/memories from database into FAISS"""
        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                
                # Load transcript segments
                cur.execute("SELECT * FROM transcript_segments WHERE doc_id IS NOT NULL")
                segments = cur.fetchall()
                
                embeddings_to_add = []
                for seg in segments:
                    doc_id = seg['doc_id']
                    if doc_id not in self.document_store:
                        # Reconstruct document metadata
                        self.document_store[doc_id] = {
                            'id': doc_id,
                            'text': seg['text'],
                            'type': 'transcript_segment',
                            'segment_id': seg['id'],
                            'transcript_id': seg['transcript_id'],
                            'speaker': seg['speaker'],
                            'start_time': seg['start_time'],
                            'end_time': seg['end_time'],
                            'emotion': seg['emotion'],
                            'emotion_confidence': seg['emotion_confidence'],
                            'emotion_scores': json.loads(seg['emotion_scores']) if seg['emotion_scores'] else None,
                            'audio_metrics': json.loads(seg['audio_metrics']) if seg['audio_metrics'] else None,
                            'created_at': seg['created_at']
                        }
                        
                        # Decode embedding
                        if seg['embedding']:
                            embedding = np.frombuffer(seg['embedding'], dtype=np.float32)
                            embeddings_to_add.append(embedding)
                
                # Load memories
                cur.execute("SELECT * FROM memories WHERE doc_id IS NOT NULL")
                memories = cur.fetchall()
                
                for mem in memories:
                    doc_id = mem['doc_id']
                    if doc_id not in self.document_store:
                        self.document_store[doc_id] = {
                            'id': doc_id,
                            'text': f"{mem['title']}\n{mem['body']}",
                            'type': 'memory',
                            'memory_id': mem['memory_id'],
                            'title': mem['title'],
                            'body': mem['body'],
                            'metadata': json.loads(mem['metadata']) if mem['metadata'] else {},
                            'created_at': mem['created_at']
                        }
                        
                        if mem['embedding']:
                            embedding = np.frombuffer(mem['embedding'], dtype=np.float32)
                            embeddings_to_add.append(embedding)
                
                
                # Add embeddings to FAISS
                if embeddings_to_add:
                    embeddings_array = np.vstack(embeddings_to_add)
                    self.faiss_index.add(embeddings_array)
                    logger.info(f"Loaded {len(embeddings_to_add)} documents into FAISS index")
                else:
                    logger.info("No existing documents to load")
                    
        except Exception as e:
            logger.error(f"Failed to load existing data: {e}")
            import traceback
            traceback.print_exc()
    
    def get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text"""
        try:
            embedding = self.embedding_model.encode(text, convert_to_tensor=False)
            # Normalize for cosine similarity (required for IndexFlatIP)
            embedding = embedding.astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return np.zeros(self.embedding_dim, dtype=np.float32)
    
    def index_transcript(
        self,
        job_id: str,
        session_id: str,
        full_text: str,
        audio_duration: float,
        segments: List[Dict[str, Any]]
    ) -> int:
        """
        Index a full transcript with all segments and metadata
        
        Returns transcript_id
        """
        with self.lock:
            try:
                conn = self._connect()
                cur = conn.cursor()
                
                timestamp = datetime.utcnow().isoformat()
                
                # Store transcript record
                cur.execute("""
                    INSERT OR REPLACE INTO transcript_records
                    (job_id, session_id, full_text, audio_duration, timestamp, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (job_id, session_id, full_text, audio_duration, timestamp, timestamp))
                
                transcript_id = cur.lastrowid
                if transcript_id == 0:
                    # If REPLACE happened, get existing ID
                    cur.execute("SELECT id FROM transcript_records WHERE job_id = ?", (job_id,))
                    transcript_id = cur.fetchone()[0]
                
                # Clear old segments if replacing
                cur.execute("SELECT doc_id FROM transcript_segments WHERE transcript_id = ?", (transcript_id,))
                old_doc_ids = [row[0] for row in cur.fetchall()]
                for doc_id in old_doc_ids:
                    if doc_id in self.document_store:
                        del self.document_store[doc_id]
                
                cur.execute("DELETE FROM transcript_segments WHERE transcript_id = ?", (transcript_id,))
                
                # Store segments and index in FAISS
                embeddings_to_add = []
                last_end_by_speaker: Dict[str, float] = {}
                for idx, seg in enumerate(segments):
                    doc_id = f"seg_{job_id}_{idx}_{uuid.uuid4().hex[:8]}"
                    text = seg.get('text', '')
                    emotion_value = seg.get('emotion', seg.get('dominant_emotion'))
                    features = self._compute_segment_features(seg, last_end_by_speaker)
                    
                    # Generate embedding only if semantics enabled
                    embedding = None
                    if os.getenv("RAG_ENABLE_SEMANTIC", "true").lower() in {"1", "true", "yes"}:
                        try:
                            self._ensure_semantic_ready()
                            embedding = self.get_embedding(text)
                            embeddings_to_add.append(embedding)
                        except Exception as _e:
                            logger.warning(f"[RAG] Embedding generation skipped: {_e}")
                    
                    # Store in document store
                    self.document_store[doc_id] = {
                        'id': doc_id,
                        'text': text,
                        'type': 'transcript_segment',
                        'job_id': job_id,
                        'transcript_id': transcript_id,
                        'seq': idx,
                        'speaker': seg.get('speaker'),
                        'start_time': seg.get('start_time'),
                        'end_time': seg.get('end_time'),
                        'emotion': emotion_value,
                        'emotion_confidence': seg.get('emotion_confidence'),
                        'emotion_scores': seg.get('emotion_scores'),
                        'audio_metrics': seg.get('audio_metrics'),
                        'word_count': features["word_count"],
                        'filler_count': features["filler_count"],
                        'pace_wpm': features["pace_wpm"],
                        'pause_ms': features["pause_ms"],
                        'pitch_mean': features["pitch_mean"],
                        'pitch_std': features["pitch_std"],
                        'volume_rms': features["volume_rms"],
                        'volume_peak': features["volume_peak"],
                        'created_at': timestamp
                    }
                    
                    # Store in database
                    cur.execute(f"""
                        INSERT INTO transcript_segments
                        (transcript_id, seq, text, speaker, start_time, end_time,
                         speaker_confidence, {self.emotion_column}, emotion_confidence, emotion_scores,
                         audio_metrics, embedding, doc_id, created_at,
                         word_count, filler_count, pace_wpm, pause_ms,
                         pitch_mean, pitch_std, volume_rms, volume_peak)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        transcript_id,
                        idx,
                        text,
                        seg.get('speaker'),
                        seg.get('start_time'),
                        seg.get('end_time'),
                        seg.get('speaker_confidence'),
                        emotion_value,
                        seg.get('emotion_confidence'),
                        json.dumps(seg.get('emotion_scores')) if seg.get('emotion_scores') else None,
                        json.dumps(seg.get('audio_metrics')) if seg.get('audio_metrics') else None,
                        (embedding.tobytes() if embedding is not None else None),
                        doc_id,
                        timestamp,
                        features["word_count"],
                        features["filler_count"],
                        features["pace_wpm"],
                        features["pause_ms"],
                        features["pitch_mean"],
                        features["pitch_std"],
                        features["volume_rms"],
                        features["volume_peak"],
                    ))
                
                # Add all embeddings to FAISS
                if embeddings_to_add:
                    embeddings_array = np.vstack(embeddings_to_add)
                    self.faiss_index.add(embeddings_array)
                    logger.info(f"Indexed {len(embeddings_to_add)} segments for job {job_id}")
                
                conn.commit()

                # Save FAISS index
                self._save_faiss_index()

                logger.info(f"Transcript {job_id} indexed successfully (transcript_id={transcript_id})")
                return transcript_id
            except Exception as e:
                logger.error(f"Failed to index transcript: {e}")
                import traceback
                traceback.print_exc()
                conn.rollback()
                raise

    def _ensure_segment_column_extensions(self, cursor: sqlite3.Cursor) -> None:
        """Ensure extended analytics columns exist on transcript_segments table."""
        cursor.execute("PRAGMA table_info(transcript_segments)")
        existing = {row["name"] for row in cursor.fetchall()}
        columns_to_add = [
            ("word_count", "INTEGER"),
            ("filler_count", "INTEGER"),
            ("pace_wpm", "REAL"),
            ("pause_ms", "REAL"),
            ("pitch_mean", "REAL"),
            ("pitch_std", "REAL"),
            ("volume_rms", "REAL"),
            ("volume_peak", "REAL"),
        ]
        for name, decl in columns_to_add:
            if name not in existing:
                cursor.execute(f"ALTER TABLE transcript_segments ADD COLUMN {name} {decl}")

    def _compute_segment_features(
        self,
        segment: Dict[str, Any],
        last_end_by_speaker: Dict[str, float],
    ) -> Dict[str, Optional[float]]:
        """Derive speech metrics for a segment."""
        text = segment.get("text") or ""
        tokens = WORD_REGEX.findall(text)
        word_count = len(tokens)
        filler_count = 0
        lowered = text.lower()
        for pattern in FILLER_PATTERNS:
            matches = pattern.findall(lowered)
            filler_count += len(matches)

        start_time = segment.get("start_time")
        end_time = segment.get("end_time")
        pace_wpm = None
        if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
            duration = max(0.0, end_time - start_time)
            if duration > 0:
                pace_wpm = (word_count / duration) * 60.0

        pause_ms = None
        speaker = segment.get("speaker")
        if speaker:
            prev_end = last_end_by_speaker.get(speaker)
            if prev_end is not None and isinstance(start_time, (int, float)):
                delta = (start_time - prev_end) * 1000.0
                if delta > 0:
                    pause_ms = delta
            if isinstance(end_time, (int, float)):
                last_end_by_speaker[speaker] = end_time

        audio_metrics = segment.get("audio_metrics") or {}
        pitch_mean = audio_metrics.get("pitch_mean") or segment.get("pitch_mean")
        pitch_std = audio_metrics.get("pitch_std") or segment.get("pitch_std")
        volume_rms = audio_metrics.get("volume_rms") or audio_metrics.get("rms")
        volume_peak = audio_metrics.get("volume_peak") or audio_metrics.get("peak")

        return {
            "word_count": word_count,
            "filler_count": filler_count,
            "pace_wpm": pace_wpm,
            "pause_ms": pause_ms,
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "volume_rms": volume_rms,
            "volume_peak": volume_peak,
        }
    
    def search_semantic(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        last_n_transcripts: Optional[int] = None,
        speakers: Optional[List[str]] = None,
        bias_emotions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search using FAISS vector similarity
        
        Args:
            query: Natural language query
            top_k: Number of results to return
            doc_type: Filter by 'transcript_segment' or 'memory' (optional)
        
        Returns:
            List of results with text, metadata, and similarity score
        """
        try:
            # Semantic search can be disabled via env for speed
            if os.getenv("RAG_ENABLE_SEMANTIC", "true").lower() not in {"1", "true", "yes"}:
                logger.warning("[RAG] Semantic search requested but disabled; returning empty list")
                return []
            # Ensure model/index ready, then embed
            self._ensure_semantic_ready()
            query_embedding = self.get_embedding(query)
            
            # Search FAISS index (get more candidates for filtering)
            candidate_limit = max(20, top_k * 3)
            D, I = self.faiss_index.search(query_embedding.reshape(1, -1), candidate_limit)
            
            # Hydrate results from document store
            filtered_results = []
            doc_ids = list(self.document_store.keys())
            start_dt = None
            end_dt = None
            speakers_set = {s.lower() for s in speakers} if speakers else None
            bias_set = {e.lower() for e in bias_emotions} if bias_emotions else None
            allowed_transcript_ids = None

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date)
                except ValueError:
                    try:
                        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    except ValueError:
                        logger.warning(f"[RAG] Invalid start_date format: {start_date}")
                        start_dt = None
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date)
                except ValueError:
                    try:
                        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    except ValueError:
                        logger.warning(f"[RAG] Invalid end_date format: {end_date}")
                        end_dt = None

            if last_n_transcripts and last_n_transcripts > 0:
                allowed_transcript_ids = self._get_recent_transcript_ids(last_n_transcripts)
                logger.info(f"[RAG] Limiting search to last {len(allowed_transcript_ids)} transcripts")

            def parse_created_at(value: Optional[str]) -> Optional[datetime]:
                if not value:
                    return None
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            return datetime.strptime(value, "%Y-%m-%d")
                        except ValueError:
                            return None
            
            for score, idx in zip(D[0], I[0]):
                if idx < 0 or idx >= len(doc_ids):
                    continue
                
                doc_id = doc_ids[idx]
                doc = self.document_store.get(doc_id)
                
                if not doc:
                    continue
                
                # Filter by doc_type if specified
                if doc_type and doc.get('type') != doc_type:
                    continue

                metadata = {k: v for k, v in doc.items() if k not in ['id', 'text', 'type']}
                created_at_raw = metadata.get('created_at')
                created_at_dt = parse_created_at(created_at_raw)

                # Date filtering
                if start_dt and created_at_dt and created_at_dt < start_dt:
                    continue
                if end_dt and created_at_dt and created_at_dt > end_dt:
                    continue

                # last_n transcripts filter (transcript segments only)
                if allowed_transcript_ids is not None and doc.get('type') == 'transcript_segment':
                    transcript_id = metadata.get('transcript_id')
                    if transcript_id not in allowed_transcript_ids:
                        continue

                # speaker filter (transcript segments only)
                if speakers_set and doc.get('type') == 'transcript_segment':
                    speaker_value = (metadata.get('speaker') or '').lower()
                    if speaker_value not in speakers_set:
                        continue

                adjusted_score = float(score)
                if bias_set and doc.get('type') == 'transcript_segment':
                    emotion_value = (metadata.get('emotion') or '').lower()
                    if emotion_value in bias_set:
                        adjusted_score += 0.05

                filtered_results.append({
                    'id': doc['id'],
                    'text': doc['text'],
                    'type': doc['type'],
                    'metadata': metadata,
                    'score': adjusted_score
                })
            
            filtered_results.sort(key=lambda r: r['score'], reverse=True)
            final_results = filtered_results[:top_k]
            logger.info(f"Semantic search for '{query}' returned {len(final_results)} filtered results")
            return final_results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_recent_transcript_ids(self, limit: int) -> set[int]:
        """Return IDs of the most recent transcripts (by created_at DESC)"""
        try:
            with self.lock:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM transcript_records ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                rows = cur.fetchall()
                return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"[RAG] Failed to load recent transcript ids: {e}")
            return set()
    
    def add_memory(
        self,
        title: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a memory/note to the system"""
        with self.lock:
            try:
                memory_id = str(uuid.uuid4())
                doc_id = f"mem_{memory_id}"
                timestamp = datetime.utcnow().isoformat()
                
                # Generate embedding
                text = f"{title}\n{body}"
                embedding = self.get_embedding(text)
                
                # Store in document store
                self.document_store[doc_id] = {
                    'id': doc_id,
                    'text': text,
                    'type': 'memory',
                    'memory_id': memory_id,
                    'title': title,
                    'body': body,
                    'metadata': metadata or {},
                    'created_at': timestamp
                }
                
                # Store in database
                conn = self._connect()
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO memories
                    (memory_id, title, body, metadata, embedding, doc_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    memory_id,
                    title,
                    body,
                    json.dumps(metadata) if metadata else None,
                    embedding.tobytes(),
                    doc_id,
                    timestamp
                ))
                
                conn.commit()
                
                # Add to FAISS
                self.faiss_index.add(embedding.reshape(1, -1))
                self._save_faiss_index()
                
                logger.info(f"Memory added: {memory_id}")
                return memory_id
                
            except Exception as e:
                logger.error(f"Failed to add memory: {e}")
                raise
    
    def get_transcript(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get full transcript by job_id"""
        try:
            conn = self._connect()
            cur = conn.cursor()
            
            # Get transcript record
            cur.execute("SELECT * FROM transcript_records WHERE job_id = ?", (job_id,))
            record = cur.fetchone()
            
            if not record:
                return None
            
            # Get segments
            cur.execute("""
                SELECT * FROM transcript_segments 
                WHERE transcript_id = ? 
                ORDER BY seq
            """, (record['id'],))
            segments = cur.fetchall()
            
            
            return {
                'job_id': record['job_id'],
                'session_id': record['session_id'],
                'full_text': record['full_text'],
                'audio_duration': record['audio_duration'],
                'timestamp': record['timestamp'],
                'created_at': record['created_at'],
                'segments': [
                    {
                        'seq': seg['seq'],
                        'text': seg['text'],
                        'speaker': seg['speaker'],
                        'start_time': seg['start_time'],
                        'end_time': seg['end_time'],
                        'emotion': seg['emotion'],
                        'emotion_confidence': seg['emotion_confidence'],
                        'emotion_scores': json.loads(seg['emotion_scores']) if seg['emotion_scores'] else None,
                        'audio_metrics': json.loads(seg['audio_metrics']) if seg['audio_metrics'] else None
                    }
                    for seg in segments
                ]
            }
        except Exception as e:
            logger.error(f"Failed to get transcript: {e}")
            return None
    
    def get_recent_transcripts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transcripts for UI with speaker and emotion data"""
        try:
            conn = self._connect()
            cur = conn.cursor()
            
            # Only get transcripts with actual text content
            cur.execute("""
                SELECT * FROM transcript_records 
                WHERE full_text IS NOT NULL AND full_text != ''
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            records = cur.fetchall()
            
            results = []
            for rec in records:
                # Get segments for this transcript
                cur.execute(f"""
                    SELECT speaker, {self.emotion_column} AS emotion, text, emotion_confidence, 
                           emotion_scores, start_time, end_time,
                           word_count, filler_count, pace_wpm, pause_ms,
                           pitch_mean, pitch_std, volume_rms, volume_peak
                    FROM transcript_segments 
                    WHERE transcript_id = ? 
                    ORDER BY seq
                """, (rec['id'],))
                segments = cur.fetchall()
                
                # Extract unique speakers and dominant emotion
                speakers = list(set([seg['speaker'] for seg in segments if seg['speaker']]))
                emotions = [seg['emotion'] for seg in segments if seg['emotion']]
                dominant_emotion = max(set(emotions), key=emotions.count) if emotions else None
                
                results.append({
                    'job_id': rec['job_id'],
                    'session_id': rec['session_id'],
                    'full_text': rec['full_text'],  # Return full text, let frontend handle truncation
                    'audio_duration': rec['audio_duration'],
                    'timestamp': rec['timestamp'],
                    'created_at': rec['created_at'],
                    'speakers': speakers,
                    'dominant_emotion': dominant_emotion,
                    'segment_count': len(segments),
                    'segments': [
                        {
                            'speaker': seg['speaker'],
                            'emotion': seg['emotion'],
                            'text': seg['text'],
                            'emotion_confidence': seg['emotion_confidence'],
                            'start_time': seg['start_time'],
                            'end_time': seg['end_time'],
                            'word_count': seg['word_count'],
                            'filler_count': seg['filler_count'],
                            'pace_wpm': seg['pace_wpm'],
                            'pause_ms': seg['pause_ms'],
                            'pitch_mean': seg['pitch_mean'],
                            'pitch_std': seg['pitch_std'],
                            'volume_rms': seg['volume_rms'],
                            'volume_peak': seg['volume_peak'],
                        }
                        for seg in segments
                    ]
                })
            
            logger.info("[RAG] get_recent_transcripts -> %s transcripts (limit=%s)", len(results), limit)
            return results
        except Exception as e:
            logger.error(f"Failed to get recent transcripts: {e}")
            return []

    def get_emotion_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Aggregate emotion counts across transcript segments"""
        try:
            conn = self._connect()
            cur = conn.cursor()

            conditions = [f"ts.{self.emotion_column} IS NOT NULL", f"ts.{self.emotion_column} != ''"]
            params: List[Any] = []

            if start_date:
                start_iso = f"{start_date}T00:00:00"
                conditions.append("tr.created_at >= ?")
                params.append(start_iso)
            if end_date:
                end_iso = f"{end_date}T23:59:59"
                conditions.append("tr.created_at <= ?")
                params.append(end_iso)

            where_clause = " AND ".join(conditions)

            cur.execute(
                f"""
                SELECT ts.{self.emotion_column} AS emotion, COUNT(*) AS count
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause}
                GROUP BY ts.{self.emotion_column}
                ORDER BY count DESC
                """,
                params,
            )
            rows = cur.fetchall()

            total_analyzed = sum(row["count"] for row in rows)

            # Build per-day trend data within the requested window
            params_for_timeline = list(params)
            cur.execute(
                f"""
                SELECT date(tr.created_at) AS day, ts.{self.emotion_column} AS emotion, COUNT(*) AS count
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause}
                GROUP BY day, ts.{self.emotion_column}
                ORDER BY day ASC
                """,
                params_for_timeline,
            )
            trend_rows = cur.fetchall()

            timeline_map: Dict[str, Dict[str, int]] = {}
            for row in trend_rows:
                day = row.get("day")
                emotion = row.get("emotion")
                if not day or not emotion:
                    continue
                day_map = timeline_map.setdefault(day, {})
                day_map[emotion] = row["count"]

            timeline = [
                {"date": day, "counts": counts}
                for day, counts in sorted(timeline_map.items(), key=lambda item: item[0])
            ]


            return {
                "total_analyzed": total_analyzed,
                "emotions": [
                    {"emotion": row["emotion"], "count": row["count"]}
                    for row in rows
                ],
                "timeline": timeline,
            }
        except Exception as e:
            logger.error(f"[RAG] Failed to compute emotion stats: {e}")
            return {"total_analyzed": 0, "emotions": [], "timeline": []}
    
    def list_memories(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all memories with pagination"""
        logger.info(f"📋 [MEMORY-LIST] Listing memories (limit={limit}, offset={offset})")
        
        try:
            conn = self._connect()
            cur = conn.cursor()
            
            # Check if table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
            if not cur.fetchone():
                logger.warning("⚠️ [MEMORY-LIST] Table 'memories' does not exist")
                return []
            
            # Get paginated memories
            cur.execute("""
                SELECT memory_id, title, body, metadata, created_at 
                FROM memories 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            memories = cur.fetchall()
            
            result = [
                {
                    'memory_id': mem['memory_id'],
                    'title': mem['title'],
                    'body': mem['body'],
                    'metadata': json.loads(mem['metadata']) if mem['metadata'] else {},
                    'created_at': mem['created_at']
                }
                for mem in memories
            ]
            
            logger.info(f"✅ [MEMORY-LIST] Returning {len(result)} memories")
            return result
            
        except Exception as e:
            logger.error(f"❌ [MEMORY-LIST] Failed: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search memories using semantic search"""
        logger.info(f"🔍 [MEMORY-SEARCH] Query: '{query}' (limit={limit})")
        
        try:
            # Use semantic search with type filter
            results = self.search_semantic(
                query=query,
                top_k=limit,
                doc_type='memory'
            )
            
            # Convert to memory format
            memories = []
            for result in results:
                metadata = result.get('metadata', {})
                memories.append({
                    'memory_id': metadata.get('memory_id'),
                    'title': metadata.get('title'),
                    'body': metadata.get('body'),
                    'score': result.get('score'),
                    'metadata': metadata.get('metadata', {}),
                    'created_at': metadata.get('created_at')
                })
            
            logger.info(f"✅ [MEMORY-SEARCH] Returning {len(memories)} results")
            return memories
            
        except Exception as e:
            logger.error(f"❌ [MEMORY-SEARCH] Failed: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _save_faiss_index(self):
        """Save FAISS index and document store to disk"""
        try:
            faiss.write_index(self.faiss_index, str(self.faiss_index_path))
            
            # Save document store
            doc_store_path = Path(str(self.faiss_index_path) + ".docs")
            with open(doc_store_path, 'w', encoding='utf-8') as f:
                json.dump(self.document_store, f)
            
            logger.debug("FAISS index and document store saved")
        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT service authentication (Phase 3: Enforce JWT-only + replay)."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks
        if request.url.path == "/health":
            return await call_next(request)

        if service_auth is None:
            logger.error("❌ Service auth unavailable")
            return JSONResponse(status_code=503, content={"detail": "Service auth unavailable"})

        jwt_token = request.headers.get("X-Service-Token")
        if not jwt_token:
            logger.error(f"❌ Missing JWT for {request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Missing service token"})

        allowed = ["gateway", "transcription-service", "gemma-service"]
        try:
            payload = service_auth.verify_token(jwt_token, allowed_services=allowed, expected_aud="internal")
        except ValueError as exc:
            logger.error(f"❌ JWT rejected: {exc} path={request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Invalid service token"})

        # Replay protection (log + short circuit on failure)
        from shared.security.service_auth import get_replay_protector
        import time as _t

        ttl = max(10, int(payload.get("expires_at", 0) - _t.time()) + 10)
        ok, reason = get_replay_protector().check_and_store(payload.get("request_id", ""), ttl)
        if not ok:
            logger.error(f"❌ JWT replay blocked: reason={reason}")
            return JSONResponse(status_code=401, content={"detail": "Replay detected"})

        rid_short = str(payload.get("request_id", ""))[:8]
        logger.info(f"✅ JWT OK s={payload.get('service_id')} aud=internal rid={rid_short} path={request.url.path}")
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global rag_service, service_auth
    
    logger.info("Starting RAG Service with FAISS vector search...")
    
    # Initialize service auth (Phase 3)
    try:
        from shared.security.secrets import get_secret
        from shared.security.service_auth import get_service_auth, load_service_jwt_keys
        jwt_keys = load_service_jwt_keys("rag-service")
        service_auth = get_service_auth(service_id="rag-service", service_secret=jwt_keys)
        logger.info(
            "✅ JWT service auth initialized (enforcing JWT-only, aud=internal, replay protected, keys=%s)",
            len(jwt_keys),
        )
        rag_db_key = get_secret("rag_db_key")
        if rag_db_key:
            logger.info("RAG DB encryption key loaded from secrets")
        else:
            logger.warning("RAG DB encryption key not found; database will be stored in plaintext")
    except Exception as e:
        logger.error(f"❌ JWT service auth initialization failed: {e}")
        raise

    try:
        rag_service = RAGService(
            db_path=DB_PATH,
            faiss_index_path=FAISS_INDEX_PATH,
            embedding_model_name=EMBEDDING_MODEL,
            db_encryption_key=rag_db_key,
        )
        logger.info("✅ RAG Service started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start RAG Service: {e}")
        raise

    if EMAIL_ANALYZER_ENABLED:
        try:
            from modules.email.db import initialize_database  # type: ignore
            from modules.email import routes as email_routes  # type: ignore

            logger.info("[EMAIL] Initializing encrypted email analyzer database within RAG service...")
            initialize_database()
            app.include_router(email_routes.router, prefix="/email")
            logger.info("[EMAIL] ✅ Email analyzer router mounted on RAG service")
        except Exception as exc:
            logger.error(f"[EMAIL] ❌ Failed to initialize email analyzer: {exc}")
    else:
        logger.info("[EMAIL] Email analyzer disabled via EMAIL_ANALYZER_ENABLED=false")
    
    yield
    
    logger.info("RAG Service shutting down...")


app = FastAPI(
    title="RAG Service",
    version="2.0.0",
    description="Vector-based RAG with FAISS semantic search",
    lifespan=lifespan
)

# Add JWT middleware (Phase 2: Permissive)
app.add_middleware(ServiceAuthMiddleware)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint"""
    docs = 0
    try:
        if rag_service and getattr(rag_service, 'faiss_index', None) is not None:
            docs = int(getattr(rag_service.faiss_index, 'ntotal', 0) or 0)
    except Exception:
        docs = 0
    return {
        "status": "healthy",
        "service": "RAG",
        "version": "2.0.0",
        "faiss_documents": docs,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM
    }


@app.post("/index/transcript")
def index_transcript(
    request: TranscriptIndexRequest,
):
    """Index a full transcript with segments and metadata"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    try:
        # Convert Pydantic models to dicts
        segments_dict = [seg.model_dump() for seg in request.segments]
        
        transcript_id = rag_service.index_transcript(
            job_id=request.job_id,
            session_id=request.session_id,
            full_text=request.full_text,
            audio_duration=request.audio_duration,
            segments=segments_dict
        )
        
        return {
            "success": True,
            "transcript_id": transcript_id,
            "job_id": request.job_id,
            "segments_indexed": len(request.segments)
        }
    except Exception as e:
        logger.error(f"Failed to index transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/semantic")
def search_semantic(
    request: SemanticSearchRequest,
):
    """Semantic search using vector similarity"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    try:
        results = rag_service.search_semantic(
            query=request.query,
            top_k=request.top_k,
            doc_type=request.doc_type,
            start_date=request.start_date,
            end_date=request.end_date,
            last_n_transcripts=request.last_n_transcripts,
            speakers=request.speakers,
            bias_emotions=request.bias_emotions
        )
        
        return {
            "success": True,
            "query": request.query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/add")
def add_memory(
    request: MemoryAddRequest,
):
    """Add a memory/note"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    try:
        memory_id = rag_service.add_memory(
            title=request.title,
            body=request.body,
            metadata=request.metadata
        )
        
        return {
            "success": True,
            "memory_id": memory_id
        }
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transcript/{job_id}")
def get_transcript(
    job_id: str,
):
    """Get full transcript by job_id"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    transcript = rag_service.get_transcript(job_id)
    
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    return {"success": True, "transcript": transcript}


@app.get("/transcripts/recent")
def get_recent_transcripts(
    limit: int = 10,
):
    """Get recent transcripts"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    transcripts = rag_service.get_recent_transcripts(limit=limit)
    logger.info("[RAG] /transcripts/recent API -> %s transcripts (limit=%s)", len(transcripts), limit)
    
    return {
        "success": True,
        "transcripts": transcripts,
        "count": len(transcripts)
    }


@app.get("/transcripts/speakers")
def get_transcript_speakers():
    """Return list of unique speakers for filter dropdowns."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        speakers = rag_service.get_unique_speakers()
        return {"success": True, "speakers": speakers}
    except Exception as e:
        logger.error(f"[RAG] get_transcript_speakers failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load speakers")


@app.get("/debug/transcripts/time-range")
def get_transcript_time_range():
    """Expose dataset coverage info for diagnostics and UI hints."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        return rag_service.get_transcript_time_range()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RAG] transcript time range computation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute transcript time range")


@app.post("/transcripts/count")
def count_transcripts_endpoint(request: Dict[str, Any]):
    """Count transcript segments matching filters."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    filters = request or {}
    try:
        count = rag_service.count_transcripts_filtered(filters)
        return {"success": True, "count": count}
    except Exception as e:
        logger.error(f"[RAG] count_transcripts_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to count transcripts")


@app.post("/transcripts/query")
def query_transcripts_endpoint(request: Dict[str, Any]):
    """Query transcript segments with context for Gemma analyzer."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    filters = request or {}
    try:
        result = rag_service.query_transcripts_filtered(filters)
        payload = {"success": True}
        payload.update(result)
        return payload
    except Exception as e:
        logger.error(f"[RAG] query_transcripts_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to query transcripts")


# ============================================================================
# Analysis Artifact Endpoints
# ============================================================================


@app.post("/analysis/archive")
def archive_analysis_endpoint(request: Dict[str, Any]):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    body = request.get("body")
    if not body:
        raise HTTPException(status_code=400, detail="Artifact body required")

    try:
        artifact_id = rag_service.archive_analysis_artifact(
            artifact_id=request.get("artifact_id"),
            analysis_id=request.get("analysis_id"),
            title=request.get("title"),
            body=body,
            metadata=request.get("metadata"),
            index_body=bool(request.get("index")),
        )
        return {"success": True, "artifact_id": artifact_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[RAG] archive_analysis_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to archive artifact")


@app.get("/analysis/list")
def list_analysis_endpoint(limit: int = 50, offset: int = 0, user_id: Optional[str] = None):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    try:
        result = rag_service.list_analysis_artifacts(limit=limit, offset=offset, user_id=user_id)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[RAG] list_analysis_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list artifacts")


@app.get("/analysis/{artifact_id}")
def get_analysis_endpoint(artifact_id: str):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    try:
        artifact = rag_service.get_analysis_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return {"success": True, "artifact": artifact}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RAG] get_analysis_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load artifact")


@app.post("/analysis/search")
def search_analysis_endpoint(request: Dict[str, Any]):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    query = (request or {}).get("query", "").strip()
    if not query:
        return {"success": True, "items": []}
    try:
        items = rag_service.search_analysis_artifacts(query=query, limit=request.get("limit", 20))
        return {"success": True, "items": items}
    except Exception as e:
        logger.error(f"[RAG] search_analysis_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to search artifacts")


@app.get("/analysis/{artifact_id}/chunks")
def list_artifact_chunks_endpoint(artifact_id: str, limit: int = 20, offset: int = 0):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    try:
        result = rag_service.list_artifact_chunks(artifact_id, limit=limit, offset=offset)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[RAG] list_artifact_chunks_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chunks")


@app.post("/analysis/chunks/search")
def search_artifact_chunks_endpoint(request: Dict[str, Any]):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    query = (request or {}).get("query", "").strip()
    if not query:
        return {"success": True, "items": []}
    artifact_ids = request.get("artifact_ids")
    limit = max(1, min(int(request.get("limit", 20) or 20), 100))
    try:
        items = rag_service.search_artifact_chunks(query, artifact_ids=artifact_ids, limit=limit)
        return {"success": True, "items": items}
    except Exception as e:
        logger.error(f"[RAG] search_artifact_chunks_endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to search chunks")

# ============================================================================
# Memory Endpoints
# ============================================================================

@app.get("/memory/list")
def list_memories(
    limit: int = 100,
    offset: int = 0,
):
    """List all memories with pagination"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    memories = rag_service.list_memories(limit=limit, offset=offset)
    
    return {
        "success": True,
        "memories": memories,
        "count": len(memories)
    }


@app.get("/memory/emotions/stats")
def memory_emotion_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Return aggregated emotion statistics across transcripts"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    stats = rag_service.get_emotion_stats(start_date=start_date, end_date=end_date)

    return {
        "success": True,
        "start_date": start_date,
        "end_date": end_date,
        **stats,
    }

@app.post("/memory/search")
def search_memories(
    request: Dict[str, Any],
):
    """Search memories by query"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    query = request.get("q", request.get("query", ""))
    limit = request.get("top_k", request.get("limit", 10))
    
    memories = rag_service.search_memories(query=query, limit=limit)
    
    return {
        "success": True,
        "memories": memories,
        "count": len(memories)
    }

@app.get("/memory/stats")
def get_memory_stats(
):
    """Get memory statistics"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    
    # Count memories from database
    try:
        conn = rag_service._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM memories WHERE body IS NOT NULL AND body != ''")
        total_memories = cur.fetchone()[0]
        
        return {
            "success": True,
            "total_memories": total_memories,
            "faiss_documents": rag_service.faiss_index.ntotal if rag_service.faiss_index else 0
        }
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {
            "success": True,
            "total_memories": 0,
            "faiss_documents": rag_service.faiss_index.ntotal if rag_service.faiss_index else 0
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004, log_level="info")
