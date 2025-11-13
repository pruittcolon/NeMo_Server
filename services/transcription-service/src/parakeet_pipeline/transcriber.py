"""High-level Parakeet transcription pipeline."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

import torch
from nemo.collections.asr.models import EncDecCTCModelBPE

from .chunker import ConvertedAudio, convert_audio_to_wav, split_audio_into_chunks
from .diarizer import PyannoteDiarizer, assign_speakers, SpeakerSegment

try:  # Optional dependency
    from .nemo_sortformer import NemoSortformerDiarizer
except Exception:  # pragma: no cover - fallback if NeMo extras missing
    NemoSortformerDiarizer = None

logger = logging.getLogger(__name__)


@dataclass
class ParakeetSegment:
    """Speech segment produced by the Parakeet pipeline."""

    start: float
    end: float
    text: str
    speaker: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ParakeetTranscription:
    """Full transcription result."""

    text: str
    segments: List[ParakeetSegment] = field(default_factory=list)
    duration: float = 0.0


class ParakeetPipeline:
    """Encapsulates the Parakeet-TDT ASR model and optional Pyannote diarization."""

    def __init__(
        self,
        model_id: str = "nvidia/parakeet-tdt-0.6b-v2",
        chunk_duration: int = 300,
        device: Optional[str] = None,
        enable_diarization: bool = True,
        diarization_device: str = "cpu",
        diarization_num_speakers: Optional[int] = None,
    ) -> None:
        self.model_id = model_id
        self.chunk_duration = chunk_duration
        self.model_device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info("Loading Parakeet model %s on %s", self.model_id, self.model_device)
        self.model: EncDecCTCModelBPE = EncDecCTCModelBPE.from_pretrained(self.model_id)
        self.model = self.model.to(self.model_device)
        self.model.eval()
        logger.info("Parakeet model loaded successfully")

        self.diarizer_backend = os.getenv("DIARIZER_BACKEND", "pyannote").lower()
        self.diarizer: Optional[object] = None
        if enable_diarization:
            if self.diarizer_backend == "nemo":
                self.diarizer = self._init_nemo_diarizer(diarization_num_speakers)
            else:
                self.diarizer = self._init_pyannote_diarizer(
                    diarization_device, diarization_num_speakers
                )

        if self.diarizer:
            logger.info("Diarization backend enabled: %s", self.diarizer_backend)
        else:
            logger.info("Diarization disabled or unavailable (requested backend=%s)", self.diarizer_backend)

    # ------------------------------------------------------------------#
    # Device management
    # ------------------------------------------------------------------#
    def to(self, device: str) -> None:
        """Move the ASR model to the requested device."""
        target = device
        if target == self.model_device:
            return
        if target == "cuda" and not torch.cuda.is_available():
            target = "cpu"

        logger.info("Moving Parakeet model to %s", target)
        self.model = self.model.to(target)
        self.model_device = target

        if target == "cpu":
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------#
    # Transcription
    # ------------------------------------------------------------------#
    def transcribe_file(self, audio_path: str) -> ParakeetTranscription:
        """
        Transcribe an audio file using Parakeet and optional diarization.

        Args:
            audio_path: path to an audio file (any format supported by ffmpeg)
        """
        converted: ConvertedAudio = convert_audio_to_wav(audio_path)
        chunk_paths, duration = split_audio_into_chunks(converted.path, self.chunk_duration)

        full_text_parts: List[str] = []
        segments: List[ParakeetSegment] = []

        try:
            for index, chunk_path in enumerate(chunk_paths):
                offset = index * self.chunk_duration
                chunk_segments = self._transcribe_chunk(chunk_path, offset)
                if not chunk_segments:
                    continue

                full_text_parts.append(" ".join(seg.text for seg in chunk_segments if seg.text))
                segments.extend(chunk_segments)

            if self.diarizer:
                diarized_segments: List[SpeakerSegment] = self.diarizer.diarize(converted.path)
                assign_speakers(segments, diarized_segments)

            # Normalise speaker labels
            for seg in segments:
                seg.speaker = _normalise_speaker_label(seg.speaker)

            full_text = " ".join(part for part in full_text_parts if part).strip()
            return ParakeetTranscription(
                text=full_text,
                segments=segments,
                duration=duration,
            )
        finally:
            # Clean up temporary assets
            for chunk in chunk_paths:
                if chunk != converted.path and os.path.exists(chunk):
                    try:
                        os.unlink(chunk)
                    except OSError:
                        pass
            converted.cleanup()

    def _transcribe_chunk(self, chunk_path: str, offset: float) -> List[ParakeetSegment]:
        """
        Transcribe an individual chunk and return segments with offsets applied.
        """
        try:
            hypotheses = self.model.transcribe(
                [chunk_path],
                return_hypotheses=True,
                timestamps=True,
            )
        except Exception as exc:
            logger.error("Parakeet transcription failed for %s: %s", chunk_path, exc)
            return []

        if not hypotheses:
            return []

        hypothesis = hypotheses[0]
        text = getattr(hypothesis, "text", "") or ""
        text = text.strip()
        segments: List[ParakeetSegment] = []

        timestamp_info = getattr(hypothesis, "timestamp", None)
        segment_entries = []
        if isinstance(timestamp_info, dict):
            segment_entries = timestamp_info.get("segment") or timestamp_info.get("segments") or []

        if segment_entries:
            for entry in segment_entries:
                start = float(entry.get("start", 0.0)) + offset
                end = float(entry.get("end", start)) + offset
                segment_text = entry.get("text") or entry.get("segment") or text
                segments.append(
                    ParakeetSegment(
                        start=start,
                        end=end,
                        text=segment_text.strip(),
                    )
                )
        else:
            words = text.split()
            approx_duration = max(1.0, len(words) / 2.5)
            segments.append(
                ParakeetSegment(
                    start=offset,
                    end=offset + approx_duration,
                    text=text,
                )
            )

        # Ensure segments are ordered and contiguous
        segments.sort(key=lambda seg: seg.start)
        return segments

    # ------------------------------------------------------------------#
    # Diarizer initialisation helpers
    # ------------------------------------------------------------------#
    def _init_pyannote_diarizer(
        self,
        device: str,
        num_speakers: Optional[int],
    ) -> Optional[PyannoteDiarizer]:
        diarizer = PyannoteDiarizer(
            device=device,
            num_speakers=num_speakers,
        )
        if diarizer and diarizer.pipeline:
            return diarizer
        logger.warning("Pyannote diarization unavailable (missing token or dependency)")
        return None

    def _init_nemo_diarizer(self, num_speakers: Optional[int]) -> Optional[object]:
        if NemoSortformerDiarizer is None:
            logger.warning("NeMo diarizer unavailable (nemo_toolkit not installed)")
            return None

        model_path = os.getenv("SORTFORMER_MODEL")
        if not model_path:
            logger.warning("SORTFORMER_MODEL env var not set; cannot enable NeMo diarizer")
            return None

        max_spks = num_speakers or int(os.getenv("SORTFORMER_MAX_SPKS", "4"))
        device = os.getenv("SORTFORMER_DEVICE", "cuda")
        try:
            return NemoSortformerDiarizer(
                nemo_model_path=model_path,
                max_speakers=max_spks,
                device=device,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to initialise NeMo diarizer: %s", exc)
            return None


def _normalise_speaker_label(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    label = label.lower()
    if label.startswith("speaker_"):
        suffix = label.split("_", 1)[1]
        if suffix.startswith("speaker_"):
            suffix = suffix.split("_", 1)[1]
        if suffix.startswith("spk"):
            suffix = suffix.replace("spk", "")
        suffix = suffix.replace("speaker", "")
        suffix = suffix.strip("_")
        try:
            idx = int(suffix)
        except ValueError:
            return f"speaker_{suffix}"
        return f"speaker_{idx}"
    return label
