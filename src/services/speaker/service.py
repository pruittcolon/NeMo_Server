"""
Speaker Diarization Service

CONSOLIDATES 3x duplicate speaker ID implementations from main3.py:
1. apply_diarization() - lines 238-348
2. Enrollment matching in /transcribe - lines 743-793  
3. K-means clustering logic

Single source of truth for:
- Speaker embedding generation (TitaNet)
- K-means clustering (2 speakers)
- Enrollment matching (cosine similarity)
- Speaker label mapping (Pruitt, Ericah, SPK_XX)

CPU-only operation (GPU reserved for Gemma)
"""

import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import numpy as np
from scipy.spatial.distance import cosine
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize

# Import our utilities
from src.utils.audio_utils import AudioConverter
from src.models.model_manager import SpeakerModelManager

# Import config from parent
import sys
parent_src = str(Path(__file__).parent.parent.parent.parent / "src")
if parent_src not in sys.path:
    sys.path.insert(0, parent_src)

try:
    import config
    ENROLL_MATCH_THRESHOLD = config.ENROLL_MATCH_THRESHOLD
    SECONDARY_CONFIDENCE_THRESHOLD = config.SECONDARY_CONFIDENCE_THRESHOLD
except ImportError:
    # Fallback defaults
    ENROLL_MATCH_THRESHOLD = 0.60
    SECONDARY_CONFIDENCE_THRESHOLD = 0.65


class SpeakerMapper:
    """
    Maps raw speaker IDs to friendly labels
    
    Assigns primary/secondary labels based on speaking duration
    Extracted from: main3.py lines 381-425
    """
    
    def __init__(
        self,
        segments: List[Dict[str, Any]],
        primary_label: str = "SPK_00",
        secondary_label: str = "SPK_01",
        secondary_threshold: float = SECONDARY_CONFIDENCE_THRESHOLD
    ):
        """
        Initialize speaker mapper
        
        Args:
            segments: List of segments with speaker labels
            primary_label: Label for primary speaker (most speaking time)
            secondary_label: Label for secondary speaker
            secondary_threshold: Confidence threshold for secondary speaker
        """
        self.primary_label = primary_label
        self.secondary_label = secondary_label
        self.secondary_threshold = secondary_threshold
        self.raw_to_friendly: Dict[str, str] = {}
        self.primary_id: Optional[str] = None
        self.secondary_id: Optional[str] = None
        self._build(segments)
    
    def _build(self, segments: List[Dict[str, Any]]) -> None:
        """Build speaker mapping based on durations"""
        if not segments:
            return
        
        # Calculate duration per speaker
        durations: Dict[str, float] = {}
        for segment in segments:
            speaker = segment.get("speaker")
            if not speaker:
                continue
            
            start = float(segment.get("start", 0.0) or 0.0)
            end = float(segment.get("end", 0.0) or 0.0)
            duration = max(0.0, end - start)
            
            # Fallback to text length if no duration
            if duration <= 0.0:
                duration = float(len((segment.get("text") or "")))
            
            durations[speaker] = durations.get(speaker, 0.0) + duration
        
        # Sort by duration (descending)
        ordered = sorted(durations.items(), key=lambda item: item[1], reverse=True)
        
        # Assign labels
        if ordered:
            self.primary_id = ordered[0][0]
            self.raw_to_friendly[self.primary_id] = self.primary_label
        
        if len(ordered) > 1:
            self.secondary_id = ordered[1][0]
            self.raw_to_friendly[self.secondary_id] = self.secondary_label
    
    def friendly_label(self, raw: str, confidence: Optional[float] = None) -> str:
        """
        Get friendly label for raw speaker ID
        
        Args:
            raw: Raw speaker ID (e.g., "SPK_00")
            confidence: Optional confidence score
        
        Returns:
            Friendly label (e.g., "Pruitt", "Ericah", "SPK_00")
        """
        raw = raw or "SPK"
        friendly = self.raw_to_friendly.get(raw, raw)
        
        # Add "(maybe)" suffix if secondary speaker with low confidence
        if (friendly == self.secondary_label and 
            confidence is not None and 
            confidence < self.secondary_threshold):
            return f"{friendly} (maybe)"
        
        return friendly


class SpeakerService:
    """
    Unified speaker identification service
    
    Consolidates all speaker diarization logic into single implementation
    """
    
    def __init__(
        self,
        enrollment_dir: Optional[str] = None,
        match_threshold: float = ENROLL_MATCH_THRESHOLD,
        backend: str = "lite"
    ):
        """
        Initialize speaker service
        
        Args:
            enrollment_dir: Directory containing enrollment embeddings
            match_threshold: Similarity threshold for enrollment matching
            backend: Diarization backend ("lite" or "nemo")
        """
        self.match_threshold = match_threshold
        self.backend = backend
        
        # Set enrollment directory
        if enrollment_dir is None:
            # Default: instance/enrollment/
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.enrollment_dir = project_root / "instance" / "enrollment"
        else:
            self.enrollment_dir = Path(enrollment_dir)
        
        # Initialize components
        self.audio_converter = AudioConverter()
        self.speaker_manager = SpeakerModelManager()
        
        # Cache for enrollment embeddings
        self._enrollment_cache: Dict[str, np.ndarray] = {}
        
        print(f"[SPEAKER] Service initialized (backend={backend}, threshold={match_threshold})")
    
    def load_model(self) -> None:
        """Load TitaNet speaker model (CPU-only)"""
        if not self.speaker_manager.is_loaded:
            print("[SPEAKER] Loading TitaNet speaker model...")
            self.speaker_manager.load()
            print("[SPEAKER] Speaker model loaded on CPU")
    
    def _extract_segment_embedding(
        self,
        audio_path: str,
        start: float,
        end: float
    ) -> Optional[np.ndarray]:
        """
        Extract speaker embedding for audio segment
        
        Uses TitaNet model to generate 192-dimensional embedding
        Extracted from: main3.py lines 262-281
        
        Args:
            audio_path: Path to audio file
            start: Start time in seconds
            end: End time in seconds
        
        Returns:
            192-dimensional embedding or None if extraction fails
        """
        # Ensure model is loaded
        if not self.speaker_manager.is_loaded:
            self.load_model()
        
        temp_path = None
        try:
            # Extract audio segment
            temp_path = self.audio_converter.convert_segment(
                input_path=audio_path,
                start_time=start,
                end_time=end
            )
            
            # Generate embedding with TitaNet
            model = self.speaker_manager.model
            embedding = model.get_embedding(temp_path).detach().cpu().numpy().reshape(-1)
            
            return embedding.astype(np.float32)
            
        except Exception as e:
            print(f"[SPEAKER] Warning: Failed to extract embedding for segment {start:.2f}-{end:.2f}: {e}")
            return None
            
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def _load_enrollment_embedding(self, speaker_name: str) -> Optional[np.ndarray]:
        """
        Load enrollment embedding from disk
        
        Args:
            speaker_name: Name of enrolled speaker (e.g., "pruitt")
        
        Returns:
            Embedding array or None if not found
        """
        # Check cache first
        if speaker_name in self._enrollment_cache:
            return self._enrollment_cache[speaker_name]
        
        # Load from disk
        embedding_path = self.enrollment_dir / f"{speaker_name.lower()}_embedding.npy"
        
        try:
            if embedding_path.exists():
                embedding = np.load(str(embedding_path)).reshape(-1).astype(np.float32)
                self._enrollment_cache[speaker_name] = embedding
                print(f"[SPEAKER] Loaded enrollment for '{speaker_name}' (norm: {np.linalg.norm(embedding):.6f})")
                return embedding
        except Exception as e:
            print(f"[SPEAKER] Warning: Could not load enrollment for '{speaker_name}': {e}")
        
        return None
    
    def _compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
        
        Returns:
            Similarity score (0-1, higher is more similar)
        """
        # Normalize embeddings
        emb1_norm = normalize(embedding1.reshape(1, -1))
        emb2_norm = normalize(embedding2.reshape(1, -1))
        
        # Compute cosine similarity (1 - cosine distance)
        if np.linalg.norm(emb1_norm) > 0 and np.linalg.norm(emb2_norm) > 0:
            similarity = float(1 - cosine(emb1_norm.reshape(-1), emb2_norm.reshape(-1)))
        else:
            similarity = 0.0
        
        return similarity
    
    def _cluster_speakers(self, embeddings: np.ndarray, n_clusters: int = 2) -> np.ndarray:
        """
        Cluster speaker embeddings using K-means
        
        Args:
            embeddings: Array of embeddings (N x 192)
            n_clusters: Number of speakers (default: 2)
        
        Returns:
            Cluster labels for each embedding
        """
        if embeddings.shape[0] < 2:
            # Single segment, no clustering needed
            return np.zeros((embeddings.shape[0],), dtype=np.int32)
        
        # Normalize for cosine distance
        embeddings_norm = normalize(embeddings)
        
        # K-means clustering
        k = min(n_clusters, embeddings_norm.shape[0])
        kmeans = KMeans(n_clusters=k, n_init=10, random_state=0)
        labels = kmeans.fit_predict(embeddings_norm)
        
        return labels.astype(np.int32)
    
    def diarize_segments(
        self,
        audio_path: str,
        segments: List[Dict[str, Any]],
        enrollment_speakers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform speaker diarization on transcribed segments
        
        CONSOLIDATES all speaker ID logic from main3.py
        
        Args:
            audio_path: Path to audio file
            segments: List of transcribed segments with start/end times
            enrollment_speakers: Optional list of enrolled speaker names to match
        
        Returns:
            Segments with speaker labels added
        """
        # Check backend
        if self.backend != 'lite':
            # For non-lite backend, just label as SPK
            return [{
                **seg,
                "speaker": "SPK",
                "speaker_confidence": None
            } for seg in segments]
        
        if not segments:
            return []
        
        print(f"[SPEAKER] Diarizing {len(segments)} segments from {audio_path}")
        
        # Extract embeddings for all segments
        embeddings = []
        for seg in segments:
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
            
            emb = self._extract_segment_embedding(audio_path, start, end)
            if emb is None:
                # Use zero vector if extraction fails
                emb = np.zeros((192,), dtype=np.float32)
            
            embeddings.append(emb.reshape(1, -1))
        
        # Stack embeddings
        X = np.vstack(embeddings) if embeddings else np.zeros((len(segments), 192), dtype=np.float32)
        
        # Cluster speakers
        cluster_labels = self._cluster_speakers(X, n_clusters=2)
        
        # Load enrollment embeddings (check all enrolled speakers)
        enrollment_embeddings = {}
        if enrollment_speakers is None:
            enrollment_speakers = self.get_enrolled_speakers()
        
        for speaker_name in enrollment_speakers:
            emb = self._load_enrollment_embedding(speaker_name)
            if emb is not None:
                enrollment_embeddings[speaker_name] = emb
        
        # Match segments against enrollments
        labeled_segments = []
        
        for i, seg in enumerate(segments):
            emb = X[i]
            cluster_id = int(cluster_labels[i])
            
            # Default label and confidence
            speaker_label = f"SPK_{cluster_id:02d}"
            confidence = None
            
            # Try enrollment matching
            best_match = None
            best_similarity = 0.0
            
            for speaker_name, enroll_emb in enrollment_embeddings.items():
                similarity = self._compute_similarity(emb, enroll_emb)
                
                if i < 5:  # Log first 5 segments
                    print(f"[SPEAKER] Segment {i}: similarity to '{speaker_name}' = {similarity:.3f} "
                          f"(threshold={self.match_threshold:.3f})")
                
                if similarity >= self.match_threshold and similarity > best_similarity:
                    best_match = speaker_name
                    best_similarity = similarity
            
            # Use enrollment match if found
            if best_match:
                speaker_label = speaker_name.capitalize()  # e.g., "Pruitt"
                confidence = best_similarity
                
                if i < 5:
                    print(f"[SPEAKER] ✅ Segment {i}: Matched to '{speaker_label}' (sim={confidence:.3f})")
            
            # Add speaker info to segment
            labeled_segments.append({
                **seg,
                "speaker": speaker_label,
                "speaker_raw": speaker_label,
                "speaker_confidence": confidence
            })
        
        print(f"[SPEAKER] Diarization complete: {len(labeled_segments)} segments labeled")
        return labeled_segments
    
    def save_enrollment(
        self,
        speaker_name: str,
        audio_path: str,
        start: float = 0.0,
        end: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create speaker enrollment from audio
        
        Args:
            speaker_name: Name of speaker to enroll
            audio_path: Path to enrollment audio
            start: Start time (default: 0.0)
            end: End time (default: full audio)
        
        Returns:
            Enrollment result with path and embedding info
        """
        # Ensure model is loaded
        if not self.speaker_manager.is_loaded:
            self.load_model()
        
        # Determine end time if not provided
        if end is None:
            import soundfile as sf
            info = sf.info(audio_path)
            end = info.duration
        
        # Extract embedding
        print(f"[SPEAKER] Generating enrollment for '{speaker_name}' from {audio_path}")
        embedding = self._extract_segment_embedding(audio_path, start, end)
        
        if embedding is None:
            raise RuntimeError("Failed to extract embedding for enrollment")
        
        # Save to enrollment directory
        os.makedirs(self.enrollment_dir, exist_ok=True)
        
        embedding_path = self.enrollment_dir / f"{speaker_name.lower()}_embedding.npy"
        np.save(str(embedding_path), embedding)
        
        # Update cache
        self._enrollment_cache[speaker_name] = embedding
        
        print(f"[SPEAKER] Enrollment saved: {embedding_path} (shape={embedding.shape}, norm={np.linalg.norm(embedding):.6f})")
        
        return {
            "speaker": speaker_name,
            "embedding_path": str(embedding_path),
            "embedding_shape": embedding.shape,
            "embedding_norm": float(np.linalg.norm(embedding))
        }
    
    def get_enrolled_speakers(self) -> List[str]:
        """Get list of enrolled speakers"""
        enrolled = []
        
        if self.enrollment_dir.exists():
            for file in self.enrollment_dir.glob("*_embedding.npy"):
                speaker_name = file.stem.replace("_embedding", "")
                enrolled.append(speaker_name)
        
        return enrolled
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "model_loaded": self.speaker_manager.is_loaded,
            "model_device": self.speaker_manager.device,
            "backend": self.backend,
            "match_threshold": self.match_threshold,
            "enrolled_speakers": self.get_enrolled_speakers(),
            "enrollment_dir": str(self.enrollment_dir)
        }


