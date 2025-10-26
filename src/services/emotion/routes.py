"""
Emotion Analysis API Routes

FastAPI endpoints for emotion analysis
Extracted from main3.py (emotion analysis endpoints)

Endpoints:
- POST /analyze/emotion - Analyze emotion in text
- POST /analyze/emotion_batch - Analyze emotions for multiple texts
- POST /analyze/prepare_emotion_analysis - Prepare emotion context
- POST /analyze/emotion_context - Get emotion context for segments

Maintains backward compatibility with original API
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import EmotionService


# Create router
router = APIRouter(prefix="/emotion", tags=["emotion"])

# Service instance (will be initialized by main app)
_service: Optional[EmotionService] = None


def initialize_service(device: str = "cpu") -> EmotionService:
    """
    Initialize emotion service
    
    Args:
        device: Device for emotion model (default: "cpu")
    
    Returns:
        Initialized EmotionService
    """
    global _service
    _service = EmotionService(device=device)
    return _service


def get_service() -> EmotionService:
    """Get emotion service instance"""
    if _service is None:
        raise RuntimeError("Emotion service not initialized")
    return _service


# -------------------------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------------------------

class EmotionAnalyzeRequest(BaseModel):
    """Request model for single emotion analysis"""
    text: str


class EmotionBatchRequest(BaseModel):
    """Request model for batch emotion analysis"""
    texts: List[str]


class EmotionSegmentsRequest(BaseModel):
    """Request model for segment emotion analysis"""
    segments: List[Dict[str, Any]]


class EmotionContextRequest(BaseModel):
    """Request model for emotion context preparation"""
    segments: List[Dict[str, Any]]
    window_size: int = 3


# -------------------------------------------------------------------------
# Emotion Endpoints
# -------------------------------------------------------------------------

@router.post("/emotion")
def analyze_emotion_endpoint(payload: EmotionAnalyzeRequest) -> Dict[str, Any]:
    """
    Analyze emotion in text
    
    Args:
        payload: Request with text to analyze
    
    Returns:
        {
            "dominant_emotion": str,
            "confidence": float,
            "emotions": {
                "anger": float,
                "disgust": float,
                "fear": float,
                "joy": float,
                "neutral": float,
                "sadness": float,
                "surprise": float
            }
        }
    """
    service = get_service()
    
    try:
        result = service.analyze(payload.text)
        return result
    except Exception as e:
        print(f"[EMOTION API] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emotion_batch")
def analyze_emotion_batch(payload: EmotionBatchRequest) -> Dict[str, Any]:
    """
    Analyze emotions for multiple texts
    
    Args:
        payload: Request with list of texts
    
    Returns:
        {
            "results": [
                {
                    "dominant_emotion": str,
                    "confidence": float,
                    "emotions": {...}
                },
                ...
            ]
        }
    """
    service = get_service()
    
    try:
        results = service.analyze_batch(payload.texts)
        return {"results": results}
    except Exception as e:
        print(f"[EMOTION API] Batch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emotion_segments")
def analyze_emotion_segments(payload: EmotionSegmentsRequest) -> Dict[str, Any]:
    """
    Analyze emotions for transcription segments
    
    Args:
        payload: Request with segments
    
    Returns:
        {
            "segments": [
                {
                    ...original segment fields,
                    "emotion": str,
                    "emotion_confidence": float,
                    "emotions": {...}
                },
                ...
            ]
        }
    """
    service = get_service()
    
    try:
        enriched_segments = service.analyze_segments(payload.segments)
        return {"segments": enriched_segments}
    except Exception as e:
        print(f"[EMOTION API] Segments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prepare_emotion_analysis")
def prepare_emotion_analysis(payload: EmotionContextRequest) -> List[Dict[str, Any]]:
    """
    Prepare emotion context for analysis
    
    Groups segments with surrounding context for better understanding
    
    Args:
        payload: Request with segments and window size
    
    Returns:
        List of emotion context items with:
        - segment: original segment
        - context_segments: surrounding segments
        - context_text: combined context text
        - segment_emotion: emotion for this segment
        - context_emotion: emotion for full context
    """
    service = get_service()
    
    try:
        context_items = service.prepare_emotion_context(
            segments=payload.segments,
            window_size=payload.window_size
        )
        return context_items
    except Exception as e:
        print(f"[EMOTION API] Context preparation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emotion_context")
def emotion_context_endpoint(payload: EmotionContextRequest) -> List[Dict[str, Any]]:
    """
    Get emotion context for segments (alias for prepare_emotion_analysis)
    
    Args:
        payload: Request with segments and window size
    
    Returns:
        List of emotion context items
    """
    return prepare_emotion_analysis(payload)


@router.post("/emotion_summary")
def get_emotion_summary(payload: EmotionSegmentsRequest) -> Dict[str, Any]:
    """
    Get overall emotion summary for segments
    
    Args:
        payload: Request with segments
    
    Returns:
        {
            "total_segments": int,
            "dominant_emotion": str,
            "emotion_counts": {...},
            "emotion_percentages": {...},
            "average_confidence": float
        }
    """
    service = get_service()
    
    try:
        summary = service.get_emotion_summary(payload.segments)
        return summary
    except Exception as e:
        print(f"[EMOTION API] Summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emotion/stats")
def get_emotion_stats() -> Dict[str, Any]:
    """
    Get emotion service statistics
    
    Returns:
        Service stats including model status
    """
    service = get_service()
    return service.get_stats()


@router.get("/emotion/health")
def check_emotion_health() -> Dict[str, bool]:
    """
    Check emotion service health
    
    Returns:
        Health status
    """
    service = get_service()
    return {
        "available": service.is_available(),
        "classifier_loaded": service.classifier is not None
    }


