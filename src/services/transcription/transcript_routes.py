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

import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse

from .service import TranscriptionService


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
                diarized_segments = speaker_service.diarize_segments(
                    audio_path=audio_path,
                    segments=result["segments"],
                    enrollment_speakers=["pruitt", "ericah"]  # From config
                )
                result["segments"] = diarized_segments
                print(f"[TRANSCRIPTION API] ✓ Diarization complete: {len(diarized_segments)} segments")
                
            except Exception as e:
                print(f"[TRANSCRIPTION API] Diarization failed: {e}")
                # Continue without diarization - segments still have [SPK] labels
        
        # Clean up audio file after diarization
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass
        
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


