"""
Emotion Analysis Service

Thin wrapper around existing emotion_analyzer.py
As per user request: "I WANT emotion_analyzer.py to remain AS IS"

This service provides:
- Text emotion classification (DistilRoBERTa)
- Batch emotion analysis
- Emotion context preparation

All heavy lifting is done by the existing emotion_analyzer module
This wrapper ensures CPU-only operation (GPU reserved for Gemma)
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import config from parent
parent_src = str(Path(__file__).parent.parent.parent.parent / "src")
if parent_src not in sys.path:
    sys.path.insert(0, parent_src)

try:
    # Import existing emotion_analyzer unchanged
    from emotion_analyzer import analyze_emotion, initialize_emotion_classifier
    print("[EMOTION] Successfully imported emotion_analyzer")
except ImportError as e:
    print(f"[EMOTION] ERROR: Failed to import emotion_analyzer: {e}")
    print("[EMOTION] Ensure src/emotion_analyzer.py exists and is importable")
    analyze_emotion = None
    initialize_emotion_classifier = None


class EmotionService:
    """
    Emotion analysis service wrapper
    
    Delegates all operations to existing emotion_analyzer module
    Ensures CPU-only for DistilRoBERTa (GPU reserved for Gemma)
    """
    
    def __init__(self, device: str = "cpu"):
        """
        Initialize emotion service
        
        Args:
            device: Device for emotion model (default: "cpu")
        """
        if analyze_emotion is None or initialize_emotion_classifier is None:
            raise RuntimeError("emotion_analyzer module not available")
        
        self.device = device
        self.classifier = None
        
        # Initialize classifier on CPU
        try:
            initialize_emotion_classifier()  # No arguments needed
            # Get the global classifier
            from emotion_analyzer import emotion_classifier
            self.classifier = emotion_classifier
            print(f"[EMOTION] Service initialized (device={self.device}, classifier={self.classifier is not None})")
        except Exception as e:
            print(f"[EMOTION] WARNING: Failed to initialize classifier: {e}")
            print("[EMOTION] Continuing without emotion analysis")
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analyze emotion in text
        
        Args:
            text: Text to analyze
        
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
        if self.classifier is None:
            # Return neutral if classifier not available
            return {
                "dominant_emotion": "neutral",
                "confidence": 1.0,
                "emotions": {
                    "anger": 0.0,
                    "disgust": 0.0,
                    "fear": 0.0,
                    "joy": 0.0,
                    "neutral": 1.0,
                    "sadness": 0.0,
                    "surprise": 0.0
                }
            }
        
        try:
            return analyze_emotion(text)
        except Exception as e:
            print(f"[EMOTION] Error analyzing text: {e}")
            # Return neutral on error
            return {
                "dominant_emotion": "neutral",
                "confidence": 0.0,
                "emotions": {}
            }
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze emotions for multiple texts
        
        Args:
            texts: List of texts to analyze
        
        Returns:
            List of emotion analysis results
        """
        results = []
        for text in texts:
            result = self.analyze(text)
            results.append(result)
        return results
    
    def analyze_segments(
        self,
        segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze emotions for transcription segments
        
        Args:
            segments: List of segments with "text" field
        
        Returns:
            Segments with emotion data added
        """
        enriched_segments = []
        
        for seg in segments:
            text = (seg.get("text") or "").strip()
            
            # Analyze emotion
            emotion_data = self.analyze(text)
            
            # Add emotion data to segment
            enriched_segment = {
                **seg,
                "emotion": emotion_data["dominant_emotion"],
                "emotion_confidence": emotion_data["confidence"],
                "emotions": emotion_data["emotions"]
            }
            
            enriched_segments.append(enriched_segment)
        
        return enriched_segments
    
    def prepare_emotion_context(
        self,
        segments: List[Dict[str, Any]],
        window_size: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Prepare emotion context for analysis
        
        Groups segments with surrounding context for better emotion understanding
        
        Args:
            segments: List of segments
            window_size: Number of segments before/after for context
        
        Returns:
            List of emotion context items
        """
        context_items = []
        
        for i, seg in enumerate(segments):
            # Get context window
            start_idx = max(0, i - window_size)
            end_idx = min(len(segments), i + window_size + 1)
            
            context_segments = segments[start_idx:end_idx]
            
            # Build context text
            context_text = " ".join(
                (s.get("text") or "").strip()
                for s in context_segments
                if s.get("text")
            )
            
            # Analyze context
            context_emotion = self.analyze(context_text)
            
            context_items.append({
                "index": i,
                "segment": seg,
                "context_segments": context_segments,
                "context_text": context_text,
                "segment_emotion": {
                    "dominant": seg.get("emotion", "neutral"),
                    "confidence": seg.get("emotion_confidence", 0.0),
                    "all_emotions": seg.get("emotions", {})
                },
                "context_emotion": context_emotion
            })
        
        return context_items
    
    def get_emotion_summary(
        self,
        segments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get overall emotion summary for segments
        
        Args:
            segments: List of segments with emotion data
        
        Returns:
            Summary statistics for emotions
        """
        # Count emotions
        emotion_counts: Dict[str, int] = {}
        total_confidence = 0.0
        
        for seg in segments:
            emotion = seg.get("emotion", "neutral")
            confidence = seg.get("emotion_confidence", 0.0)
            
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            total_confidence += confidence
        
        # Calculate percentages
        total_segments = len(segments)
        emotion_percentages = {
            emotion: (count / total_segments) * 100
            for emotion, count in emotion_counts.items()
        }
        
        # Find dominant emotion
        dominant_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0] if emotion_counts else "neutral"
        
        return {
            "total_segments": total_segments,
            "dominant_emotion": dominant_emotion,
            "emotion_counts": emotion_counts,
            "emotion_percentages": emotion_percentages,
            "average_confidence": total_confidence / total_segments if total_segments > 0 else 0.0
        }
    
    def is_available(self) -> bool:
        """Check if emotion classifier is available"""
        return self.classifier is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "classifier_loaded": self.classifier is not None,
            "device": self.device,
            "available": self.is_available()
        }


