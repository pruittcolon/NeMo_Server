"""
Transcription API Routes

FastAPI endpoints for audio transcription
Extracted from: main3.py lines 621-864

Endpoints:
- POST /transcribe - Transcribe audio file
- GET /result/{job_id} - Get job result
- GET /latest_result - Get latest transcription

Maintains exact backward compatibility with original API
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse

import config
from .service import TranscriptionService
from src.storage.transcript_store import store_transcript_fallback


# Create router
router = APIRouter(prefix="", tags=["transcription"])

# Service instance (will be initialized by main app)
_service: Optional[TranscriptionService] = None


def initialize_service(
    batch_size: int = 1,
    overlap_seconds: float = 0.7,
    upload_dir: Optional[str] = None
) -> TranscriptionService:
    """
    Initialize transcription service
    
    Args:
        batch_size: ASR batch size
        overlap_seconds: Audio overlap for streaming
        upload_dir: Directory for temp files
    
    Returns:
        Initialized TranscriptionService
    """
    global _service
    _service = TranscriptionService(
        batch_size=batch_size,
        overlap_seconds=overlap_seconds,
        upload_dir=upload_dir
    )
    return _service


def get_service() -> TranscriptionService:
    """Get transcription service instance"""
    if _service is None:
        raise RuntimeError("Transcription service not initialized")
    return _service


_LOGS_DIR = Path(getattr(config, "LOGS_DIR", Path.cwd() / "logs"))
_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_storage_log_path = _LOGS_DIR / "storage.log"
_storage_logger = logging.getLogger("storage_logger")
if not _storage_logger.handlers:
    _storage_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(_storage_log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _storage_logger.addHandler(handler)

DB_PATH = Path(getattr(config, "DB_PATH", Path.cwd() / "instance" / "memories.db"))


@router.post("/transcribe")
async def transcribe_chunk(
    audio: UploadFile = File(...),
    seq: Optional[int] = Form(None),
    stream_id: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """
    Transcribe audio file
    
    Accepts audio in any format (will be converted to 16kHz mono WAV)
    Supports streaming with overlap caching using stream_id
    
    Args:
        audio: Audio file upload
        seq: Optional sequence number for streaming
        stream_id: Optional stream identifier for overlap caching
    
    Returns:
        {
            "seq": int or null,
            "segments": [
                {
                    "start": float,
                    "end": float,
                    "text": str,
                    "speaker": str,  # Will be "SPK" initially, updated by speaker service
                    "speaker_raw": str,
                    "speaker_confidence": float or null,
                    "emotion": str,  # Will be added by emotion service
                    "emotion_confidence": float,
                    "emotions": {...}
                }
            ]
        }
    
    Raises:
        HTTPException: 500 if transcription fails
    """
    service = get_service()
    
    try:
        # Read uploaded file
        audio_data = await audio.read()
        
        # Transcribe
        result = service.transcribe(
            audio_data=audio_data,
            filename=audio.filename or "audio.wav",
            stream_id=stream_id,
            seq=seq
        )
        
        # Speaker diarization
        audio_path = result.get("audio_path")
        if audio_path and result["segments"]:
            try:
                from src.services.speaker.routes import get_service as get_speaker_service
                speaker_service = get_speaker_service()
                
                # Diarize segments with enrolled speakers
                # Load ALL enrolled speakers dynamically
                enrolled_speakers = speaker_service.get_enrolled_speakers()
                if not enrolled_speakers:
                    enrolled_speakers = ["pruitt"]  # Fallback
                    
                print(f"[TRANSCRIPTION API] Using enrolled speakers: {enrolled_speakers}")
                diarized_segments = speaker_service.diarize_segments(
                    audio_path=audio_path,
                    segments=result["segments"],
                    enrollment_speakers=enrolled_speakers
                )
                result["segments"] = diarized_segments
                print(f"[TRANSCRIPTION API] ✓ Diarization complete: {len(diarized_segments)} segments")
                
                # TV Detection using acoustic analysis
                try:
                    from src.services.speaker.tv_detector import get_tv_detector
                    tv_detector = get_tv_detector()
                    
                    # Count pruitt matches
                    pruitt_count = sum(1 for seg in diarized_segments if seg.get("speaker", "").lower() == "pruitt")
                    
                    # Detect TV audio
                    tv_result = tv_detector.is_television(
                        audio_path=audio_path,
                        segments=diarized_segments,
                        pruitt_match_count=pruitt_count
                    )
                    
                    print(f"[TV_DETECTOR] TV={tv_result['is_tv']}, confidence={tv_result['confidence']:.2f}, reason={tv_result['reason']}")
                    
                    # If TV detected, relabel non-pruitt speakers as "television"
                    if tv_result['is_tv']:
                        for seg in diarized_segments:
                            if seg.get("speaker", "").lower() != "pruitt":
                                seg["speaker"] = "television"
                                seg["speaker_confidence"] = tv_result['confidence']
                        print(f"[TV_DETECTOR] ✓ Relabeled {len(diarized_segments) - pruitt_count} segments as 'television'")
                    
                except Exception as tv_e:
                    print(f"[TV_DETECTOR] TV detection failed: {tv_e}")
                    import traceback
                    traceback.print_exc()
                
            except Exception as e:
                print(f"[TRANSCRIPTION API] Diarization failed: {e}")
                # Continue without diarization - segments still have [SPK] labels
        
        # Emotion analysis (j-hartmann model: anger, disgust, fear, joy, neutral, sadness, surprise)
        if result["segments"]:
            try:
                from src.services.emotion.routes import get_service as get_emotion_service
                emotion_service = get_emotion_service()
                
                # Analyze emotion for each segment
                for segment in result["segments"]:
                    text = segment.get("text", "")
                    if text and text.strip():
                        emotion_result = emotion_service.analyze(text)
                        segment["emotion"] = emotion_result.get("dominant_emotion", "neutral")
                        segment["emotion_confidence"] = emotion_result.get("confidence", 0.0)
                        segment["emotion_scores"] = emotion_result.get("emotions", {})
                    else:
                        segment["emotion"] = "neutral"
                        segment["emotion_confidence"] = 0.0
                        segment["emotion_scores"] = {}
                
                print(f"[TRANSCRIPTION API] ✓ Emotion analysis complete: {len(result['segments'])} segments")
                
            except Exception as e:
                print(f"[TRANSCRIPTION API] Emotion analysis failed: {e}")
                import traceback
                traceback.print_exc()
                # Continue without emotion analysis - segments will have neutral
                for segment in result["segments"]:
                    if "emotion" not in segment:
                        segment["emotion"] = "neutral"
                        segment["emotion_confidence"] = 0.0
                        segment["emotion_scores"] = {}
        
        # Clean up audio file after processing
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass
        
        text_value = result.get('text', '')
        _storage_logger.info(
            "Transcription summary job=%s chars=%d segments=%d stream=%s",
            result.get("job_id"),
            len(text_value or ""),
            len(result.get("segments") or []),
            stream_id
        )

        # === Store transcript in database + FAISS index ===
        persisted = False
        if text_value and text_value.strip():
            try:
                from src.services.rag.routes import get_service as get_rag_service
                rag_service = get_rag_service()
                
                if rag_service:
                    _storage_logger.info(
                        "Persisting transcription job=%s seq=%s stream=%s to %s",
                        result.get("job_id"),
                        seq,
                        stream_id,
                        DB_PATH
                    )
                    db_parent = DB_PATH.parent
                    db_parent.mkdir(parents=True, exist_ok=True)
                    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
                    _storage_logger.info(
                        "Current DB size before write: %.2f KB", db_size / 1024
                    )

                    # Calculate audio duration from segments
                    audio_duration = 0.0
                    if result['segments']:
                        last_seg = result['segments'][-1]
                        audio_duration = last_seg.get('end', 0.0)
                    
                    # Store in database + FAISS
                    transcript_id = rag_service.memory_service.add_transcript(
                        text=result['text'],
                        segments=result['segments'],
                        job_id=result.get('job_id', f'stream_{stream_id}'),
                        session_id=stream_id or 'default',
                        audio_duration=audio_duration
                    )
                    
                    print(f"[TRANSCRIPTION API] ✓ Stored transcript {transcript_id} with {len(result['segments'])} segments")
                    print(f"[TRANSCRIPTION API] ✓ Added to FAISS index for Gemma search")
                    new_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
                    _storage_logger.info(
                        "Stored transcript_id=%s segments=%d duration=%.2fs | DB size now %.2f KB",
                        transcript_id,
                        len(result['segments']),
                        audio_duration,
                        new_size / 1024
                    )
                    persisted = True
                else:
                    print("[TRANSCRIPTION API] Warning: RAG service not available")
                    _storage_logger.warning(
                        "RAG service unavailable, skipping persistence for job=%s",
                        result.get("job_id")
                    )
                    
            except Exception as e:
                print(f"[TRANSCRIPTION API] Warning: Could not store transcript: {e}")
                import traceback
                traceback.print_exc()
                _storage_logger.exception(
                    "Failed to persist job=%s stream=%s: %s",
                    result.get("job_id"),
                    stream_id,
                    e
                )
                # Continue - transcription still works, just not stored
        
        if (not text_value or not text_value.strip()) and result.get("segments"):
            _storage_logger.info(
                "Transcript text empty but segments exist for job=%s, using fallback storage.",
                result.get("job_id")
            )
        
        if not persisted and result.get("segments"):
            try:
                fallback_job_id = result.get("job_id") or (stream_id or f"job_{seq or '0'}")
                fallback_session = stream_id or "default"
                audio_duration = 0.0
                if result['segments']:
                    audio_duration = result['segments'][-1].get('end', 0.0) or audio_duration
                fallback_id = store_transcript_fallback(
                    DB_PATH,
                    text_value or " ",
                    result["segments"],
                    fallback_job_id,
                    fallback_session,
                    audio_duration,
                )
                _storage_logger.info(
                    "Fallback stored transcript_id=%s segments=%d duration=%.2fs (job=%s)",
                    fallback_id,
                    len(result["segments"]),
                    audio_duration,
                    fallback_job_id,
                )
            except Exception as fallback_error:
                _storage_logger.exception(
                    "Fallback persistence failed for job=%s: %s",
                    result.get("job_id"),
                    fallback_error,
                )
        elif not persisted:
            _storage_logger.warning(
                "No segments available for job=%s; nothing persisted.",
                result.get("job_id")
            )
        else:
            _storage_logger.info(
                "Skipping persistence for job=%s (empty transcript text)",
                result.get("job_id")
            )
        
        # Format response (matches original API format)
        payload = {
            "seq": seq,
            "segments": result["segments"]
        }
        
        # Log API response for debugging
        segment_texts = [s.get('text', '') for s in result['segments']]
        print(f"[TRANSCRIPTION API] Response: {len(segment_texts)} segments")
        print(f"[TRANSCRIPTION API] Full text: '{result.get('text', '')}'")
        
        return payload
        
    except RuntimeError as e:
        print(f"[TRANSCRIPTION API] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"[TRANSCRIPTION API] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")


@router.get("/result/{job_id}")
def get_result(job_id: str) -> Dict[str, Any]:
    """
    Get transcription result by job ID
    
    Args:
        job_id: Job identifier
    
    Returns:
        Job result with status and transcription
    
    Raises:
        HTTPException: 404 if job not found
    """
    service = get_service()
    
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@router.get("/latest_result", response_class=PlainTextResponse)
def get_latest_result() -> str:
    """
    Get latest transcription result as plain text
    
    Returns:
        Latest transcribed text or "No transcription yet."
    """
    service = get_service()
    return service.get_latest_result()


@router.get("/transcription/stats")
def get_transcription_stats() -> Dict[str, Any]:
    """
    Get transcription service statistics
    
    Returns:
        Service stats including model status, job count, etc.
    """
    service = get_service()
    return service.get_stats()


@router.delete("/stream/{stream_id}")
def clear_stream(stream_id: str) -> Dict[str, str]:
    """
    Clear overlap cache for a stream
    
    Args:
        stream_id: Stream identifier
    
    Returns:
        Success message
    """
    service = get_service()
    service.clear_stream(stream_id)
    return {"status": "ok", "message": f"Stream {stream_id} cleared"}
