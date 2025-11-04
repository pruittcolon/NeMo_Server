"""
Emotion analysis module to avoid circular imports.
"""

from typing import Any, Dict
import os
try:
    from transformers import pipeline  # type: ignore
except ImportError:  # pragma: no cover - executed when optional deps missing
    pipeline = None  # type: ignore

from config import ModelConfig

# Global emotion classifier
emotion_classifier = None

def initialize_emotion_classifier():
    """Initialize the emotion classifier model."""
    global emotion_classifier
    if emotion_classifier is None:
        if pipeline is None:
            print("[WARN] transformers is not installed; emotion analysis disabled.")
            return
        try:
            model_path = ModelConfig.EMOTION_MODEL_PATH
            print(f"[DEBUG] Checking emotion model at: {model_path}")
            print(f"[DEBUG] Path exists: {os.path.exists(model_path)}, is_dir: {os.path.isdir(model_path)}")
            if os.path.isdir(model_path):
                model_source = model_path
            elif ModelConfig.ALLOW_MODEL_DOWNLOAD:
                model_source = ModelConfig.EMOTION_MODEL
            else:
                print(
                    f"[WARN] Emotion analysis model not found at {model_path}. "
                    "Enable downloads (ALLOW_MODEL_DOWNLOAD=1) or provide a local cache."
                )
                return

            # Use CPU for emotion model to save GPU memory (it's lightweight)
            device = -1
            emotion_classifier = pipeline(
                "text-classification",
                model=model_source,
                tokenizer=model_source,
                return_all_scores=True,
                device=device,
            )
            print("[INIT] Emotion analysis model loaded successfully")
        except Exception as exc:
            print(f"[WARN] Failed to load emotion analysis model: {exc}")
            emotion_classifier = None

def analyze_emotion(text: str) -> Dict[str, Any]:
    """
    Analyze emotion in the given text using the Hugging Face emotion model.
    Returns emotion data including the dominant emotion and all emotion scores.
    """
    if not emotion_classifier or not text.strip():
        return {
            "dominant_emotion": "neutral",
            "confidence": 0.0,
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
        # Clean and truncate text for emotion analysis to prevent token overflow
        clean_text = text.strip()
        if len(clean_text) < 3:
            return analyze_emotion("")  # Return neutral for very short text
        
        # Truncate text to prevent token sequence length errors (max 512 tokens)
        max_chars = 2000  # Conservative limit to stay well under 512 tokens
        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars]
        
        # Get emotion predictions
        results = emotion_classifier(clean_text)
        
        # Extract emotions and scores
        emotions = {}
        dominant_emotion = "neutral"
        max_score = 0.0
        
        for result in results[0]:  # results is a list with one element containing all emotions
            emotion = result["label"]
            score = result["score"]
            emotions[emotion] = score
            
            if score > max_score:
                max_score = score
                dominant_emotion = emotion
        
        return {
            "dominant_emotion": dominant_emotion,
            "confidence": max_score,
            "emotions": emotions
        }
        
    except Exception as exc:
        print(f"[EMOTION] Error analyzing emotion: {exc}")
        # Return neutral emotion data instead of recursive call to prevent infinite loops
        return {
            "dominant_emotion": "neutral",
            "confidence": 0.0,
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
