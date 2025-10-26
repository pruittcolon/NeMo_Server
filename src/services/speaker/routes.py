"""
Speaker Enrollment API Routes

FastAPI endpoints for speaker enrollment
Extracted from: main3.py lines 541-619

Endpoints:
- POST /enroll/upload - Upload voice sample for enrollment
- GET /enroll/speakers - List enrolled speakers

Maintains backward compatibility with original API
"""

import os
import tempfile
from typing import Dict, Any, Optional
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Depends

from .service import SpeakerService
from src.auth.permissions import require_admin


# Create router
router = APIRouter(prefix="/enroll", tags=["speaker"])

# Service instance (will be initialized by main app)
_service: Optional[SpeakerService] = None


def initialize_service(
    enrollment_dir: Optional[str] = None,
    match_threshold: float = 0.60,
    backend: str = "lite"
) -> SpeakerService:
    """
    Initialize speaker service
    
    Args:
        enrollment_dir: Directory for enrollment embeddings
        match_threshold: Similarity threshold for matching
        backend: Diarization backend ("lite" or "nemo")
    
    Returns:
        Initialized SpeakerService
    """
    global _service
    _service = SpeakerService(
        enrollment_dir=enrollment_dir,
        match_threshold=match_threshold,
        backend=backend
    )
    return _service


def get_service() -> SpeakerService:
    """Get speaker service instance"""
    if _service is None:
        raise RuntimeError("Speaker service not initialized")
    return _service


@router.post("/upload")
async def enroll_upload(
    audio: UploadFile = File(...),
    speaker: str = Form(...),
    session = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Upload enrollment audio from mobile app
    
    Extracts speaker embedding and saves for future recognition
    
    Args:
        audio: Audio file (any format, will be converted to 16kHz mono)
        speaker: Speaker name (e.g., "Pruitt", "Ericah")
    
    Returns:
        {
            "status": "success",
            "message": str,
            "speaker": str,
            "embedding_path": str,
            "auto_processed": bool
        }
    
    Raises:
        HTTPException: 400 if speaker name invalid, 500 if enrollment fails
    """
    service = get_service()
    
    # Validate speaker name
    speaker_clean = speaker.strip().lower()
    if not speaker_clean:
        raise HTTPException(status_code=400, detail="Speaker name required")
    
    temp_path = None
    
    try:
        # Save uploaded audio to temp file
        audio_data = await audio.read()
        
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)
        
        with open(temp_path, "wb") as f:
            f.write(audio_data)
        
        print(f"[ENROLL] Processing enrollment for '{speaker_clean}' ({len(audio_data)} bytes)")
        
        # Convert to 16kHz mono WAV if needed
        from ...utils.audio_utils import AudioConverter
        converter = AudioConverter()
        
        converted_path = temp_path.replace(".wav", "_16k.wav")
        converter.convert_to_wav(temp_path, converted_path, remove_input=False)
        
        # Generate enrollment embedding
        result = service.save_enrollment(
            speaker_name=speaker_clean,
            audio_path=converted_path
        )
        
        # Clean up temp files
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(converted_path):
            os.remove(converted_path)
        
        print(f"[ENROLL] ✅ Enrollment successful for '{speaker_clean}'")
        
        return {
            "status": "success",
            "message": f"Enrollment successful for '{speaker_clean}'",
            "speaker": speaker_clean,
            "embedding_path": result["embedding_path"],
            "auto_processed": True
        }
        
    except RuntimeError as e:
        print(f"[ENROLL] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        print(f"[ENROLL] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {e}")
        
    finally:
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.get("/speakers")
def list_enrolled_speakers(session = Depends(require_admin)) -> Dict[str, Any]:
    """
    List all enrolled speakers
    
    Returns:
        {
            "speakers": [str],
            "count": int
        }
    """
    service = get_service()
    enrolled = service.get_enrolled_speakers()
    
    return {
        "speakers": enrolled,
        "count": len(enrolled)
    }


@router.get("/stats")
def get_speaker_stats(session = Depends(require_admin)) -> Dict[str, Any]:
    """
    Get speaker service statistics
    
    Returns:
        Service stats including model status, enrolled speakers, etc.
    """
    service = get_service()
    return service.get_stats()

