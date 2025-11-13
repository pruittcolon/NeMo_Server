"""Pyannote diarization wrapper for the Parakeet pipeline."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import torch

logger = logging.getLogger(__name__)
if logger.level > logging.INFO:
    logger.setLevel(logging.INFO)


@dataclass
class SpeakerSegment:
    """Represents a diarized speaker span."""

    start: float
    end: float
    speaker: str


class PyannoteDiarizer:
    """Thin wrapper around pyannote.audio diarization pipeline."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        device: str = "cpu",
        num_speakers: Optional[int] = None,
    ) -> None:
        self.token = (
            access_token
            or os.environ.get("HUGGINGFACE_TOKEN")
            or os.environ.get("HUGGINGFACE_ACCESS_TOKEN")
            or os.environ.get("HF_TOKEN")
            or os.environ.get("HF_ACCESS_TOKEN")
        )
        self.device = device
        self.num_speakers = num_speakers
        self.pipeline = None

        if not self.token:
            logger.warning("No HuggingFace token provided; Pyannote diarization disabled")
            return

        self._initialize()

    def _initialize(self) -> None:
        try:
            from pyannote.audio import Pipeline

            logger.info("Loading Pyannote diarization pipeline (device=%s)", self.device)
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.token,
            )

            target_device = "cuda" if self.device == "cuda" and torch.cuda.is_available() else "cpu"
            self.pipeline.to(torch.device(target_device))
            logger.info("Pyannote pipeline ready on %s", target_device)
        except Exception as exc:
            logger.error("Failed to initialise Pyannote diarization: %s", exc)
            self.pipeline = None

    def diarize(self, audio_path: str) -> List[SpeakerSegment]:
        if not self.pipeline:
            return []

        try:
            diarization = self.pipeline(
                audio_path,
                num_speakers=self.num_speakers,
            )
        except Exception as exc:
            logger.error("Pyannote diarization failed: %s", exc)
            return []

        segments: List[SpeakerSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_label = str(speaker)
            if not speaker_label.startswith("speaker_"):
                speaker_label = f"speaker_{speaker_label}"
            segments.append(
                SpeakerSegment(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker=speaker_label,
                )
            )

        segments.sort(key=lambda seg: seg.start)
        logger.info("Pyannote detected %d speaker segment(s)", len(segments))
        return segments


def assign_speakers(
    transcript_segments: List["ParakeetSegmentProtocol"],
    speaker_segments: List[SpeakerSegment],
) -> None:
    """
    Annotate transcription segments with speaker labels based on overlap.

    Segments are modified in-place.
    """
    if not transcript_segments or not speaker_segments:
        return

    for segment in transcript_segments:
        overlaps = []
        for speaker_segment in speaker_segments:
            overlap_start = max(segment.start, speaker_segment.start)
            overlap_end = min(segment.end, speaker_segment.end)
            if overlap_end > overlap_start:
                overlaps.append((overlap_end - overlap_start, speaker_segment.speaker))

        if overlaps:
            overlaps.sort(key=lambda item: item[0], reverse=True)
            _, best_speaker = overlaps[0]
            segment.speaker = best_speaker
            logger.info(
                "Assigned speaker %s to segment %.2f-%.2f with overlaps %s",
                best_speaker,
                getattr(segment, "start", -1),
                getattr(segment, "end", -1),
                overlaps,
            )
        else:
            logger.info(
                "No diarization overlap found for segment %.2f-%.2f",
                getattr(segment, "start", -1),
                getattr(segment, "end", -1),
            )


class ParakeetSegmentProtocol:
    """
    Protocol-like helper for type checking. Any object providing start/end/speaker attributes is accepted.
    """

    start: float
    end: float
    speaker: Optional[str]
