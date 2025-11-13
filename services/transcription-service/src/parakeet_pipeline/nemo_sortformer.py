"""NeMo Sortformer diarization wrapper."""

from __future__ import annotations

import logging
import os
from typing import List

from nemo.collections.asr.models import SortformerEncLabelModel

from .diarizer import SpeakerSegment

logger = logging.getLogger(__name__)
if logger.level > logging.INFO:
    logger.setLevel(logging.INFO)


class NemoSortformerDiarizer:
    """Wraps the pretrained Sortformer diarizer stored as a .nemo file."""

    def __init__(
        self,
        nemo_model_path: str,
        max_speakers: int = 4,
        device: str = "cuda",
    ) -> None:
        if not nemo_model_path or not os.path.exists(nemo_model_path):
            raise FileNotFoundError(f"Sortformer model not found: {nemo_model_path}")

        self.model_path = nemo_model_path
        self.max_speakers = max(1, max_speakers)
        self.device = device if device in {"cuda", "cpu"} else "cuda"
        logger.info("Loading Sortformer diarizer %s on %s", self.model_path, self.device)

        self.model: SortformerEncLabelModel = SortformerEncLabelModel.restore_from(
            restore_path=self.model_path,
            map_location=self.device,
            strict=False,
        )
        self.model.eval()
        self.model.freeze()
        logger.info("Sortformer diarizer ready")

    def diarize(self, audio_path: str) -> List[SpeakerSegment]:
        if not audio_path or not os.path.exists(audio_path):
            logger.error("Audio file missing for diarization: %s", audio_path)
            return []

        try:
            diar_outputs = self.model.diarize(
                audio=audio_path,
                batch_size=1,
                include_tensor_outputs=False,
                num_workers=0,
                verbose=False,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Sortformer diarization failed: %s", exc)
            return []

        if not diar_outputs:
            logger.warning("Sortformer diarizer returned no output")
            return []

        raw_output = diar_outputs[0]
        logger.info(
            "Sortformer raw diarization output (%d entries): %s",
            len(raw_output),
            raw_output,
        )
        parsed = _parse_segments(raw_output, self.max_speakers)
        logger.info(
            "Sortformer parsed %d speaker segment(s)", len(parsed)
        )
        return parsed


def _parse_segments(raw_segments: List[str], max_speakers: int) -> List[SpeakerSegment]:
    logger.info("Parsing raw diarization segments: %s", raw_segments)
    segments: List[SpeakerSegment] = []
    for line in raw_segments:
        if not line:
            continue
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        try:
            start = float(parts[0])
            end = float(parts[1])
        except ValueError:
            continue
        speaker = parts[2]
        if not speaker.startswith("speaker_"):
            speaker = f"speaker_{speaker}"

        # Clamp speaker index when the model predicts more speakers than requested
        try:
            idx = int(speaker.split("_", 1)[1])
        except (ValueError, IndexError):
            idx = None
        if idx is not None and idx >= max_speakers:
            # Preserve the predicted speaker id instead of wrapping via modulo.
            # Wrapping collapses distinct speakers (e.g., speaker_4 -> speaker_0),
            # which causes multiple voices to share one label.
            logger.warning(
                "Sortformer predicted speaker_%s beyond max_speakers=%s; keeping original label to avoid collisions",
                idx,
                max_speakers,
            )
            speaker = f"speaker_{idx}"

        segments.append(
            SpeakerSegment(
                start=start,
                end=end,
                speaker=speaker,
            )
        )

    segments.sort(key=lambda seg: seg.start)
    logger.info("Sortformer normalized segments: %s", segments)
    return segments
