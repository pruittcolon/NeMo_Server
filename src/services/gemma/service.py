"""
Gemma AI Analysis Service

**CRITICAL: This service gets EXCLUSIVE GPU access**
All other services (ASR, Speaker, Embedding, Emotion) run on CPU

Wrapper around existing gemma_context_analyzer.py
As per user request: "I WANT gemma_context_analyzer.py to remain AS IS"

This service provides:
- GPU-only enforcement for Gemma LLM
- Job queue management for long-running analyses
- WebSocket progress broadcasting
- Personality analysis, emotional triggers, summaries

Key GPU Control:
- Docker: Only this container sees GPU (deploy.resources.reservations.devices)
- Environment: CUDA_VISIBLE_DEVICES set to allow GPU
- llama-cpp-python: n_gpu_layers=-1 (all layers on GPU)
"""

import os
import sys
import uuid
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from collections import deque

# Import our GPU utilities
parent_refactored = str(Path(__file__).parent.parent.parent)
if parent_refactored not in sys.path:
    sys.path.insert(0, parent_refactored)

from src.utils.gpu_utils import clear_gpu_cache, log_vram_usage, enforce_gpu_only

# Import config and existing analyzer from parent src
parent_src = str(Path(__file__).parent.parent.parent.parent / "src")
if parent_src not in sys.path:
    sys.path.insert(0, parent_src)

try:
    # Import existing GemmaContextAnalyzer unchanged
    from gemma_context_analyzer import GemmaContextAnalyzer
    print("[GEMMA] Successfully imported GemmaContextAnalyzer")
except ImportError as e:
    print(f"[GEMMA] ERROR: Failed to import GemmaContextAnalyzer: {e}")
    print("[GEMMA] Ensure src/gemma_context_analyzer.py exists and is importable")
    GemmaContextAnalyzer = None

try:
    import config
    GEMMA_MODEL_PATH = getattr(config, 'GEMMA_MODEL_PATH', "/app/models/gemma-3-4b-it-Q4_K_M.gguf")
    MAX_GEMMA_CONTEXT_TOKENS = getattr(config, 'MAX_GEMMA_CONTEXT_TOKENS', 8192)
except (ImportError, AttributeError):
    # Fallback defaults
    GEMMA_MODEL_PATH = "/app/models/gemma-3-4b-it-Q4_K_M.gguf"
    MAX_GEMMA_CONTEXT_TOKENS = 8192
    print("[GEMMA] WARNING: config.py not found, using fallback defaults")


class JobStatus:
    """Job status constants"""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class GemmaJob:
    """Represents a Gemma analysis job"""
    
    def __init__(
        self,
        job_id: str,
        job_type: str,
        params: Dict[str, Any],
        created_by_user_id: Optional[str] = None  # NEW: Track which user created the job
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.params = params
        self.created_by_user_id = created_by_user_id  # NEW: For speaker isolation
        self.status = JobStatus.QUEUED
        self.progress = 0.0
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
    
    def start(self) -> None:
        """Mark job as started"""
        self.status = JobStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
    
    def complete(self, result: Dict[str, Any]) -> None:
        """Mark job as completed"""
        self.status = JobStatus.COMPLETED
        self.result = result
        self.progress = 1.0
        self.completed_at = datetime.utcnow()
    
    def fail(self, error: str) -> None:
        """Mark job as failed"""
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = datetime.utcnow()
    
    def update_progress(self, progress: float, message: Optional[str] = None) -> None:
        """Update job progress"""
        self.progress = max(0.0, min(1.0, progress))
        if message:
            self.params["progress_message"] = message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary"""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_by_user_id": self.created_by_user_id,  # NEW: Include user ID for access control
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class GemmaService:
    """
    Gemma AI analysis service with EXCLUSIVE GPU access
    
    **GPU Enforcement:**
    - This service runs in separate Docker container with GPU access
    - All other services have CUDA_VISIBLE_DEVICES=""
    - llama-cpp-python loads all layers on GPU (n_gpu_layers=-1)
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        max_context_tokens: int = MAX_GEMMA_CONTEXT_TOKENS,
        enforce_gpu: bool = True
    ):
        """
        Initialize Gemma service
        
        Args:
            model_path: Path to Gemma GGUF model
            max_context_tokens: Maximum context window size
            enforce_gpu: If True, enforce GPU-only operation
        """
        if GemmaContextAnalyzer is None:
            raise RuntimeError("GemmaContextAnalyzer not available")
        
        self.model_path = model_path or GEMMA_MODEL_PATH
        self.max_context_tokens = max_context_tokens
        self.enforce_gpu = enforce_gpu
        
        # Job management
        self.jobs: Dict[str, GemmaJob] = {}
        self.job_queue: deque = deque()
        self.processing_lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.should_stop = False
        
        # WebSocket broadcast callback (set by FastAPI app)
        self.broadcast_callback: Optional[Callable] = None
        
        # Gemma analyzer (will be initialized on first use)
        self.analyzer: Optional[GemmaContextAnalyzer] = None
        self.analyzer_lock = threading.Lock()
        
        print(f"[GEMMA] Service initialized (model={self.model_path}, enforce_gpu={enforce_gpu})")
        
        # Start job worker thread
        self._start_worker()
    
    def _ensure_gpu_access(self) -> None:
        """Ensure this service has GPU access"""
        if self.enforce_gpu:
            # Allow GPU access (undo any CPU-only restrictions)
            enforce_gpu_only(device_id=0)
            print("[GEMMA] ✅ GPU access enabled (CUDA_VISIBLE_DEVICES set)")
    
    def _load_analyzer(self) -> None:
        """Load Gemma analyzer (GPU-only)"""
        with self.analyzer_lock:
            if self.analyzer is not None:
                return  # Already loaded
            
            print("[GEMMA] Loading Gemma analyzer on GPU...")
            
            # Ensure GPU access
            self._ensure_gpu_access()
            
            # Clear GPU cache before loading
            clear_gpu_cache()
            log_vram_usage("[GEMMA] Before loading")
            
            try:
                # Get memory service from RAG for GemmaContextAnalyzer
                try:
                    from src.services.rag.routes import get_service as get_rag_service
                    rag_service = get_rag_service()
                    memory_service = rag_service.memory_service if rag_service else None
                except Exception as e:
                    print(f"[GEMMA] Warning: Could not get memory service: {e}")
                    memory_service = None
                
                if memory_service is None:
                    raise RuntimeError("Memory service not available - required for GemmaContextAnalyzer")
                
                # Initialize analyzer (it will load Gemma on GPU)
                # GemmaContextAnalyzer only takes memory_service as parameter
                self.analyzer = GemmaContextAnalyzer(memory_service=memory_service)
                
                print("[GEMMA] ✅ Gemma analyzer loaded successfully on GPU")
                log_vram_usage("[GEMMA] After loading")
                
            except Exception as e:
                print(f"[GEMMA] ❌ ERROR: Failed to load Gemma analyzer: {e}")
                raise RuntimeError(f"Failed to load Gemma analyzer: {e}")
    
    def _start_worker(self) -> None:
        """Start background worker thread for job processing"""
        if self.worker_thread is not None and self.worker_thread.is_alive():
            return  # Already running
        
        self.should_stop = False
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[GEMMA] Background worker thread started")
    
    def _worker_loop(self) -> None:
        """Background worker loop for processing jobs"""
        print("[GEMMA] Worker loop started")
        
        while not self.should_stop:
            try:
                # Get next job from queue
                with self.processing_lock:
                    if len(self.job_queue) == 0:
                        # No jobs, sleep briefly
                        import time
                        time.sleep(0.5)
                        continue
                    
                    job_id = self.job_queue.popleft()
                    job = self.jobs.get(job_id)
                    
                    if job is None:
                        continue
                
                # Process job
                self._process_job(job)
                
            except Exception as e:
                print(f"[GEMMA] Worker error: {e}")
        
        print("[GEMMA] Worker loop stopped")
    
    def _process_job(self, job: GemmaJob) -> None:
        """Process a single job"""
        print(f"[GEMMA] Processing job {job.job_id} (type={job.job_type})")
        
        job.start()
        self._broadcast_job_update(job)
        
        try:
            # Ensure analyzer is loaded
            if self.analyzer is None:
                self._load_analyzer()
            
            # Route to appropriate handler
            if job.job_type == "personality_analysis":
                result = self._run_personality_analysis(job)
            elif job.job_type == "emotional_triggers":
                result = self._run_emotional_triggers(job)
            elif job.job_type == "gemma_summary":
                result = self._run_gemma_summary(job)
            elif job.job_type == "comprehensive":
                result = self._run_comprehensive_analysis(job)
            elif job.job_type == "multi_stage_analysis":
                result = self._run_multi_stage_analysis(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
            
            # Mark as completed
            job.complete(result)
            print(f"[GEMMA] ✅ Job {job.job_id} completed")
            
        except Exception as e:
            print(f"[GEMMA] ❌ Job {job.job_id} failed: {e}")
            job.fail(str(e))
        
        finally:
            self._broadcast_job_update(job)
    
    def _broadcast_job_update(self, job: GemmaJob, extra_data: Dict[str, Any] = None) -> None:
        """
        Broadcast job update via WebSocket if callback is set
        
        Args:
            job: The Gemma job to broadcast
            extra_data: Optional extra data to merge into the broadcast (e.g., live_prompt)
        """
        if self.broadcast_callback:
            try:
                job_dict = job.to_dict()
                if extra_data:
                    job_dict.update(extra_data)
                self.broadcast_callback(job_dict)
            except Exception as e:
                print(f"[GEMMA] Broadcast error: {e}")
    
    def _run_personality_analysis(self, job: GemmaJob) -> Dict[str, Any]:
        """Run personality analysis"""
        segments = job.params.get("segments", [])
        
        job.update_progress(0.1, "Analyzing personality traits...")
        self._broadcast_job_update(job)
        
        result = self.analyzer.analyze_personality(segments)
        
        job.update_progress(0.9, "Finalizing analysis...")
        self._broadcast_job_update(job)
        
        return result
    
    def _run_emotional_triggers(self, job: GemmaJob) -> Dict[str, Any]:
        """Run emotional trigger detection"""
        segments = job.params.get("segments", [])
        
        job.update_progress(0.1, "Detecting emotional triggers...")
        self._broadcast_job_update(job)
        
        result = self.analyzer.detect_emotional_triggers(segments)
        
        job.update_progress(0.9, "Finalizing triggers...")
        self._broadcast_job_update(job)
        
        return result
    
    def _run_gemma_summary(self, job: GemmaJob) -> Dict[str, Any]:
        """Run Gemma summary generation using actual LLM"""
        context = job.params.get("context", {})
        user_message = context.get("user_message", "")
        
        job.update_progress(0.1, "Generating response...")
        self._broadcast_job_update(job)
        
        try:
            # Access LLM via analyzer's memory_service
            if not hasattr(self.analyzer, 'memory_service') or not hasattr(self.analyzer.memory_service, '_llm'):
                raise RuntimeError("LLM not available in memory service")
            
            llm = self.analyzer.memory_service._llm
            
            # Create a conversational prompt
            prompt = f"""You are Gemma AI, a helpful and friendly assistant. Answer the user's question naturally and concisely in 2-3 sentences.

User: {user_message}

Gemma:"""
            
            job.update_progress(0.3, "Generating response...")
            self._broadcast_job_update(job)
            
            # Generate response using LLM
            response = llm(
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_p=0.9,
                repeat_penalty=1.1,
                stop=["User:", "\n\n"]
            )
            
            summary_text = response['choices'][0]['text'].strip()
            
            job.update_progress(0.9, "Finalizing response...")
            self._broadcast_job_update(job)
            
            result = {
                "summary": summary_text,
                "analysis_type": "chat",
                "timestamp": str(datetime.utcnow())
            }
            
            return result
            
        except Exception as e:
            print(f"[GEMMA] Error generating response: {e}")
            # Fallback to simple response if LLM fails
            return {
                "summary": f"I'm sorry, I encountered an error generating a response. Error: {str(e)}",
                "analysis_type": "chat",
                "timestamp": str(datetime.utcnow())
            }
    
    def _run_comprehensive_analysis(self, job: GemmaJob) -> Dict[str, Any]:
        """Run comprehensive analysis (all analyses combined)"""
        segments = job.params.get("segments", [])

        job.update_progress(0.1, "Starting comprehensive analysis...")
        self._broadcast_job_update(job)

        result = self.analyzer.comprehensive_analysis(segments)

        job.update_progress(0.9, "Finalizing comprehensive analysis...")
        self._broadcast_job_update(job)

        return result
    
    def _run_multi_stage_analysis(self, job: GemmaJob) -> Dict[str, Any]:
        """
        Run optimized multi-stage comprehensive analysis
        
        Process:
        1. For each emotion, analyze last 5 transcriptions (internal only)
        2. Calculate ETA from first 5 analyses
        3. Meta-analyze for:
           - Common themes with exact quotes
           - Logical fallacies with justification
           - Factual errors with evidence
           - Root causes with supporting text
        
        Returns ONLY meta-analysis (not individual emotions) for efficiency
        """
        import time
        
        print(f"[MULTI_STAGE] ━━━━━ STARTING ANALYSIS ━━━━━")
        print(f"[MULTI_STAGE] Job params: {job.params}")
        
        job.update_progress(0.05, "Starting analysis...")
        self._broadcast_job_update(job)
        
        # Get parameters
        filters = job.params.get("filters", {})
        speakers = filters.get("speakers", [])
        emotions = filters.get("emotions", [])
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        limit_per_emotion = filters.get("limit_per_emotion", 5)
        
        print(f"[MULTI_STAGE] Filters: speakers={speakers}, emotions={emotions}, limit={limit_per_emotion}")
        
        # Timing for ETA calculation
        analysis_times = []
        start_time = time.time()
        
        # Import database access
        import sqlite3
        from src import config
        
        # ⚡ FIX: Use the correct database path where transcripts are actually stored
        db_path = "/instance/memory.db"  # The REAL database with 1400+ segments
        print(f"[MULTI_STAGE] Using database: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Stage 1: Analyze each emotion separately
        emotion_analyses = []
        total_emotions = len(emotions) if emotions else 7  # 7 emotions in j-hartmann
        
        print(f"[MULTI_STAGE] total_emotions={total_emotions}, emotions list={emotions}")
        
        if not emotions:
            # Default: all emotions
            emotions = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]
        
        print(f"[MULTI_STAGE] Starting loop over {len(emotions)} emotions...")
        
        for i, emotion in enumerate(emotions):
            print(f"[MULTI_STAGE] ━━━ Processing emotion {i+1}/{len(emotions)}: {emotion} ━━━")
            emotion_start = time.time()
            
            # Calculate ETA after first 5 analyses
            if i >= 5 and analysis_times:
                avg_time = sum(analysis_times[:5]) / 5
                remaining = total_emotions - i
                eta_seconds = avg_time * remaining
                eta_minutes = int(eta_seconds / 60)
                eta_text = f"ETA: ~{eta_minutes}min" if eta_minutes > 0 else f"ETA: ~{int(eta_seconds)}s"
            else:
                eta_text = "Calculating ETA..."
            
            progress = 0.1 + (i / total_emotions) * 0.6  # 10% to 70%
            job.update_progress(progress, f"Analyzing {emotion} ({i+1}/{len(emotions)}) - {eta_text}")
            
            # Broadcast live prompt status
            self._broadcast_job_update(job, extra_data={
                "live_prompt": {
                    "index": i + 1,
                    "total": len(emotions),
                    "emotion": emotion,
                    "status": "preparing"
                }
            })
            
            try:
                # Build query for this emotion
                query = """
                    SELECT 
                        ts.id, ts.text, ts.speaker, ts.emotion, 
                        ts.start_time, ts.end_time, ts.created_at,
                        tr.full_text
                    FROM transcript_segments ts
                    LEFT JOIN transcript_records tr ON ts.transcript_id = tr.id
                    WHERE ts.emotion = ?
                """
                params = [emotion]
                
                # Apply filters
                if speakers:
                    placeholders = ','.join('?' * len(speakers))
                    query += f" AND ts.speaker IN ({placeholders})"
                    params.extend(speakers)
                
                if start_date:
                    query += " AND ts.created_at >= ?"
                    params.append(start_date)
                
                if end_date:
                    query += " AND ts.created_at <= ?"
                    params.append(end_date)
                
                query += f" ORDER BY ts.created_at DESC LIMIT ?"
                params.append(limit_per_emotion)
                
                print(f"[MULTI_STAGE] Executing query for {emotion}...")
                print(f"[MULTI_STAGE] Query: {query}")
                print(f"[MULTI_STAGE] Params: {params}")
                cur.execute(query, params)
                rows = cur.fetchall()
                print(f"[MULTI_STAGE] Found {len(rows)} rows for {emotion}")
                
                if len(rows) == 0:
                    print(f"[MULTI_STAGE] No rows found for {emotion}, skipping...")
                    continue
                
                # Format with context: Previous statements + target statement
                # Last statement is the one to analyze, previous ones are context
                context_statements = []
                target_statement = None
                
                for idx, row in enumerate(rows):
                    statement = f'[{row["speaker"]}] {row["text"]}'
                    if idx < len(rows) - 1:
                        context_statements.append(f"{idx+1}. {statement}")
                    else:
                        target_statement = statement
                
                context_text = "\n".join(context_statements) if context_statements else "No prior context"
                
                # Structured prompt with context + target
                prompt = f"""These previous {len(context_statements)} statements lead to the final statement which you need to analyze for {emotion}:

CONTEXT (Previous statements):
{context_text}

ANALYZE THIS ONE BELOW:
{len(rows)}. {target_statement}

Respond with (BE SPECIFIC):
Common theme is: [Your best guess at the theme, no matter what]
Logical fallacies were: [NA or specific fallacy with EXACT QUOTE, e.g., "Ad hominem: 'He sucks'"]
Factual errors were: [NA or specific error with correction, e.g., "'Jupiter has 1 moon' - actually has 95"]
Root causes were: [What triggered the emotion? Cite EXACT WORDS]"""
                
                # Broadcast prompt being sent
                self._broadcast_job_update(job, extra_data={
                    "live_prompt": {
                        "index": i + 1,
                        "total": len(emotions),
                        "emotion": emotion,
                        "status": "sent",
                        "context": context_statements,
                        "target": target_statement,
                        "prompt": prompt
                    }
                })
                
                # Generate analysis using LLM (shorter output for token efficiency)
                if hasattr(self.analyzer, 'memory_service') and hasattr(self.analyzer.memory_service, '_llm'):
                    llm = self.analyzer.memory_service._llm
                    response = llm(
                        prompt=prompt,
                        max_tokens=200,  # Reduced from 500 for speed
                        temperature=0.7,
                        top_p=0.9
                    )
                    
                    analysis_text = response['choices'][0]['text'].strip()
                    
                    # Broadcast response received
                    self._broadcast_job_update(job, extra_data={
                        "live_prompt": {
                            "index": i + 1,
                            "total": len(emotions),
                            "emotion": emotion,
                            "status": "responded",
                            "context": context_statements,
                            "target": target_statement,
                            "prompt": prompt,
                            "response": analysis_text
                        }
                    })
                    
                    # Store detailed analysis (NOW shown to user)
                    emotion_analyses.append({
                        "emotion": emotion,
                        "speaker": speakers[0] if len(speakers) == 1 else "multiple",
                        "sample_count": len(rows),
                        "context_statements": context_statements,
                        "target_statement": target_statement,
                        "prompt_sent": prompt,  # Show user what was sent to Gemma
                        "gemma_response": analysis_text  # Show Gemma's response
                    })
                else:
                    emotion_analyses.append({
                        "emotion": emotion,
                        "speaker": speakers[0] if len(speakers) == 1 else "multiple",
                        "sample_count": len(rows),
                        "context_statements": context_statements,
                        "target_statement": target_statement,
                        "prompt_sent": prompt,
                        "gemma_response": f"Analysis unavailable (LLM not loaded)"
                    })
                
                # Track timing for ETA
                emotion_time = time.time() - emotion_start
                analysis_times.append(emotion_time)
                    
            except Exception as e:
                print(f"[MULTI_STAGE] Error analyzing {emotion}: {e}")
                analysis_times.append(0)  # Add placeholder for failed analyses
                continue
        
        conn.close()
        
        # Stage 2: Meta-analysis (the ONLY output shown to user)
        job.update_progress(0.75, "Synthesizing cross-emotional patterns...")
        self._broadcast_job_update(job)
        
        # Chunk analyses if too long (prevent token overflow)
        MAX_CHUNK_SIZE = 6  # Max 6 emotions per chunk
        emotion_chunks = [emotion_analyses[i:i+MAX_CHUNK_SIZE] for i in range(0, len(emotion_analyses), MAX_CHUNK_SIZE)]
        
        meta_analyses = []
        
        for chunk_idx, chunk in enumerate(emotion_chunks):
            # Combine analyses for this chunk (condensed format)
            chunk_text = "\n\n".join([
                f"{ea['emotion'].upper()} ({ea['sample_count']} samples): {ea.get('gemma_response', ea.get('analysis', 'N/A'))}"
                for ea in chunk
            ])
            
            # Meta-analysis prompt with explicit quote requirements
            meta_prompt = f"""Analyze these {len(chunk)} emotions. For cross-emotional insights:

{chunk_text}

Identify (BE SPECIFIC):
1. COMMON THEMES: What patterns appear across emotions? Provide EXACT QUOTES as evidence.
2. LOGICAL FALLACIES: What reasoning errors? Name the fallacy, provide EXACT TEXT showing it.
3. FACTUAL ERRORS: What mistakes? Provide EXACT STATEMENT that is incorrect.
4. ROOT CAUSES: What deeper causes? Cite EXACT WORDS revealing the pattern.

Format: [Category]: [Finding]. EVIDENCE: "exact quote here"."""
        
            # Generate meta-analysis for this chunk
            if hasattr(self.analyzer, 'memory_service') and hasattr(self.analyzer.memory_service, '_llm'):
                llm = self.analyzer.memory_service._llm
                meta_response = llm(
                    prompt=meta_prompt,
                    max_tokens=500,  # Reduced from 800
                    temperature=0.7,
                    top_p=0.9
                )
                
                chunk_analysis = meta_response['choices'][0]['text'].strip()
                meta_analyses.append(chunk_analysis)
            else:
                meta_analyses.append(f"Chunk {chunk_idx+1} analysis unavailable (LLM not loaded)")
        
        # Combine all chunk meta-analyses
        if len(meta_analyses) > 1:
            # If multiple chunks, synthesize them
            meta_analysis = "\n\n---\n\n".join([
                f"ANALYSIS PART {i+1}:\n{ma}" for i, ma in enumerate(meta_analyses)
            ])
        else:
            meta_analysis = meta_analyses[0] if meta_analyses else "Analysis unavailable"
        
        job.update_progress(0.95, "Finalizing analysis...")
        self._broadcast_job_update(job)
        
        # Calculate total time
        total_time = time.time() - start_time
        avg_time_per_emotion = total_time / len(emotion_analyses) if emotion_analyses else 0
        
        # Return BOTH individual analyses AND meta-analysis
        return {
            "summary": f"Analyzed {len(emotion_analyses)} emotions in {int(total_time)}s",
            "individual_analyses": emotion_analyses,  # NEW: Show per-emotion details
            "meta_analysis": meta_analysis,
            "filters_applied": filters,
            "total_emotions": len(emotion_analyses),
            "total_samples": sum(ea['sample_count'] for ea in emotion_analyses),
            "processing_time_seconds": int(total_time),
            "avg_time_per_emotion_seconds": round(avg_time_per_emotion, 1),
            "timestamp": str(datetime.utcnow())
        }
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def submit_job(
        self,
        job_type: str,
        params: Dict[str, Any],
        created_by_user_id: Optional[str] = None  # NEW: Track which user created the job
    ) -> str:
        """
        Submit analysis job to queue
        
        Args:
            job_type: Type of analysis ("personality_analysis", "emotional_triggers", etc.)
            params: Job parameters
            created_by_user_id: Optional user ID for speaker isolation tracking
        
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        job = GemmaJob(
            job_id=job_id,
            job_type=job_type,
            params=params,
            created_by_user_id=created_by_user_id  # NEW: Pass user ID to job
        )
        
        with self.processing_lock:
            self.jobs[job_id] = job
            self.job_queue.append(job_id)
        
        print(f"[GEMMA] Job {job_id} submitted (type={job_type}, user={created_by_user_id})")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status and result"""
        job = self.jobs.get(job_id)
        return job.to_dict() if job else None
    
    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent jobs"""
        job_list = list(self.jobs.values())
        job_list.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in job_list[:limit]]
    
    def set_broadcast_callback(self, callback: Callable) -> None:
        """Set WebSocket broadcast callback"""
        self.broadcast_callback = callback
        print("[GEMMA] WebSocket broadcast callback registered")
    
    def stop(self) -> None:
        """Stop the service"""
        self.should_stop = True
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
        print("[GEMMA] Service stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        import torch
        
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
        
        return {
            "analyzer_loaded": self.analyzer is not None,
            "gpu_available": gpu_available,
            "gpu_name": gpu_name,
            "model_path": self.model_path,
            "max_context_tokens": self.max_context_tokens,
            "total_jobs": len(self.jobs),
            "queued_jobs": len(self.job_queue),
            "worker_active": self.worker_thread.is_alive() if self.worker_thread else False
        }


