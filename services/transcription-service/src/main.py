"""
Transcription Service with GPU Pause/Resume
Owns GPU by default, pauses for Gemma requests
"""

import os
import logging
import asyncio
import uuid
import math
import contextlib
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List, Tuple
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import httpx
import numpy as np
import soundfile as sf
import io
import tempfile
import torch
import nemo.collections.asr as nemo_asr
from nemo.collections.asr.models import EncDecSpeakerLabelModel, EncDecClassificationModel
import sys

from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score

from .pause_manager import get_pause_manager
from .audio_metrics import extract_audio_metrics
from .parakeet_pipeline import ParakeetPipeline, ParakeetTranscription, ParakeetSegment

# Add shared modules to path
sys.path.insert(0, '/app')

# Import replay protector at module level (not in middleware dispatch for efficiency)
try:
    from shared.security.service_auth import get_replay_protector
except ImportError:
    get_replay_protector = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic models
class TranscriptionResponse(BaseModel):
    """Transcription response"""
    job_id: str
    status: str
    text: str = ""
    segments: list = []
    message: str = ""

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
EMOTION_SERVICE_URL = os.getenv("EMOTION_SERVICE_URL", "http://emotion-service:8005")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:8004")
NEMO_MODEL_PATH = os.getenv("NEMO_MODEL_PATH", "")  # Local .nemo file path
NEMO_MODEL_NAME = os.getenv("NEMO_MODEL_NAME", "nvidia/parakeet-rnnt-0.6b")  # Use smaller 0.6B model (fallback)
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")
JWT_ONLY = os.getenv("JWT_ONLY", "false").lower() in {"1", "true", "yes"}

TRANSCRIBE_USE_VAD = os.getenv("TRANSCRIBE_USE_VAD", "true").lower() == "true"
VAD_MODEL_NAME = os.getenv("VAD_MODEL_NAME", "vad_multilingual_marblenet")
VAD_SPEECH_THRESHOLD = float(os.getenv("VAD_SPEECH_THRESHOLD", "0.5"))
VAD_ONSET = float(os.getenv("VAD_ONSET", "0.6"))      # start speech threshold (higher)
VAD_OFFSET = float(os.getenv("VAD_OFFSET", "0.4"))    # stop speech threshold (lower)
VAD_SMOOTHING_SEC = float(os.getenv("VAD_SMOOTHING_SEC", "0.15"))
VAD_PAD_ONSET_SEC = float(os.getenv("VAD_PAD_ONSET_SEC", "0.05"))
VAD_PAD_OFFSET_SEC = float(os.getenv("VAD_PAD_OFFSET_SEC", "0.1"))
MERGE_GAP_SEC = float(os.getenv("VAD_MERGE_GAP_SEC", "0.3"))
MIN_SPEECH_SEC = float(os.getenv("VAD_MIN_SPEECH_SEC", "0.5"))
MAX_SEGMENT_SEC = float(os.getenv("VAD_MAX_SEGMENT_SEC", "30.0"))
SEGMENT_OVERLAP_SEC = float(os.getenv("VAD_SEGMENT_OVERLAP_SEC", "0.5"))
DIARIZATION_SPK_MIN = int(os.getenv("DIARIZATION_SPK_MIN", "1"))
DIARIZATION_SPK_MAX = int(os.getenv("DIARIZATION_SPK_MAX", "3"))
ASR_BATCH_SIZE = int(os.getenv("ASR_BATCH_SIZE", "2"))
CPU_ONLY_VAD_EMBEDS = os.getenv("CPU_ONLY_VAD_EMBEDS", "true").lower() == "true"
DEFAULT_SPEAKER_EMBED_DIM = int(os.getenv("SPEAKER_EMBED_DIM_DEFAULT", "192"))

TRANSCRIBE_STRATEGY = os.getenv("TRANSCRIBE_STRATEGY", "rnnt").lower()
PARAKEET_MODEL_ID = os.getenv("PARAKEET_MODEL_ID", "nvidia/parakeet-tdt-0.6b-v2")
PARAKEET_CHUNK_DURATION = int(os.getenv("PARAKEET_CHUNK_DURATION", "300"))
ENABLE_PYANNOTE = os.getenv("ENABLE_PYANNOTE", "true").lower() == "true"
PYANNOTE_DEVICE = os.getenv("PYANNOTE_DEVICE", "cpu")
_max_speakers_raw = os.getenv("PYANNOTE_MAX_SPEAKERS")
try:
    PYANNOTE_MAX_SPEAKERS = int(_max_speakers_raw) if _max_speakers_raw else None
except ValueError:
    logger.warning("Invalid PYANNOTE_MAX_SPEAKERS value '%s'; defaulting to auto", _max_speakers_raw)
    PYANNOTE_MAX_SPEAKERS = None

# Audio buffering for diarization
# Key: stream_id, Value: {'audio_chunks': [], 'sample_rate': int, 'last_update': float}
audio_buffers: Dict[str, Dict[str, Any]] = {}
DIARIZATION_BUFFER_DURATION = 30  # Run diarization every 30 seconds of accumulated audio
MAX_BUFFER_AGE = 300  # Clear buffers after 5 minutes of inactivity

# Global transcription models
asr_model = None
speaker_model = None  # TitaNet for speaker embeddings
transcription_model_loaded = False
vad_model = None
service_auth = None
asr_device = "cpu"
speaker_device = "cpu"
vad_device = "cpu"
vad_window_stride = 0.01
speaker_embedding_dim = 0
parakeet_pipeline: Optional[ParakeetPipeline] = None


def _resample_audio(audio: np.ndarray, input_sr: int, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    """Resample audio to target sample rate (mono)."""
    if input_sr == target_sr:
        return audio.astype(np.float32), input_sr
    import librosa
    resampled = librosa.resample(audio.astype(np.float32), orig_sr=input_sr, target_sr=target_sr)
    return resampled.astype(np.float32), target_sr


def _split_long_segment(start: float, end: float, max_duration: float, overlap: float) -> List[Tuple[float, float]]:
    """Split long segments into smaller windows with optional overlap."""
    duration = end - start
    if duration <= max_duration or max_duration <= 0:
        return [(start, end)]
    segments = []
    cursor = start
    while cursor < end:
        seg_end = min(cursor + max_duration, end)
        segments.append((cursor, seg_end))
        if seg_end >= end:
            break
        cursor = seg_end - overlap
        if cursor < start:
            cursor = start
    return segments


def _merge_close_segments(segments: List[Tuple[float, float]], gap: float, min_duration: float) -> List[Tuple[float, float]]:
    """Merge segments separated by short gaps and drop very short speech regions."""
    if not segments:
        return []
    merged: List[List[float]] = [[segments[0][0], segments[0][1]]]
    for start, end in segments[1:]:
        if start - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    filtered = [(max(0.0, s), max(0.0, e)) for s, e in merged if (e - s) >= min_duration]
    return filtered


def run_vad_segments(audio: np.ndarray, sample_rate: int) -> List[Tuple[float, float]]:
    """Run NeMo VAD with smoothing, hysteresis, padding, and post-processing."""
    global vad_window_stride
    duration = len(audio) / sample_rate
    if not TRANSCRIBE_USE_VAD or vad_model is None:
        return [(0.0, duration)]

    signal = torch.tensor(audio, dtype=torch.float32, device=vad_device).unsqueeze(0)
    length = torch.tensor([signal.shape[1]], dtype=torch.int64, device=vad_device)

    with torch.no_grad():
        processed_signal, processed_length = vad_model.preprocessor(audio_signal=signal, length=length)
        logits, _ = vad_model.encoder(audio_signal=processed_signal, length=processed_length)
        probs = torch.softmax(vad_model.decoder(logits=logits), dim=-1)
        speech_probs = probs.squeeze(0)[:, 1].cpu().numpy()

    try:
        vad_window_stride = float(vad_model.cfg.preprocessor.params.window_stride)
    except Exception:
        vad_window_stride = 0.01

    # Smoothing (moving average)
    smoothing_frames = max(1, int(max(VAD_SMOOTHING_SEC, vad_window_stride) / vad_window_stride))
    if smoothing_frames % 2 == 0:
        smoothing_frames += 1
    if smoothing_frames > 1:
        kernel = np.ones(smoothing_frames, dtype=np.float32) / smoothing_frames
        speech_probs = np.convolve(speech_probs, kernel, mode="same")

    segments: List[Tuple[float, float]] = []
    active = False
    start_time = 0.0

    for idx, prob in enumerate(speech_probs):
        t = idx * vad_window_stride
        if not active and prob >= VAD_ONSET:
            active = True
            start_time = t
        elif active and prob <= VAD_OFFSET:
            end_time = t
            start = max(0.0, start_time - VAD_PAD_ONSET_SEC)
            end = min(duration, end_time + VAD_PAD_OFFSET_SEC)
            if (end - start) >= MIN_SPEECH_SEC:
                segments.append((start, end))
            active = False

    if active:
        end_time = len(speech_probs) * vad_window_stride
        start = max(0.0, start_time - VAD_PAD_ONSET_SEC)
        end = min(duration, end_time + VAD_PAD_OFFSET_SEC)
        if (end - start) >= MIN_SPEECH_SEC:
            segments.append((start, end))

    merged_segments = _merge_close_segments(segments, MERGE_GAP_SEC, MIN_SPEECH_SEC)

    final_segments: List[Tuple[float, float]] = []
    for seg_start, seg_end in merged_segments:
        final_segments.extend(_split_long_segment(seg_start, seg_end, MAX_SEGMENT_SEC, SEGMENT_OVERLAP_SEC))

    bounded_segments = [
        (max(0.0, seg_start), min(seg_end, duration))
        for seg_start, seg_end in final_segments
        if seg_start < duration and seg_end > seg_start and (seg_end - seg_start) >= 0.1
    ]

    if not bounded_segments:
        return [(0.0, duration)]
    logger.info(
        "[VAD] segments=%d total_speech=%.2fs (duration=%.2fs)",
        len(bounded_segments),
        sum(e - s for s, e in bounded_segments),
        duration,
    )
    return bounded_segments


def extract_speaker_embeddings(audio: np.ndarray, sample_rate: int, segments: List[Tuple[float, float]]) -> List[np.ndarray]:
    """Compute speaker embeddings for each speech segment."""
    global speaker_embedding_dim
    if speaker_model is None or not segments:
        return []

    embeddings: List[np.ndarray] = []
    min_samples = int(sample_rate * 0.1)  # Minimum 100ms
    
    for start, end in segments:
        start_idx = max(0, int(start * sample_rate))
        end_idx = min(len(audio), int(end * sample_rate))
        segment_audio = audio[start_idx:end_idx]
        
        # Handle too-short or empty segments
        if segment_audio.size == 0 or len(segment_audio) < min_samples:
            if embeddings:
                # Use last valid embedding
                logger.warning(f"Segment too short ({len(segment_audio)} samples), reusing previous embedding")
                embeddings.append(embeddings[-1].copy())
            else:
                # First segment is bad - create zero vector
                dim = speaker_embedding_dim or DEFAULT_SPEAKER_EMBED_DIM
                logger.warning(f"First segment too short, using zero vector")
                embeddings.append(np.zeros(dim, dtype=np.float32))
            continue

        try:
            tensor = torch.tensor(segment_audio, dtype=torch.float32, device=speaker_device).unsqueeze(0)
            length = torch.tensor([tensor.shape[1]], dtype=torch.int64, device=speaker_device)

            with torch.no_grad():
                embedding = speaker_model.get_embedding(audio_signal=tensor, length=length)
            vec = embedding.squeeze(0).cpu().numpy()
            speaker_embedding_dim = vec.shape[0]
            embeddings.append(vec)
        except Exception as e:
            logger.warning(f"Failed to extract embedding for segment [{start:.2f}, {end:.2f}]: {e}")
            if embeddings:
                embeddings.append(embeddings[-1].copy())
            else:
                dim = speaker_embedding_dim or DEFAULT_SPEAKER_EMBED_DIM
                embeddings.append(np.zeros(dim, dtype=np.float32))

    return embeddings


def cluster_speakers(embeddings: List[np.ndarray]) -> List[int]:
    """Cluster speaker embeddings using agglomerative clustering with cosine distance."""
    n = len(embeddings)
    if n == 0:
        return []
    if n == 1:
        return [0]

    X = np.stack(embeddings)
    
    # Check for all-zero or invalid embeddings
    norms = np.linalg.norm(X, axis=1)
    if np.all(norms < 1e-6):
        logger.warning("[DIARIZATION] All embeddings are zero - using single speaker")
        return [0] * n
    
    # Filter out zero embeddings for clustering
    valid_mask = norms >= 1e-6
    valid_count = np.sum(valid_mask)
    
    if valid_count < 2:
        logger.warning(f"[DIARIZATION] Only {valid_count} valid embeddings - using single speaker")
        return [0] * n
    
    # Normalize valid embeddings
    X_valid = X[valid_mask]
    norms_valid = norms[valid_mask, np.newaxis]
    X_norm = X_valid / (norms_valid + 1e-8)
    
    # Clustering on valid embeddings only
    best_labels_valid = np.zeros(valid_count, dtype=int)
    best_score = 0.0  # Neutral baseline instead of -1.0
    
    min_k = max(1, DIARIZATION_SPK_MIN)
    max_k = min(DIARIZATION_SPK_MAX, valid_count)
    
    for k in range(min_k, max_k + 1):
        if k == 1:
            labels_valid = np.zeros(valid_count, dtype=int)
            score = 0.0  # Neutral baseline
        else:
            try:
                clustering = AgglomerativeClustering(n_clusters=k, affinity="cosine", linkage="average")
                labels_valid = clustering.fit_predict(X_norm)
                
                # Check if clustering actually created k clusters
                unique_labels = np.unique(labels_valid)
                if len(unique_labels) >= 2:
                    score = silhouette_score(X_norm, labels_valid, metric="cosine")
                else:
                    score = -1.0
            except Exception as e:
                logger.warning(f"[DIARIZATION] Clustering k={k} failed: {e}")
                labels_valid = np.zeros(valid_count, dtype=int)
                score = -1.0
        
        if score > best_score:
            best_score = score
            best_labels_valid = labels_valid.copy()
    
    # Map back to all embeddings
    labels = np.zeros(n, dtype=int)
    labels[valid_mask] = best_labels_valid
    # Invalid embeddings get speaker 0
    
    logger.info(
        f"[DIARIZATION] Clustered {valid_count}/{n} valid embeddings into "
        f"{len(np.unique(best_labels_valid))} speakers (score={best_score:.3f})"
    )
    return labels.tolist()


def transcribe_segments_with_asr(segment_paths: List[str], batch_size: int = 1):
    """Run ASR on list of audio segment paths and return texts."""
    if not segment_paths:
        return []
    outputs = asr_model.transcribe(segment_paths, batch_size=batch_size, timestamps=False, return_hypotheses=True)
    texts: List[str] = []
    for item in outputs:
        if isinstance(item, str):
            texts.append(item.strip())
        elif isinstance(item, dict):
            texts.append(item.get("text", "").strip())
        elif hasattr(item, "text"):
            texts.append(getattr(item, "text", "").strip())
        else:
            texts.append("")
    return texts


def merge_adjacent_segments(segments: List[Dict[str, Any]], gap_threshold: float) -> List[Dict[str, Any]]:
    """Merge consecutive segments belonging to the same speaker within a small gap."""
    if not segments:
        return []
    merged: List[Dict[str, Any]] = [segments[0].copy()]
    for seg in segments[1:]:
        last = merged[-1]
        if (
            seg["speaker"] == last["speaker"]
            and seg["start_time"] - last["end_time"] <= gap_threshold
        ):
            last["end_time"] = max(last["end_time"], seg["end_time"])
            last["text"] = (last["text"] + " " + seg["text"]).strip()
            last["speaker_confidence"] = min(
                last.get("speaker_confidence", 1.0),
                seg.get("speaker_confidence", 1.0),
            )
        else:
            merged.append(seg.copy())
    return merged


async def _transcribe_with_parakeet(
    audio_data: np.ndarray,
    sample_rate: int,
    audio_duration: float,
    job_id: str,
    stream_id: Optional[str],
) -> TranscriptionResponse:
    """Handle transcription using the Parakeet pipeline."""
    global parakeet_pipeline

    if parakeet_pipeline is None:
        raise HTTPException(status_code=503, detail="Parakeet pipeline not initialised")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        sf.write(tmp_file.name, audio_data, sample_rate)
        tmp_path = tmp_file.name

    try:
        result: ParakeetTranscription = await asyncio.to_thread(parakeet_pipeline.transcribe_file, tmp_path)
    finally:
        with contextlib.suppress(Exception):
            os.unlink(tmp_path)

    segments: List[Dict[str, Any]] = []
    for seg in result.segments:
        speaker_label = seg.speaker or "speaker_0"
        if not speaker_label.startswith("speaker_"):
            speaker_label = f"speaker_{speaker_label}"
        segments.append({
            "text": seg.text.strip(),
            "speaker": speaker_label,
            "start_time": float(seg.start),
            "end_time": float(seg.end),
            "speaker_confidence": 0.9 if seg.speaker else 0.5,
        })

    if not segments:
        logger.warning("[PARAKEET] No segments returned; creating fallback segment")
        segments = [{
            "text": result.text or "",
            "speaker": "speaker_0",
            "start_time": 0.0,
            "end_time": audio_duration,
            "speaker_confidence": 0.5,
        }]

    segments = merge_adjacent_segments(sorted(segments, key=lambda s: s["start_time"]), MERGE_GAP_SEC)
    enriched_segments = await enrich_segments_with_metadata(segments, audio_data, sample_rate)
    full_text = result.text.strip() if result.text else " ".join(seg["text"] for seg in enriched_segments).strip()

    asyncio.create_task(
        index_transcript_in_rag(
            job_id=job_id,
            session_id=stream_id or "default",
            full_text=full_text,
            audio_duration=audio_duration,
            segments=enriched_segments,
        )
    )
    asyncio.create_task(
        create_memory_from_transcript(
            job_id=job_id,
            full_text=full_text,
            segments=enriched_segments,
        )
    )

    return TranscriptionResponse(
        job_id=job_id,
        status="complete",
        text=full_text,
        segments=enriched_segments,
        message="Success",
    )


def load_nemo_models():
    """Load transcription resources on startup."""
    global asr_model, speaker_model, vad_model, transcription_model_loaded
    global asr_device, speaker_device, vad_device, speaker_embedding_dim, vad_window_stride
    global parakeet_pipeline

    try:
        if TRANSCRIBE_STRATEGY == "parakeet":
            logger.info("Initialising Parakeet transcription strategy")
            parakeet_pipeline = ParakeetPipeline(
                model_id=PARAKEET_MODEL_ID,
                chunk_duration=PARAKEET_CHUNK_DURATION,
                enable_diarization=ENABLE_PYANNOTE,
                diarization_device=PYANNOTE_DEVICE,
                diarization_num_speakers=PYANNOTE_MAX_SPEAKERS,
            )
            transcription_model_loaded = True
            logger.info("Parakeet pipeline ready")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        asr_device = device

        # Load ASR model from local .nemo file if path provided, otherwise download from HuggingFace
        if NEMO_MODEL_PATH and os.path.exists(NEMO_MODEL_PATH):
            logger.info("Loading NeMo ASR model from local file: %s on %s...", NEMO_MODEL_PATH, device)
            asr_model = nemo_asr.models.ASRModel.restore_from(NEMO_MODEL_PATH, map_location=device)
        else:
            logger.info("Loading NeMo ASR model '%s' on %s...", NEMO_MODEL_NAME, device)
            asr_model = nemo_asr.models.ASRModel.from_pretrained(NEMO_MODEL_NAME)
            asr_model = asr_model.to(device)

        asr_model.eval()
        logger.info("✅ NeMo ASR model loaded successfully on %s!", device)

        # Load TitaNet speaker embedding model (for simple K-means diarization)
        try:
            speaker_target_device = "cpu" if CPU_ONLY_VAD_EMBEDS else device
            speaker_device = speaker_target_device
            logger.info("Loading TitaNet speaker embedding model on %s...", speaker_target_device)
            speaker_model = EncDecSpeakerLabelModel.from_pretrained("nvidia/speakerverification_en_titanet_large")
            speaker_model = speaker_model.to(speaker_target_device)
            speaker_model.eval()
            speaker_embedding_dim = getattr(speaker_model, "embedding_dim", DEFAULT_SPEAKER_EMBED_DIM)
            logger.info("✅ TitaNet speaker model loaded successfully on %s!", speaker_target_device)
        except Exception as exc:
            logger.warning("⚠️ Failed to load TitaNet: %s", exc)
            logger.warning("Continuing without speaker diarization")
            speaker_model = None

        # Load VAD model
        if TRANSCRIBE_USE_VAD:
            try:
                vad_target_device = "cpu" if CPU_ONLY_VAD_EMBEDS else device
                vad_device = vad_target_device
                logger.info("Loading NeMo VAD model '%s' on %s...", VAD_MODEL_NAME, vad_target_device)
                vad_model = EncDecClassificationModel.from_pretrained(VAD_MODEL_NAME)
                vad_model = vad_model.to(vad_target_device)
                vad_model.eval()
                try:
                    vad_window_stride = float(vad_model.cfg.preprocessor.params.window_stride)
                except Exception:
                    vad_window_stride = 0.01
                logger.info("✅ VAD model loaded successfully!")
            except Exception as vad_error:
                logger.warning("⚠️ Failed to load VAD model '%s': %s", VAD_MODEL_NAME, vad_error)
                vad_model = None
        else:
            vad_model = None

        transcription_model_loaded = True
        logger.info("All models loaded successfully!")

    except Exception as exc:
        logger.error("Failed to load models: %s", exc)
        transcription_model_loaded = False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_service_headers(expires_in: int = 60) -> Dict[str, str]:
    """Build service-to-service auth headers (JWT-only)."""
    if service_auth is None:
        raise RuntimeError("Service authentication not initialized")
    try:
        token = service_auth.create_token(expires_in=expires_in)
        return {"X-Service-Token": token}
    except Exception as e:
        logger.error(f"⚠️ Failed to create service JWT: {e}")
        raise

async def get_emotion_for_text(text: str) -> Dict[str, Any]:
    """Call emotion service to analyze text"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{EMOTION_SERVICE_URL}/analyze",
                json={"text": text},
                headers=get_service_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "emotion": data.get("emotion"),
                    "confidence": data.get("confidence"),
                    "scores": data.get("scores", {})
                }
            else:
                logger.warning(f"Emotion service returned {response.status_code}")
                return {}
    except Exception as e:
        logger.error(f"Failed to get emotion: {e}")
        return {}


async def enrich_segments_with_metadata(
    segments: List[Dict[str, Any]],
    audio_data: np.ndarray,
    sample_rate: int
) -> List[Dict[str, Any]]:
    """
    Enrich transcript segments with emotion and audio metrics
    
    Args:
        segments: List of transcript segments
        audio_data: Full audio waveform
        sample_rate: Audio sample rate
    
    Returns:
        Enriched segments with emotion and audio metrics
    """
    enriched = []
    
    for seg in segments:
        # Extract audio segment
        start_sample = int(seg["start_time"] * sample_rate)
        end_sample = int(seg["end_time"] * sample_rate)
        segment_audio = audio_data[start_sample:end_sample]
        
        # Extract audio metrics
        audio_metrics = {}
        if len(segment_audio) > 0:
            audio_metrics = extract_audio_metrics(
                segment_audio,
                sample_rate,
                text=seg["text"]
            )
        
        # Get emotion (async)
        emotion_data = await get_emotion_for_text(seg["text"])
        
        # Combine all metadata
        enriched_seg = {
            **seg,
            "emotion": emotion_data.get("emotion"),
            "emotion_confidence": emotion_data.get("confidence"),
            "emotion_scores": emotion_data.get("scores"),
            "audio_metrics": audio_metrics
        }
        
        enriched.append(enriched_seg)
    
    logger.info(f"Enriched {len(enriched)} segments with emotion and audio metrics")
    return enriched


async def index_transcript_in_rag(
    job_id: str,
    session_id: str,
    full_text: str,
    audio_duration: float,
    segments: List[Dict[str, Any]]
):
    """
    Index transcript in RAG service for semantic search
    
    Args:
        job_id: Unique job identifier
        session_id: Session identifier
        full_text: Complete transcript text
        audio_duration: Audio duration in seconds
        segments: List of enriched segments
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{RAG_SERVICE_URL}/index/transcript",
                json={
                    "job_id": job_id,
                    "session_id": session_id,
                    "full_text": full_text,
                    "audio_duration": audio_duration,
                    "segments": segments
                },
                headers=get_service_headers()
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Indexed transcript {job_id} in RAG service")
            else:
                logger.warning(f"RAG indexing failed with status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to index in RAG: {e}")
        # Don't raise - indexing failure shouldn't block transcription


async def create_memory_from_transcript(
    job_id: str,
    full_text: str,
    segments: List[Dict[str, Any]]
):
    """
    Create a memory entry from transcript for persistent storage
    
    Args:
        job_id: Unique job identifier
        full_text: Complete transcript text
        segments: List of enriched segments
    """
    # Only create memories for non-empty transcripts
    if not full_text or not full_text.strip():
        return
    
    try:
        # Extract key metadata from segments
        speakers = list(set([seg.get("speaker", "Unknown") for seg in segments if seg.get("speaker")]))
        emotions = [seg.get("emotion") for seg in segments if seg.get("emotion")]
        dominant_emotion = max(set(emotions), key=emotions.count) if emotions else None
        
        # Create memory title from first 50 chars of text
        title = full_text[:50] + "..." if len(full_text) > 50 else full_text
        
        memory_data = {
            "title": title,
            "body": full_text,  # Fixed: was "content", should be "body" per RAG API
            "metadata": {
                "source": f"phone_transcript_{job_id}",
                "transcript_job_id": job_id,
                "speakers": speakers,
                "dominant_emotion": dominant_emotion,
                "segment_count": len(segments)
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{RAG_SERVICE_URL}/memory/add",
                json=memory_data,
                headers=get_service_headers()
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Created memory from transcript {job_id}")
            else:
                logger.warning(f"Memory creation failed with status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to create memory from transcript: {e}")
        # Don't raise - memory creation failure shouldn't block transcription


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT service authentication (Phase 3: Enforce JWT-only + replay)."""
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks
        if request.url.path == "/health":
            return await call_next(request)

        jwt_token = request.headers.get("X-Service-Token")
        if not jwt_token:
            logger.error(f"❌ Missing JWT for {request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Missing service token"})
        
        if not service_auth:
            logger.error(f"❌ Service auth not initialized for {request.url.path}")
            return JSONResponse(status_code=503, content={"detail": "Service auth unavailable"})

        try:
            # Allowed callers: gateway only
            allowed = ["gateway"]
            payload = service_auth.verify_token(jwt_token, allowed_services=allowed, expected_aud="internal")

            # Replay protection
            if get_replay_protector is None:
                logger.warning(f"⚠️ Replay protection not available, skipping replay check")
            else:
                import time as _t
                ttl = max(10, int(payload["expires_at"] - _t.time()) + 10)
                ok, reason = get_replay_protector().check_and_store(payload.get("request_id", ""), ttl)
                if not ok:
                    logger.error(f"❌ JWT replay blocked: reason={reason}")
                    return JSONResponse(status_code=401, content={"detail": "Replay detected"})

            rid_short = str(payload.get('request_id',''))[:8]
            logger.info(f"✅ JWT OK s={payload.get('service_id')} aud=internal rid={rid_short} path={request.url.path}")
            return await call_next(request)
        except Exception as e:
            logger.error(f"❌ JWT rejected: {e} path={request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Invalid service token"})


# Request/Response models
# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    # Startup
    logger.info("Starting Transcription Service...")
    
    # Initialize service auth (Phase 3)
    global service_auth
    try:
        from shared.security.secrets import get_secret
        from shared.security.service_auth import get_service_auth
        jwt_secret = get_secret("jwt_secret", default="dev_jwt_secret")
        if jwt_secret:
            service_auth = get_service_auth(service_id="transcription-service", service_secret=jwt_secret)
            logger.info("✅ JWT service auth initialized (enforcing JWT-only, aud=internal, replay protected)")
    except Exception as e:
        logger.error(f"❌ JWT service auth initialization failed: {e}")
        raise
    
    # Load NeMo models
    load_nemo_models()
    
    # Connect pause manager to Redis
    pause_manager = get_pause_manager()
    pause_manager.redis_url = REDIS_URL
    await pause_manager.connect()
    
    # Set callbacks
    async def on_pause():
        """When Gemma needs GPU - move ASR model to CPU to free VRAM"""
        global asr_model, parakeet_pipeline
        logger.info("[CALLBACK] 🛑 Pause callback triggered - offloading ASR resources")
        
        try:
            if TRANSCRIBE_STRATEGY == "parakeet":
                if parakeet_pipeline is not None:
                    parakeet_pipeline.to("cpu")
                    logger.info("[CALLBACK] ✅ Parakeet model moved to CPU")
            else:
                if asr_model is not None:
                    asr_model = asr_model.to("cpu")
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    logger.info("[CALLBACK] ✅ ASR model moved to CPU, GPU VRAM freed!")
        except Exception as exc:
            logger.error("[CALLBACK] ❌ Failed to offload ASR resources: %s", exc)
    
    async def on_resume():
        """When Gemma done - move ASR model back to GPU"""
        global asr_model, parakeet_pipeline
        logger.info("[CALLBACK] ▶️ Resume callback triggered - reloading ASR to GPU")
        
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if TRANSCRIBE_STRATEGY == "parakeet":
                if parakeet_pipeline is not None:
                    parakeet_pipeline.to(device)
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    logger.info("[CALLBACK] ✅ Parakeet model ready on %s", device.upper())
            else:
                if asr_model is not None:
                    asr_model = asr_model.to(device)
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    logger.info("[CALLBACK] ✅ ASR model back on %s!", device.upper())
        except Exception as exc:
            logger.error("[CALLBACK] ❌ Failed to reload ASR resources: %s", exc)
        
        # Process queued chunks
        queued_chunks = pause_manager.get_queued_chunks()
        if queued_chunks:
            logger.info(f"[CALLBACK] 📋 Processing {len(queued_chunks)} queued chunks")
            # TODO: Process each queued chunk here
    
    pause_manager.set_pause_callback(on_pause)
    pause_manager.set_resume_callback(on_resume)
    
    # Simulate model loading
    global transcription_model_loaded
    transcription_model_loaded = True
    logger.info("Transcription Service started successfully (GPU mode)")
    
    # Signal Gemma to move to CPU now that transcription is ready
    try:
        logger.info("[TRANSCRIPTION] 📡 Signaling Gemma to move to CPU...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://gemma-service:8001/move-to-cpu",
                headers=get_service_headers()
            )
            if response.status_code == 200:
                logger.info("[TRANSCRIPTION] ✅ Gemma moved to CPU, GPU now available for transcription")
            else:
                logger.warning(f"[TRANSCRIPTION] ⚠️ Failed to signal Gemma: {response.status_code}")
    except Exception as e:
        logger.warning(f"[TRANSCRIPTION] ⚠️ Could not signal Gemma to move to CPU: {e}")
        logger.info("[TRANSCRIPTION] This is OK if Gemma is already on CPU or not running")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Transcription Service...")
    await pause_manager.disconnect()
    logger.info("Transcription Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Transcription Service",
    description="NeMo ASR transcription with GPU pause/resume support",
    version="1.0.0",
    lifespan=lifespan
)

# Add JWT middleware (Phase 2: Permissive)
app.add_middleware(ServiceAuthMiddleware)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    pause_manager = get_pause_manager()
    
    return {
        "status": "healthy" if transcription_model_loaded else "unhealthy",
        "model_loaded": transcription_model_loaded,
        "pause_status": pause_manager.get_status()
    }


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_chunk(
    audio: UploadFile = File(...),
    seq: Optional[int] = Form(None),
    stream_id: Optional[str] = Form(None)
):
    """Transcribe audio chunk using NeMo ASR with VAD + diarization."""
    pause_manager = get_pause_manager()

    if not transcription_model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if pause_manager.is_paused():
        chunk_data = {
            "filename": audio.filename,
            "seq": seq,
            "stream_id": stream_id,
        }
        pause_manager.add_to_queue(chunk_data)
        logger.info(
            "Paused - queued chunk %s (queue size=%d)",
            audio.filename,
            len(pause_manager.chunk_queue),
        )
        return TranscriptionResponse(
            job_id=f"queued-{stream_id}-{seq}",
            status="queued",
            message="Transcription paused for high-priority task, chunk queued",
        )

    job_id = f"{stream_id or str(uuid.uuid4())}-{seq or 0}"

    try:
        pause_manager.set_processing(True)

        audio_bytes = await audio.read()
        logger.info("[TRANSCRIPTION] Processing chunk %s (%d bytes)", audio.filename, len(audio_bytes))

        # Load and prepare audio with validation
        try:
            audio_data, sample_rate = sf.read(io.BytesIO(audio_bytes))
        except Exception as e:
            logger.error(f"[AUDIO] Failed to decode audio: {e}")
            raise HTTPException(status_code=400, detail="Invalid audio format")
        
        # Convert to mono
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)
        
        # Ensure float32 and clip to valid range
        audio_data = audio_data.astype(np.float32)
        audio_data = np.clip(audio_data, -1.0, 1.0)
        
        # Resample to 16kHz
        audio_data, sample_rate = _resample_audio(audio_data, sample_rate, 16000)
        audio_duration = len(audio_data) / sample_rate
        
        # Validate minimum length
        if audio_duration < 0.1:
            logger.warning(f"[AUDIO] Too short: {audio_duration:.2f}s")
            raise HTTPException(status_code=400, detail="Audio too short (minimum 0.1 seconds)")

        # Route to Parakeet pipeline if strategy is set
        if TRANSCRIBE_STRATEGY == "parakeet":
            logger.info("[TRANSCRIPTION] Using Parakeet strategy")
            return await _transcribe_with_parakeet(audio_data, sample_rate, audio_duration, job_id, stream_id)

        # VAD with validation and fallback
        try:
            speech_segments = run_vad_segments(audio_data, sample_rate)
            if not speech_segments:
                logger.warning("[VAD] No speech segments found, using full audio")
                speech_segments = [(0.0, audio_duration)]
        except Exception as vad_error:
            logger.error(f"[VAD] Failed: {vad_error}", exc_info=True)
            speech_segments = [(0.0, audio_duration)]

        speech_segments = sorted(speech_segments, key=lambda span: span[0])

        # Extract embeddings with validation
        embeddings = []
        try:
            embeddings = extract_speaker_embeddings(audio_data, sample_rate, speech_segments)
            if not embeddings or len(embeddings) != len(speech_segments):
                logger.warning(f"[DIARIZATION] Embedding mismatch: {len(embeddings)} vs {len(speech_segments)}")
                embeddings = []
        except Exception as embed_error:
            logger.error(f"[DIARIZATION] Embedding extraction failed: {embed_error}", exc_info=True)
            embeddings = []

        # Cluster speakers with validation
        if embeddings:
            try:
                speaker_labels = cluster_speakers(embeddings)
            except Exception as cluster_error:
                logger.error(f"[DIARIZATION] Clustering failed: {cluster_error}", exc_info=True)
                speaker_labels = [0] * len(speech_segments)
        else:
            logger.info("[DIARIZATION] No embeddings - using single speaker")
            speaker_labels = [0] * len(speech_segments)

        if speaker_labels:
            unique_speakers = sorted(set(speaker_labels))
            logger.info(
                "[DIARIZATION] spans=%d unique_speakers=%s",
                len(speech_segments),
                unique_speakers,
            )

        segments: List[Dict[str, Any]] = []
        transcript_text = ""

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                segment_infos: List[Dict[str, Any]] = []
                segment_paths: List[str] = []
                last_decode_end = 0.0

                for idx, ((span_start, span_end), speaker_id) in enumerate(zip(speech_segments, speaker_labels)):
                    decode_start = span_start if span_start >= last_decode_end else last_decode_end
                    decode_end = span_end
                    if decode_end - decode_start <= 0.0:
                        continue

                    start_idx = max(0, int(decode_start * sample_rate))
                    end_idx = min(len(audio_data), int(decode_end * sample_rate))
                    if end_idx <= start_idx:
                        continue

                    segment_audio = audio_data[start_idx:end_idx]
                    if segment_audio.size == 0:
                        continue

                    seg_path = os.path.join(tmpdir, f"segment_{idx}.wav")
                    sf.write(seg_path, segment_audio, sample_rate)
                    segment_paths.append(seg_path)
                    segment_infos.append({
                        "start_time": float(decode_start),
                        "end_time": float(decode_end),
                        "speaker": f"speaker_{int(speaker_id)}",
                    })
                    last_decode_end = decode_end

                if not segment_paths:
                    logger.warning("[TRANSCRIPTION] No valid segments, using fallback ASR")
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                        sf.write(tmp_file.name, audio_data, sample_rate)
                        fallback_path = tmp_file.name
                    try:
                        outputs = asr_model.transcribe([fallback_path], batch_size=1, timestamps=False, return_hypotheses=True)
                        if outputs:
                            first = outputs[0]
                            text = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", str(first))
                            transcript_text = text.strip()
                        segments = [{
                            "text": transcript_text,
                            "speaker": "speaker_0",
                            "start_time": 0.0,
                            "end_time": audio_duration,
                            "speaker_confidence": 1.0,
                        }]
                    finally:
                        with contextlib.suppress(Exception):
                            os.unlink(fallback_path)
                else:
                    texts = transcribe_segments_with_asr(segment_paths, batch_size=max(1, ASR_BATCH_SIZE))
                    for info, text in zip(segment_infos, texts):
                        segments.append({
                            "text": text,
                            "speaker": info["speaker"],
                            "start_time": info["start_time"],
                            "end_time": info["end_time"],
                            "speaker_confidence": 0.9,
                        })
                    transcript_text = " ".join(seg["text"] for seg in segments).strip()
        except Exception as pipeline_error:
            logger.error("[TRANSCRIPTION] Pipeline error: %s", pipeline_error)
            segments = [{
                "text": "",
                "speaker": "speaker_0",
                "start_time": 0.0,
                "end_time": audio_duration,
                "speaker_confidence": 1.0,
            }]
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_data, sample_rate)
                fallback_path = tmp_file.name
            try:
                outputs = asr_model.transcribe([fallback_path], batch_size=1, timestamps=False, return_hypotheses=True)
                if outputs:
                    first = outputs[0]
                    text = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", str(first))
                    transcript_text = text.strip()
                    segments[0]["text"] = transcript_text
            finally:
                with contextlib.suppress(Exception):
                    os.unlink(fallback_path)

        segments = merge_adjacent_segments(sorted(segments, key=lambda s: s["start_time"]), MERGE_GAP_SEC)
        logger.info(
            "[TRANSCRIPTION] Raw segments=%d merged=%d",
            len(segment_infos) if 'segment_infos' in locals() else len(segments),
            len(segments),
        )

        enriched_segments = await enrich_segments_with_metadata(segments, audio_data, sample_rate)
        full_text = " ".join(seg["text"] for seg in enriched_segments).strip()

        asyncio.create_task(
            index_transcript_in_rag(
                job_id=job_id,
                session_id=stream_id or "default",
                full_text=full_text,
                audio_duration=audio_duration,
                segments=enriched_segments,
            )
        )

        asyncio.create_task(
            create_memory_from_transcript(
                job_id=job_id,
                full_text=full_text,
                segments=enriched_segments,
            )
        )

        logger.info(
            "[TRANSCRIPTION] Finished chunk %s -> %d segments (duration %.2fs)",
            audio.filename,
            len(enriched_segments),
            audio_duration,
        )

        return TranscriptionResponse(
            job_id=job_id,
            status="complete",
            text=full_text,
            segments=enriched_segments,
            message="Success",
        )

    except HTTPException:
        # Re-raise HTTP exceptions (400, 503, etc.)
        raise
    except Exception as exc:
        logger.error("[TRANSCRIPTION] Fatal transcription error: %s", exc, exc_info=True)
        # Return valid error response instead of raising
        return TranscriptionResponse(
            job_id=job_id,
            status="error",
            text="",
            segments=[],
            message=f"Transcription failed: {str(exc)}"
        )
    finally:
        pause_manager.set_processing(False)



@app.get("/pause/status")
async def get_pause_status():
    """Get pause manager status"""
    pause_manager = get_pause_manager()
    return pause_manager.get_status()


@app.post("/pause/process-queue")
async def process_queued_chunks():
    """
    Manually trigger processing of queued chunks
    (Normally triggered automatically on resume)
    """
    pause_manager = get_pause_manager()
    
    if pause_manager.is_paused():
        return {"status": "still_paused", "message": "Cannot process while paused"}
    
    queued_chunks = pause_manager.get_queued_chunks()
    
    if not queued_chunks:
        return {"status": "no_chunks", "message": "No chunks in queue"}
    
    logger.info(f"Processing {len(queued_chunks)} queued chunks...")
    
    # Process each chunk
    # In production: call transcription for each
    processed = []
    for chunk in queued_chunks:
        logger.info(f"Processing queued chunk: {chunk}")
        # Process chunk...
        processed.append(chunk)
    
    return {
        "status": "processed",
        "count": len(processed),
        "chunks": processed
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
